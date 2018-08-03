#!/usr/bin/env python
import binascii
import logging
import os
import time
import subprocess
import linode_api4

homedir = os.getenv('HOME')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def wait(keyfn):
    with open(keyfn, 'r') as kf:
        key = kf.readline().strip()
    client = linode_api4.LinodeClient(key)
    linodes = [ l for l in client.linode.instances() ]

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
    key = os.getenv("LINODE_API_KEY")
    if key is None:
        raise RuntimeError("please specify Linode API key")

    wait(key)

if __name__ == "__main__":
    main()
