#!/usr/bin/env python
import binascii
import json
import logging
import os
import sys
import socket

import linode_api4

# default values

prm_region = "us-east"
prm_image = "linode/centos7"
prm_osd_size_GB = 20
prm_osds_per_host = 1

# should not have to modify what's below

ssh_public_key_filename = os.getenv("HOME") + "/.ssh/id_rsa.pub"
kfn = os.getenv('SSH_PUBLIC_KEY_FILENAME')
if kfn:
    ssh_public_key_filename = kfn

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# read group ID

try:
    with open('LINODE_GROUP', 'r') as gf:
        my_group = gf.readline().strip()
except IOError as e:
    my_group = "ceph-" + str(binascii.b2a_hex(os.urandom(3)))[2:-1]
    with open('LINODE_GROUP', 'w') as gfwrite:
        gfwrite.write(my_group)

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
    for c in api4_client.linode.instances(linode_api4.Instance.group == my_group):
        print('%s label %s' % (c, c.label))

    print('')
    print('currently existing volumes:')
    my_volumes = [ v for v in api4_client.volumes() if str(v).startswith(my_group) ]
    for v in my_volumes:
        print('%s size %d region %s linode %s' % (
            v.label, v.size, v.region, v.linode_id))
    print('')
    sys.stdout.flush()

    try:
        selected_region = CLUSTER['region'].lower()
    except KeyError:
        selected_region = prm_region.lower()

    regions = api4_client.regions()
    region = None
    for r in regions:
        if str(r).lower().__contains__(selected_region.lower()):
            region = r
            break
    if not region:
        logging.error('selected region %s does not match available regions' % selected_region)
        sys.exit(NOTOK)
    logging.info('region is %s' % region)

    try:
        selected_image = CLUSTER['image']
    except KeyError:
        selected_image = prm_image
    logging.info('image is %s' % selected_image)

    types = api4_client.linode.types()
    new_linodes = {}
    try:
        roles_in_cluster_json = CLUSTER['roles']
    except KeyError:
        logging.error('syntax for cluster.json has changed, see new sample file')

    for c in roles_in_cluster_json:
        plan = c['plan']
        count = c['count']
        prefix = c['prefix']
        ansible_role = prefix + 's'

        if prefix == 'osd':
            try:
                osds_per_host = c['osds-per-host']
            except KeyError:
                osds_per_host = prm_osds_per_host
            try:
                osd_size = c['osd-size-GB']
            except KeyError:
                osd_size = prm_osd_size_GB

        for t in types:
            if str(t).lower().__contains__(plan.lower()):
                vmtype = t
                break
        for host in range(0, count):
            next_label= '%s_%s%03d' % (my_group, prefix, host)
            logging.debug('creating vm %s type %s group %s image %s' % (
                            next_label, vmtype, my_group, prm_image))
            try:
                new_linode, password = api4_client.linode.instance_create(
                    vmtype,
                    region,
                    label=next_label,
                    group=my_group,
                    image=selected_image,
                    authorized_keys = ssh_public_key_filename)
            except linode_api4.errors.ApiError as e:
                if str(e).__contains__('must be unique'):
                    logging.warn('duplicate label %s detected, continuing anyway' % next_label)
                    continue
                else:
                    raise e
            ipv6addr = new_linode.ipv6.split('/')[0]
            label = new_linode.label
            new_linodes[str(new_linode)] = (vmtype, prefix, ipv6addr, region, password)
            logging.info('%s, %s, %s, %s' % (new_linode, ipv6addr, prefix, vmtype))
            if prefix == 'osd':
                for dev in range(0, prm_osds_per_host):
                    volname = '%s_%s%03d_v%02d' % (my_group, prefix, host, dev)
                    logging.debug('creating vol %s size %s region %s' % (volname, osd_size, region))
                    new_vol = api4_client.volume_create(
                                volname,
                                size=osd_size,
                                region=region)
                    new_vol.attach(new_linode)
                    logging.info('attached volume %s to instance %s' % (new_vol, new_linode))

    with open("ansible_inventory", mode = 'w') as f:
        ansible_roles = set()
        for inst in new_linodes.keys():
            (_, prefix, _, _, _) = new_linodes[inst]
            ansible_roles.add(prefix)
        for next_prefix in ansible_roles:
            f.write('\n')
            f.write('[' + next_prefix + 's]\n')
            for inst in new_linodes.keys():
                (ty, prefix, ip, rg, pw) = new_linodes[inst]
                if prefix == next_prefix:
                    f.write(ip + '\n')

def main():
    token_fn = os.getenv("LINODE_API_KEY")
    if token_fn is None:
        raise RuntimeError("please specify Linode API token filename")
    with open(token_fn, 'r') as tf:
        token = tf.readline().strip()
    client = linode_api4.LinodeClient(token)
    launch(client)

if __name__ == "__main__":
    main()
