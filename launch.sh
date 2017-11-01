#!/bin/bash

set -ex

# may be necessary for ansible with >25 forks
ulimit -n 65536 || true

source "$(dirname "$0")/ansible-env.bash"

CEPH_ANSIBLE=~/ceph-ansible/
NUKE=0
LOG=OUTPUT
YML="$(dirname "$0")/linode.yml"
RETRY="${YML%.*}.retry"

function main {
    if [ "$NUKE" -gt 0 ]; then
        time python2 "$(dirname "$0")/linode-nuke.py"
    fi
    if [ "$NUKE" -gt 0 -o ! -f ansible_inventory ]; then
        time python2 "$(dirname "$0")/linode-launch.py"
    fi
    # wait for Linodes to finish booting
    time python2 "$(dirname "$0")/linode-wait.py"

    do_playbook --limit=all "$(dirname "$0")/pre-config.yml"

    if [ "$NUKE" -gt 0 ]; then
        # /dev/sdc is sometimes not wiped after linode-nuke.py
        # (Linode wipes deleted disks on a schedule rather than immediately.)
        ans --module-name=shell --args='wipefs -a /dev/sdc' osds
    fi

    # Sometimes we hit transient errors, so retry until it works!
    if ! do_playbook --limit=all "$YML"; then
        # Always include the mons because we need their statistics to generate ceph.conf
        printf 'mons\nmgrs\n' >> "$RETRY"
        do_playbook --limit=@"${RETRY}" "$YML"
        rm -f -- "${RETRY}"
    fi
}

ARGUMENTS='--options c:,h,n,l: --long ceph-ansible:,help,nuke,log:'
NEW_ARGUMENTS=$(getopt $ARGUMENTS -- "$@")
eval set -- "$NEW_ARGUMENTS"

function usage {
    printf "%s: [--ceph-ansible path] [--nuke] [--log path]\n" "$0"
}

while [ "$#" -ge 0 ]; do
    case "$1" in
        -c|--ceph-ansible)
            shift
            CEPH_ANSIBLE="$1"
            shift
            ;;
        -h|--help)
            usage
            exit
            ;;
        -n|--nuke)
            NUKE=1
            shift
            ;;
        -l|--log)
            shift
            LOG="$1"
            shift
            ;;
        --)
            shift
            break
            ;;
    esac
done
export CEPH_ANSIBLE

if [ -z "$LINODE_API_KEY" ]; then
    printf "Specify the Linode API key using the LINODE_API_KEY environment variable.\n"
    exit 1
fi

if ! [ -d "$CEPH_ANSIBLE"/roles ]; then
    printf "Cannot find ceph-ansible environment, please specify the path to ceph-ansible. (current: %s)\n" "$CEPH_ANSIBLE"
    exit 1
fi

cat > ansible.cfg <<EOF
# Managed by launch.sh, do not modify!
[defaults]
action_plugins = ${CEPH_ANSIBLE}/plugins/actions
library = ${CEPH_ANSIBLE}/library
roles_path = ${CEPH_ANSIBLE}/roles
EOF

main |& tee -a "$LOG"
