import binascii
import json
import logging
import os
import sys

from contextlib import closing, contextmanager
from multiprocessing.dummy import Pool as ThreadPool
from threading import BoundedSemaphore

import linode.api as linapi

try:
    with open("LINODE_GROUP") as f:
        GROUP = unicode(f.read())
except IOError as e:
    GROUP = unicode("ceph-"+binascii.b2a_hex(os.urandom(3)))
    with open("LINODE_GROUP", "w") as f:
        f.write(GROUP)

@contextmanager
def releasing(semaphore):
    semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

DATACENTER = "Newark"
DISTRIBUTION = "CentOS 7"
KERNEL = "Latest 64 bit"
SSH_PRIVATE_KEY_FILE = os.getenv("HOME") + "/.ssh/id_rsa"
SSH_PUBLIC_KEY_FILE = os.getenv("HOME") + "/.ssh/id_rsa.pub"
with open(SSH_PUBLIC_KEY_FILE) as f:
    SSH_KEY = f.read()

# read cluster definition (host types and their properties)

try:
    with open('cluster.json', 'r') as cl:
        CLUSTER = json.load(cl, 'latin-1')
except IOError as e:
    print('file cluster.json not found')
    sys.exit(1)
print(json.dumps(CLUSTER, indent=4))

linodes = []
create_semaphore = BoundedSemaphore(15)
config_semaphore = BoundedSemaphore(8)
def do_create(client, running, datacenter, plans, distribution, kernel, machine, i):
    plan = filter(lambda p: p[u'LABEL'].lower().find(str(machine['plan']).lower()) >= 0, plans)[0]
    name =  u'{0}-{1:03d}'.format(machine['prefix'], i)
    label =  u'{0}-{1}'.format(GROUP, name)
    logging.info("%s", "creating {}".format(label))

    active = filter(lambda x: x[u'LABEL'] == label and x[u'LPM_DISPLAYGROUP'] == GROUP, running)
    assert(len(active) <= 1)
    if active:
        logging.info("%s", "linode {} already exists: {}".format(label, active[0][u'LINODEID']))
        node = {u'LinodeID': active[0][u'LINODEID']}
    else:
        with releasing(create_semaphore):
            node = client.linode_create(DatacenterID = datacenter, PlanID = plan[u'PLANID'], PaymentTerm = 1)
            client.linode_update(LinodeID = node[u'LinodeID'], Label = label, lpm_displayGroup = GROUP, watchdog = 1, Alert_cpu_enabled = 0)
            logging.info("created %s: %s", label, node[u'LinodeID'])

    with releasing(config_semaphore):
        try:
            client.linode_ip_addprivate(LinodeID = node[u'LinodeID'])
        except linapi.ApiError as err:
            err = err.value[0]
            if err[u'ERRORCODE'] != 8:
                logging.error(err)
                raise
        ips = client.linode_ip_list(LinodeID = node[u'LinodeID'])
        ip_private = filter(lambda ip: not ip[u'ISPUBLIC'], ips)[0][u'IPADDRESS']
        ip_public = filter(lambda ip: ip[u'ISPUBLIC'], ips)[0][u'IPADDRESS']

        current_disks = client.linode_disk_list(LinodeID = node[u'LinodeID'])
        configs = client.linode_config_list(LinodeID = node[u'LinodeID'])
        try:
            swap_size = int(machine['swap_size'] if machine.get('swap_size') is not None else 128)
            root_size = int(machine['root_size'] if machine.get('root_size') is not None else int(plan['DISK'])*1024 - swap_size)
            if root_size + swap_size < int(plan['DISK'])*1024:
                raw_size = int(plan['DISK'])*1024 - (root_size+swap_size)
            else:
                raw_size = 0
            disks = []
            root = filter(lambda d: d[u'LABEL'] == u'root', current_disks)
            if root:
                root = root[0]
                assert(root[u'SIZE'] == int(root_size))
                disks.append({u'DiskID': root[u'DISKID']})
            else:
                disks.append(client.linode_disk_createfromdistribution(LinodeID = node[u'LinodeID'], Label = u'root', DistributionID = distribution, rootPass = binascii.b2a_hex(os.urandom(20)), Size = root_size, rootSSHKey = SSH_KEY))
            swap = filter(lambda d: d[u'LABEL'] == u'swap', current_disks)
            if swap:
                swap = swap[0]
                assert(swap[u'SIZE'] == int(swap_size))
                assert(swap[u'TYPE'] == u'swap')
                disks.append({u'DiskID': swap[u'DISKID']})
            else:
                disks.append(client.linode_disk_create(LinodeID = node[u'LinodeID'], Label = u'swap', Type = u'swap', Size = swap_size))
            raw = filter(lambda d: d[u'LABEL'] == u'raw', current_disks)
            if raw:
                raw = raw[0]
                assert(raw[u'SIZE'] == int(raw_size))
                assert(raw[u'TYPE'] == u'raw')
                disks.append({u'DiskID': raw[u'DISKID']})
            elif raw_size > 0:
                disks.append(client.linode_disk_create(LinodeID = node[u'LinodeID'], Label = u'raw', Type = u'raw', Size = raw_size))
            disks = [unicode(d[u'DiskID']) for d in disks]
            disklist = u','.join(disks)
            logging.info("%s", "{} disks: {}".format(label, disks))
            ceph_config = filter(lambda c: c[u'Label'] == u'ceph', configs)
            if ceph_config:
                logging.info("%s", "{} ceph config already setup".format(label))
                config = ceph_config[0]
            else:
                config = client.linode_config_create(LinodeID = node[u'LinodeID'], Label = u'ceph', KernelID = kernel, Disklist = disklist, RootDeviceNum = 1)
        except linapi.ApiError as err:
            raise

        if active and active[0][u'STATUS'] == 1:
            logging.info("%s", "Linode {} already running.".format(label))
        else:
            client.linode_boot(LinodeID = node[u'LinodeID'], ConfigID = config[u'ConfigID'])
            logging.info("%s", "booted {}: {}".format(label, node[u'LinodeID']))
        linodes.append({"id": node[u'LinodeID'], "name": name, "label": label, "ip_private": ip_private, "ip_public": ip_public, "group": machine['group'], "user": "root", "key": SSH_PRIVATE_KEY_FILE})

