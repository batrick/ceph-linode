#!/usr/bin/env python
import binascii
import logging
import sys
import os
import time
import subprocess
import linode_api4

homedir = os.getenv('HOME')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def wait(token, my_group):
    client = linode_api4.LinodeClient(token)
    linodes = [ l for l in client.linode.instances(linode_api4.Instance.group == my_group) ]

    linodes_not_up = linodes[:]
    while len(linodes) > 0:
        for l in linodes:
            ipv6addr = l.ipv6.split('/')[0]
            logging.info('see if %s is up' % ipv6addr)
            try:
                output = subprocess.check_output(['ssh', '-o StrictHostKeyChecking=no', '-6', ipv6addr, 'pwd'])
                if not str(output).__contains__(homedir):
                    logging.warn('failed to reach %s' % ipv6addr)
                else:
                    linodes_not_up.remove(l)
            except subprocess.CalledProcessError as e:
                logging.warn(str(e))
        logging.info('waiting 2 seconds before retrying')
        if len(linodes_not_up) > 0:
            time.sleep(2)
        linodes = linodes_not_up[:]

def main():
    tokenfn = os.getenv("LINODE_API_KEY")
    if tokenfn is None:
        raise RuntimeError("please specify Linode API token filename")
    with open(tokenfn, 'r') as kf:
        token = kf.readline().strip()

    try:
        with open('LINODE_GROUP', 'r') as gf:
            my_group = gf.readline().strip()
    except FileNotFoundError:
        print('no LINODE_GROUP file defined, so nothing to wait for')
        sys.exit(0)

    wait(token, my_group)

if __name__ == "__main__":
    main()
