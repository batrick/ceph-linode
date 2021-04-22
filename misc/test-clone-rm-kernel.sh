#!/bin/bash

set -ex

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

function main {
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
    if [ "$DISTRIBUTED" ]; then
        setfattr -n ceph.dir.pin.distributed -v 1 .
    fi
    for ((i = 0; i < COUNT; ++i)); do
        (do_clone_rm_kernel "$i") &> /root/client-output-$i.txt &
    done
    wait
    popd
}

ARGUMENTS='--options d,h,p: --long distributed,help,pin:'
NEW_ARGUMENTS=$(getopt $ARGUMENTS -- "$@")
eval set -- "$NEW_ARGUMENTS"

function usage {
    printf "%s: [--distributed|--pin=<max_mds>] <count>\n" "$0"
}

while [ "$#" -ge 0 ]; do
    case "$1" in
        -d|--distributed)
            DISTRIBUTED=1
            shift
            ;;
        -h|--help)
            usage
            exit
            ;;
        -p|--pin)
            shift
            PIN=1
            MAX_MDS="$1"
            shift
            ;;
        --)
            shift
            break
            ;;
    esac
done

COUNT="$1"
shift

main |& tee client-output.txt
