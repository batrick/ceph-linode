import json
import logging
import os

from linode_api4 import LinodeClient

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

with open("LINODE_GROUP") as f:
    GROUP = unicode(f.read().strip())

def main():
    key = os.getenv("LINODE_API_KEY")
    if key is None:
        raise RuntimeError("please specify Linode API key")

    client = LinodeClient(key)

    linodes = client.linode.instances()
    linodes = filter(lambda l: l.group == GROUP, linodes)
    for linode in linodes:
        print(linode.label)

if __name__ == "__main__":
    main()
