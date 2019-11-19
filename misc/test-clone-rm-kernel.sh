#!/bin/bash

set -ex

N="$1"
if [ -z "$N" ]; then
    exit 1
fi

MAX_MDS="$2"

function do_clone_rm_kernel {
    local c="$1"
    local T="$(mktemp -d -p "." test.XXXXXX)"
    pushd "$T"
    if [ -n "$MAX_MDS" ]; then
        setfattr -n ceph.dir.pin -v $(( RANDOM % MAX_MDS )) .
    fi
    # pick a random linux clone (not bootstrap)
    stat /cephfs/sources
    local source="$(find /cephfs/sources -maxdepth 1 -print0 | sort -z -R | sed -z '1q')"
    date '+%s' > "/root/client-$c-start.time.txt"
    git clone "file://$source" linux
    date '+%s' > "/root/client-$c-mid.time.txt"
    rm -rf linux
    date '+%s' > "/root/client-$c-end.time.txt"
    popd
    rmdir "$T"
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

    mkdir -p /cephfs/destinations
    pushd /cephfs/destinations
    for ((i = 0; i < N; ++i)); do
        (do_clone_rm_kernel "$i") &> /root/client-output-$i.txt &
    done
    wait
    popd
} > /root/client-output.txt 2>&1
