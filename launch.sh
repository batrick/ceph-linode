#!/bin/bash

set -ex

# may be necessary for ansible with >25 forks
ulimit -n 65536 || true

source "$(dirname "$0")/ansible-env.bash"

CEPH_ANSIBLE=~/ceph-ansible/
NUKE=0
DESTROY=0
LOG=OUTPUT
YML="$(dirname "$0")/linode.yml"
RETRY="${YML%.*}.retry"

function main {
    if [ "$DESTROY" -gt 0 ]; then
        time python2 "$(dirname "$0")/linode-destroy.py"
    elif [ "$NUKE" -gt 0 -o ! -f ansible_inventory ]; then
        time python2 "$(dirname "$0")/linode-nuke.py"
    fi
    if [ "$NUKE" -gt 0 -o "$DESTROY" -gt 0 -o ! -f ansible_inventory ]; then
        time python2 "$(dirname "$0")/linode-launch.py"
    fi
    # wait for Linodes to finish booting
    time python2 "$(dirname "$0")/linode-wait.py"
    sleep 5

    do_playbook "$(dirname "$0")/pre-config.yml"

    cp $ANSIBLE_INVENTORY $CEPH_ANSIBLE
    cd $CEPH_ANSIBLE
    do_playbook site.yml.sample
}

ARGUMENTS='--options c:,h,n,d,l: --long ceph-ansible:,help,nuke,log:'
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
        -d|--destroy)
            DESTROY=1
            shift
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
forks = 25
action_plugins = ${CEPH_ANSIBLE}/plugins/actions
library = ${CEPH_ANSIBLE}/library
roles_path = ${CEPH_ANSIBLE}/roles
EOF

main |& tee -a "$LOG"
