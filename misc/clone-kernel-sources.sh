#!/bin/bash

set -e

N="$1"
if [ -z "$N" ]; then
    N=1
fi

MAX_MDS="$2"

function do_clone_kernel {
    pushd "$(mktemp -d -p "." linux.XXXXXX)"
    if [ -n "$MAX_MDS" ]; then
        setfattr -n ceph.dir.pin -v $(( RANDOM % MAX_MDS )) .
    fi
    git clone "file://$(realpath /cephfs/linux/.git)" "."
    setfattr -n ceph.dir.pin -v -1 .
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

    mkdir -p /cephfs/sources
    pushd /cephfs/sources
    for ((i = 0; i < N; ++i)); do
        (do_clone_kernel "$i") &> /root/client-output-$i.txt &
    done
    wait
    popd
} > /root/client-output.txt 2>&1
