#!/usr/bin/env python
# print out ids of regions supported by linode
# cli parameter 1 - optional, specifies string to match regions against
import os
import sys
import linode_api4

token_fn = os.getenv("LINODE_API_KEY")
if token_fn is None:
    raise RuntimeError("please specify Linode API token filename")
with open(token_fn, 'r') as tf:
    token = tf.readline().strip()
client = linode_api4.LinodeClient(token)
selection = sys.argv[1] if len(sys.argv) > 1 else ''
for r in client.regions():
    if r.id.lower().__contains__(selection.lower()):
        print(r.id)
