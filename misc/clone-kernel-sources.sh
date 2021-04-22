#!/bin/bash

set -e

function do_clone_kernel {
    pushd "$(mktemp -d -p "." linux.XXXXXX)"
    if [ "$PIN" -a -n "$MAX_MDS" ]; then
        setfattr -n ceph.dir.pin -v $(( RANDOM % MAX_MDS )) .
    fi
    git clone "file://$(realpath /cephfs/linux/.git)" "."
    setfattr -n ceph.dir.pin -v -1 .
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
        (do_clone_kernel "$i") &> /root/client-output-$i.txt &
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
