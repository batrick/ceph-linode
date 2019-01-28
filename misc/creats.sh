#!/bin/bash

set -ex

{
    count=0
    while ! systemctl status ceph-fuse@-mnt; do
        sleep 5
        if ((++count > 60)); then
            exit 1
        fi
    done

    gcc -o /creats /creats.c
    /creats "$@"
} > /root/client-output.txt 2>&1
