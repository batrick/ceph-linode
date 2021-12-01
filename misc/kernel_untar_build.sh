#!/bin/bash

set -e

N="$1"
if [ -z "$N" ]; then
    N=1
fi

function do_kernel_build {
    T=$(mktemp -d -p .)
    (
        cd "$T"

        tar xzvf "$LINUX"
        cd linux*
        make defconfig
        n="$(nproc)"
        make -j$((n+1))
    )

    rm -rfv "$T"
}

function main {
    count=0
    while true; do
        if systemctl status ceph-fuse@-perf || [ "$(stat -f --format=%t /perf)" = c36400 ]; then
            break # shell ! is stupid, can't move to while
        fi
        sleep 5
        if ((++count > 60)); then
            exit 1
        fi
    done

    wget -q http://download.ceph.com/qa/linux-5.4.tar.gz
    LINUX=$(realpath linux-5.4.tar.gz)

    mkdir -p /perf/kernels
    pushd /perf/kernels
    if [ "$DISTRIBUTED" ]; then
        setfattr -n ceph.dir.pin.distributed -v 1 .
    fi
    for ((i = 0; i < COUNT; ++i)); do
        (do_kernel_build "$i") &> /root/client-output-$i.txt &
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
