#!/bin/bash

set -e

function bootstrap_clone_kernel {
  git clone -b v4.3 git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git
}

{
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

    pushd /perf
    bootstrap_clone_kernel
} > /root/client-output.txt 2>&1
