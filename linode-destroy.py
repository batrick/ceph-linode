#!/usr/bin/env python
import logging
import os
import sys
import time
import socket
import errno
import linode_api4

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def main():
    token_fn = os.getenv("LINODE_API_KEY")
    if token_fn is None:
        raise RuntimeError("please specify Linode API token file")
    with open(token_fn, 'r') as tf:
        token = tf.readline().strip()

    try:
        with open('LINODE_GROUP', 'r') as gf:
            my_group = gf.readline().strip()
    except FileNotFoundError:
        print('no LINODE_GROUP file found so we cannot determine which linodes belong to you')
        sys.exit(1)

    # get my ipv6 addr, there should be only 1
    addrinfo = socket.getaddrinfo(socket.gethostname(), 8765)[0]
    (_, _, _, _, a) = addrinfo
    (ipv6addr, _, _, _) = a
    logging.info('my ipv6addr = %s, dont delete this one' % ipv6addr)
    client = linode_api4.LinodeClient(token)
    instances = client.linode.instances(linode_api4.Instance.group == my_group)
    for c in instances:
        next_ipv6addr = c.ipv6.split('/')[0]
        if next_ipv6addr != ipv6addr:
            logging.info("deleting linode %s" % str(c))
            c.delete()

    volumes = client.volumes()
    filtered_volumes = [ v for v in volumes if v.label.startswith(my_group) ]
    retry_list = filtered_volumes [:]
    remaining_list = filtered_volumes[:]
    while len(retry_list) > 0:
        for k, v in enumerate(retry_list):
            logging.info("trying to delete volume %s"  % str(v))
            try:
                v.delete()
                remaining_list.remove(v)
            except linode_api4.errors.ApiError as e:
                logging.error(str(e))
                logging.info('probably instance is not shut down yet, pausing 5 sec')
                time.sleep(5)
        retry_list = remaining_list[:]

    retry_list = filtered_volumes[:]
    remaining_list = retry_list[:]
    while len(retry_list) > 0:
        for k, v in enumerate(retry_list):
            logging.info('verifying that volume %s has gone away' % str(v))
            try:
                status = v.status
            except linode_api4.errors.ApiError as e:
                exception_text = str(e).lower()
                if exception_text.__contains__('not found'):
                    remaining_list.remove(v)
                else:
                    raise e
        time.sleep(5)
        retry_list = remaining_list[:]

    # since instances are deleted, inventory file is worthless

    try:
        os.unlink('ansible_inventory')
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise e
    logging.info('all instances and volumes for linode group %s deleted' % my_group)

if __name__ == "__main__":
    main()
