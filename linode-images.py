#!/usr/bin/env python
# print out ids of images supported by linode
# cli parameter 1 - optional, specifies string to match images against
import os
import sys
import linode_api4

token_fn = os.getenv("LINODE_API_KEY")
if token_fn is None:
    raise RuntimeError("please specify Linode API token filename in LINODE_API_KEY env. var.")
with open(token_fn, 'r') as tf:
    token = tf.readline().strip()
client = linode_api4.LinodeClient(token)
selection = sys.argv[1] if len(sys.argv) > 1 else ''
for im in client.images():
    if im.id.lower().__contains__(selection.lower()):
        print(im.id)
