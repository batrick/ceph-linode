import binascii
import json
import logging
import os
import sys
import socket

from linode_api4 import LinodeClient, Instance

prm_region = "us-east"
prm_image = "linode/centos7"
prm_osd_size = 20
prm_osds_per_host = 1

# should not have to modify what's below

ssh_private_key_file = os.getenv("HOME") + "/.ssh/id_rsa"
ssh_public_key_file = os.getenv("HOME") + "/.ssh/id_rsa.pub"
with open(ssh_public_key_file) as f:
    ssh_private_key = f.read()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')



# read cluster definition (host types and their properties)

try:
    with open('cluster.json', 'r') as cl:
        CLUSTER = json.load(cl)
except IOError as e:
    print('file cluster.json not found')
    sys.exit(1)
print(json.dumps(CLUSTER, indent=4))

linodes = []

def launch(api4_client):
    print('')
    print('currently running instances:')
    for c in api4_client.linode.instances():
        print(c.label)

    print('')
    print('currently existing volumes:')
    for v in api4_client.volumes():
        print('%s size %d region %s linode %s' % (
            v.label, v.size, v.region, v.linode_id))
    print('')
    sys.stdout.flush()

    regions = api4_client.regions()
    for r in regions:
        if str(r).lower().__contains__(prm_region.lower()):
            region = r
            break
    logging.info('region is %s' % region)

    types = api4_client.linode.types()
    new_linodes = {}
    for c in CLUSTER:
        plan = c['plan']
        count = c['count']
        prefix = c['prefix']
        ansible_group = prefix + 's'
        for t in types:
            if str(t).lower().__contains__(plan.lower()):
                vmtype = t
                break
        for host in range(0, count):
            new_linode, password = api4_client.linode.instance_create(
                vmtype,
                region,
                image=prm_image,
                authorized_keys = ssh_public_key_file)
            ipv6addr = new_linode.ipv6.split('/')[0]
            label = new_linode.label
            new_linodes[str(new_linode)] = (vmtype, ansible_group, ipv6addr, region, password)
            logging.info('%s, %s, %s, %s' % (new_linode, ipv6addr, ansible_group, vmtype))
            if prefix == 'osd':
                for dev in range(0, prm_osds_per_host):
                    new_vol = api4_client.volume_create(
                                'v_%s_%d_v%d' % (prefix, host, dev),
                                size=prm_osd_size,
                                region=region)
                    new_vol.attach(new_linode)
                    logging.info('attached volume %s to instance %s' % (new_vol, new_linode))

    with open("ansible_inventory", mode = 'w') as f:
        groups = set()
        for inst in new_linodes.keys():
            (_, gr, _, _, _) = new_linodes[inst]
            groups.add(gr)
        for next_gr in groups:
            f.write('\n')
            f.write('[' + next_gr + ']\n')
            for inst in new_linodes.keys():
                (ty, gr, ip, rg, pw) = new_linodes[inst]
                if gr == next_gr:
                    f.write(ip + '\n')

def main():
    token_fn = os.getenv("LINODE_API_TOKEN")
    if token_fn is None:
        raise RuntimeError("please specify Linode API token filename")
    with open(token_fn, 'r') as tf:
        token = tf.readline().strip()
    client = LinodeClient(token)
    launch(client)

if __name__ == "__main__":
    main()
