#!/bin/bash

set -e

N="$1"
if [ -z "$N" ]; then
    N=1
fi

function do_kernel_build {
    T=$(mktemp -d -p /cephfs)
    (
        cd "$T"
        wget -q http://download.ceph.com/qa/linux-4.0.5.tar.xz

        tar Jxvf linux*.xz
        cd linux*
        make defconfig
        make
    )

    rm -rfv "$T"
}

{
    count=0
    while true; do
        if systemctl status ceph-fuse@-cephfs || [ "$(stat -f --format=%t /cephfs)" = c36400 ]; then
            break # shell ! is stupid, can't move to while
        fi
        sleep 5
        if ((++count > 60)); then
            exit 1
        fi
    done

    for ((i = 0; i < N; ++i)); do
        do_kernel_build &> /root/client-output-$i.txt &
    done
    wait
} > /root/client-output.txt 2>&1
