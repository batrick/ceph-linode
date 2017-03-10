import binascii
import logging
import os
import time

import linode.api as linapi

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

with open("LINODE_GROUP") as f:
    GROUP = unicode(f.read())

def wait(key):
    client = linapi.Api(key = key, batching = False)

    notdone = True
    while notdone:
        linodes = client.linode_list()
        print(linodes)
        notdone = False
        for linode in linodes:
            if linode[u'LPM_DISPLAYGROUP'] == GROUP:
                if linode[u'STATUS'] != 1:
                    notdone = True
        time.sleep(5)

def main():
    key = os.getenv("LINODE_API_KEY")
    if key is None:
        raise RuntimeError("please specify Linode API key")

    wait(key)

if __name__ == "__main__":
    main()