def create(*args, **kwargs):
    try:
        do_create(*args, **kwargs)
    except Exception as e:
        logging.exception(e)
        os._exit(1)

def launch(client):
    datacenters = client.avail_datacenters()
    plans = client.avail_linodeplans()
    distributions = client.avail_distributions()
    kernels = client.avail_kernels()

    datacenter = filter(lambda d: d[u'LOCATION'].lower().find(DATACENTER.lower()) >= 0, datacenters)[0][u'DATACENTERID']
    distribution = filter(lambda d: d[u'LABEL'].lower().find(DISTRIBUTION.lower()) >= 0, distributions)[0][u'DISTRIBUTIONID']
    kernel = filter(lambda k: k[u'LABEL'].lower().find(str(KERNEL).lower()) >= 0, kernels)[0][u'KERNELID']

    running = client.linode_list()

    with closing(ThreadPool(50)) as pool:
        for machine in CLUSTER:
            for i in range(machine['count']):
                logging.info("%s", "i={i}".format(i=i))
                pool.apply_async(create, (client, running, datacenter, plans, distribution, kernel, machine, i))
        pool.close()
        pool.join()

    logging.info("%s", client.linode_list())

    with open("ansible_inventory", mode = 'w') as f:
        groups = set([linode['group'] for linode in linodes])
        for group in groups:
            f.write("[{}]\n".format(group))
            for linode in linodes:
                if linode['group'] == group:
                    f.write("\t{} ansible_ssh_host={} ansible_ssh_port=22 ansible_ssh_user='root' ansible_ssh_private_key_file='{}'\n".format(linode['name'], linode['ip_public'], SSH_PRIVATE_KEY_FILE))

    with open("linodes", mode = 'w') as f:
        f.write(json.dumps(linodes))

def main():
    key = os.getenv("LINODE_API_KEY")
    if key is None:
        raise RuntimeError("please specify Linode API key")

    client = linapi.Api(key = key, batching = False)

    launch(client)

if __name__ == "__main__":
    main()
