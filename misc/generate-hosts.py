#!/usr/bin/python3

# script to generate an /etc/hosts file with ip addrs
# and role-based hostnames for linodes
#
# sys.argv[1] - linodes json generated via linode.py

from collections import defaultdict
import json
import sys

with open(sys.argv[1]) as f:
    LINODES = json.load(f)

groups = defaultdict(list)
for l in LINODES:
    line = f"{l['ip_private']} {l['label']}"
    groups[l['ceph_group']].append(line)

for group in sorted(groups.keys()):
    for line in sorted(groups[group], key=lambda line: line.split()[1]):
        print(line)
