#!/usr/bin/env python
import logging
import os
import time
import socket
import errno
import linode_api4

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

def main():
    token_fn = os.getenv("LINODE_API_TOKEN")
    if token_fn is None:
        raise RuntimeError("please specify Linode API token file")
    with open(token_fn, 'r') as tf:
        token = tf.readline().strip()

    # get my ipv6 addr, there should be only 1
    addrinfo = socket.getaddrinfo(socket.gethostname(), 8765)[0]
    (_, _, _, _, a) = addrinfo
    (ipv6addr, _, _, _) = a
    print('my ipv6addr = %s, dont delete this one' % ipv6addr)
    client = linode_api4.LinodeClient(token)
    instances = client.linode.instances()
    for c in instances[1:]:
        next_ipv6addr = c.ipv6.split('/')[0]
        if next_ipv6addr != ipv6addr:
            logging.info("deleting linode %s" % str(c))
            c.delete()

    volumes = client.volumes()
    retry_list = volumes[:]
    while len(retry_list) > 0:
        for k, v in enumerate(retry_list):
            logging.info("trying to delete volume %s"  % str(v))
            try:
                v.delete()
                retry_list.remove(v)
            except linode_api4.errors.ApiError as e:
                logging.error(str(e))
                logging.info('probably instance is not shut down yet, pausing 5 sec')
                time.sleep(5)
    try:
        os.unlink('ansible_inventory')
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise e

if __name__ == "__main__":
    main()
