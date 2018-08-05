#!/usr/bin/env python

# script to generate an /etc/hosts file with ipv6 addrs
# for linodes.   This is a workaround for the fact that
# certain utilities are syntactically allergic 
# to addresses with ":" in them.
#
# sys.argv[1] - ansible inventory file generated by linode-launch.py

import sys, ipaddress

with open(sys.argv[1], 'r') as f:
    lines = [ l.strip() for l in f.readlines() ]

groups = {}
for l in lines:
    if l == '':
        pass
    elif l.startswith('[') and l.endswith(']'):
        group_nm = l.split('[')[1].split(']')[0][:-1]
        groups[group_nm] = []
    elif l.__contains__(':'):
        a = ipaddress.ip_address(l)
        if isinstance(a, ipaddress.IPv6Address):
            groups[group_nm].append(str(a))

for g in groups.keys():
    for k, a in enumerate(groups[g]):
        print('%s %s%d' % (str(a), g, k))
