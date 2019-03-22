import binascii
import logging
import os
import time

from linode_api4 import LinodeClient

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

with open("LINODE_GROUP") as f:
    GROUP = unicode(f.read().strip())

def wait(key):
    client = LinodeClient(key)

    notdone = True
    while notdone:
        linodes = client.linode.instances()
        print(linodes)
        notdone = False
        for linode in linodes:
            if linode.group == GROUP:
                if linode.status != "running":
                    notdone = True
        time.sleep(5)

def main():
    key = os.getenv("LINODE_API_KEY")
    if key is None:
        raise RuntimeError("please specify Linode API key")

    wait(key)

if __name__ == "__main__":
    main()
