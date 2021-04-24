#!/bin/bash

set -ex

function wait_for_mount {
    local count=0
    while true; do
        if systemctl status ceph-fuse@-cephfs || [ "$(stat -f --format=%t /cephfs)" = c36400 ]; then
            break # shell ! is stupid, can't move to while
        fi
        sleep 5
        if ((++count > 60)); then
            exit 1
        fi
    done
}

function do_creats {
    T=$(mktemp -d -p .)
    (
        cd "$T"
        /root/creats "$T" "$NFILES"
    )
}

function main {
    gcc -o /root/creats /root/creats.c

    mkdir -p /cephfs/creats
    pushd /cephfs/creats
    if [ "$DISTRIBUTED" ]; then
        setfattr -n ceph.dir.pin.distributed -v 1 .
    fi
    for ((i = 0; i < NCREATS; ++i)); do
        (do_creats "$i") &> /root/client-output-$i.txt &
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

NCREATS="$1"
if [ -z "$NCREATS" ]; then
    NCREATS=1
else
    shift
fi

NFILES="$1"
if [ -z "$NFILES" ]; then
    NFILES=1000000
else
    shift
fi

main |& tee client-output.txt
