import binascii
import json
import logging
import os
import sys
import socket
import time

from contextlib import closing, contextmanager
from multiprocessing.dummy import Pool as ThreadPool
from threading import BoundedSemaphore

from linode_api4 import LinodeClient

try:
    with open("LINODE_GROUP") as f:
        GROUP = unicode(f.read().strip())
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

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
    
    for p in plans:
        str_plan_label = p.label
        str_reduced_plan_label = str_plan_label.split(" ")[1]
        if str(machine['plan']).lower() == str_reduced_plan_label.lower():
            plan = p
            logging.info("plan: %s" % plan)
            
    name =  u'{0}-{1:03d}'.format(machine['prefix'], i)
    label =  u'{0}-{1}'.format(GROUP, name)
    logging.info("%s", "creating {}".format(label))

    active = ""
    for node in running:
        str_label = node.label
        str_group = GROUP
        if str_label == label and str_group == GROUP:
            active = node
            logging.info("active: %s" % active)

    if active:
        logging.info("%s", "linode {} already exists: {}".format(label, active.id))
        node = client.load(active, active.id)
    else:
        with releasing(create_semaphore):
            node = client.linode.instance_create(ltype = plan.id, 
                                               region = datacenter,
                                               label = label,
                                               group = GROUP,
                                               tags = [GROUP])
            
            logging.info("created %s: %s", label, node.id)

    with releasing(config_semaphore):
        try:
            node.ip_allocate(False)
            status_check(node, "offline")
        except Exception as err:
            if err.status == 400:
                logging.error(err)
            elif err.status != 8:
                logging.error(err)
                raise
        ip_private = node.ipv4[1]
        ip_public = node.ipv4[0]

        current_disks = node.disks
        configs = node.configs
        try:
            swap_size = int(machine['swap_size'] if machine.get('swap_size') is not None else 128)
            root_size = int(machine['root_size'] if machine.get('root_size') is not None else int(plan.disk) - swap_size)
            if root_size + swap_size < int(plan.disk):
                raw_size = int(plan.disk) - (root_size+swap_size)
            else:
                raw_size = 0
            disks = []
            
            root = ""
            swap = ""
            raw = ""
            for disk in current_disks:
                dlabel = disk.label
                if dlabel == "root":
                    root = disk
                if dlabel == 'swap':
                    swap = disk
                if dlabel == 'raw':
                    raw = disk
            if root: 
                assert(root.size == int(root_size))
                disks.append(root)
            else:
                root_disk = node.disk_create(label = u'root', 
                                              image = distribution,
                                              filesystem = u'ext4',
                                              rootPass = binascii.b2a_hex(os.urandom(20)), 
                                              size = root_size, 
                                              authorized_keys=SSH_PUBLIC_KEY_FILE)
                disk_status_check(node, root_disk[0], "ready")
                disks.append(root_disk[0])
                
            if swap:
                assert(swap.size == int(swap_size))
                assert(swap.filesystem == u'swap')
                disks.append(swap)
            else:
                swap_disk = node.disk_create(label = u'swap', 
                                              filesystem = u'swap', 
                                              size = swap_size)
                disk_status_check(node, swap_disk, "ready")
                disks.append(swap_disk)

            if raw:
                assert(raw.size == int(raw_size))
                assert(raw.filesystem == u'raw')
                disks.append(raw)
            elif raw_size > 0:
                raw_disk = node.disk_create(label = u'raw', 
                                              filesystem = u'raw', 
                                              size = raw_size)
                disk_status_check(node, raw_disk, "ready")
                disks.append(raw_disk)
                
            disklist = disks
            logging.info("%s", "{} disks: {}".format(label, disks))
            ceph_config = filter(lambda c: c.label == u'ceph', configs)
            if ceph_config:
                logging.info("%s", "{} ceph config already setup".format(label))
                config = ceph_config[0]
            else:
                config = node.config_create(label = u'ceph', 
                                            kernal = kernel, 
                                            disks = disklist, 
                                            root_device = '/dev/sda')
        except Exception as err:
            raise

        if active and active.status == "running":
            logging.info("%s", "Linode {} already running.".format(label))
        else:
            node.reboot()
            logging.info("%s", "booted {}: {}".format(label, node.id))
        linodes.append({"id": node.id, 
                        "name": name, 
                        "label": label, 
                        "ip_private": ip_private, 
                        "ip_public": ip_public, 
                        "group": machine['group'], 
                        "user": "root", 
                        "key": SSH_PRIVATE_KEY_FILE})

def create(*args, **kwargs):
    try:
        do_create(*args, **kwargs)
    except Exception as e:
        logging.exception(e)
        os._exit(1)

def launch(client):
    datacenters = client.regions()
    plans = client.linode.types()
    distributions = client.images()
    kernals = client.linode.kernels()
    
    for d in datacenters:
        str_d_id = d.id 
        if CLUSTER['datacenter'].lower() in str_d_id:
            datacenter = d.id
            logging.info("datacenter: %s" % datacenter) 
            
    for distro in distributions:
        str_distro_label = distro.label
        if  CLUSTER['distribution'].lower() == str_distro_label.lower():
            distribution = distro.id
            logging.info("distro: %s" % distribution)
    
    if isinstance(CLUSTER['kernel'], str) or isinstance(CLUSTER['kernel'], unicode):
        for k in kernels:
            if str(CLUSTER['kernel']).lower() in k.id:
                kernel = k.id
                logging.info("kernal: %s" % kernel)
    elif isinstance(CLUSTER['kernel'], int):
        kernel = CLUSTER['kernel']
    else:
        raise RuntimeError("kernel field bad")

    running = client.linode.instances()

    with closing(ThreadPool(50)) as pool:
        for machine in CLUSTER['nodes']:
            for i in range(machine['count']):
                logging.info("%s", "i={i}".format(i=i))
                pool.apply_async(create, (client, running, datacenter, plans, distribution, kernel, machine, i))
        pool.close()
        pool.join()

    logging.info("%s", client.linode.instances())

    with open("ansible_inventory", mode = 'w') as f:
        groups = set([linode['group'] for linode in linodes])
        for group in groups:
            f.write("[{}]\n".format(group))
            for linode in linodes:
                if linode['group'] == group:
                    if socket.gethostname().endswith('.linode.com'):
                        # assumes deployment node is at same site as ceph cluster
                        ip_key = 'ip_private'
                    else:
                        ip_key = 'ip_public'
                    f.write("\t{} ansible_ssh_host={} ansible_ssh_port=22 ansible_ssh_user='root' ansible_ssh_private_key_file='{}'".format(linode['name'], linode[ip_key], SSH_PRIVATE_KEY_FILE))
                    if 'mon' in linode['name']:
                        f.write(" monitor_address={}".format(linode[ip_key]))
                    f.write("\n")

    with open("linodes", mode = 'w') as f:
        f.write(json.dumps(linodes))

def status_check(node, status):
    logging.info("checking node status")
    cur_status = ""
    
    while cur_status != status:
        time.sleep(10)
        cur_status = node.status
    
    return

def disk_status_check(node, disk_id, status):
    logging.debug("checking that disk is ready")
    cur_status = ""
    
    while cur_status != status:
        time.sleep(10)
        for disk in node.disks:
            if disk.id == disk_id.id:
                cur_status = disk.status
    return
    

def main():
    key = os.getenv("LINODE_API_KEY")
    if key is None:
        raise RuntimeError("please specify Linode API key")

    client = LinodeClient(key)
    
    launch(client)

if __name__ == "__main__":
    main()
