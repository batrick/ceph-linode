#!/bin/bash

set -e

ephemeral_distributed="$1"
rm_dir="$2"

N="$3"
if [ -z "$N" ]; then
    N=1 
fi


function do_scale_test {
    TESTDIR="/cephfs/"
    mkdir -p "$TESTDIR"
    T=$(mktemp -d -p "$TESTDIR")
    cd "$T"
    # Avoiding directory fragmentation for now, hence creating a new parent directory
    # after every 9998 child directories
    for ((i = 0; i < 100; ++i)); do
      mkdir "$i"
      if [ "$ephemeral_distributed" == "--ephemeral-distributed" ]; then
          setfattr -n ceph.dir.distributed.pin -v 1 $i
      fi
      for ((j = 0; j < 9998; ++j)); do
        mkdir "$i/$j"
      done
    done
    if [ "$rm_dir" == "--remove-dir" ]; then
      rm -rfv "$T"
    fi
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
        do_scale_test &> /root/client-output-$i.txt &
    done
    wait
} > /root/client-output.txt 2>&1
