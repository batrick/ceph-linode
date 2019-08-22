import json
import logging
import os
from os.path import expanduser

import linode.api as linapi

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

with open("LINODE_GROUP") as f:
    GROUP = unicode(f.read().strip())

def main():
    key = os.getenv("LINODE_API_KEY")
    if key is None:
        try:
            with open(expanduser("~/.linode.key")) as f:
                key = str(f.read().strip())
        except:
            raise RuntimeError("please specify Linode API key")

    client = linapi.Api(key = key, batching = False)

    linodes = client.linode_list()
    linodes = filter(lambda l: l[u'LPM_DISPLAYGROUP'] == GROUP, linodes)
    print(json.dumps(linodes))

if __name__ == "__main__":
    main()
