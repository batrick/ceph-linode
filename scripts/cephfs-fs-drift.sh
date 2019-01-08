#!/bin/bash

set -e

# client-000 is used to run fs-drift master
#clients=$(< linodes jq --raw-output 'map(select(.name | startswith("client"))) | map(select(.name != "client-000")) | map(.name) | join(",")')
MAX_MDS=$(< linodes jq --raw-output 'map(select(.name | startswith("mds"))) | length')
MAX_MDS=$((MAX_MDS-1)) # leave one for standby
MAX_MDS=1
NUM_CLIENTS=$(< linodes jq --raw-output 'map(select(.name | startswith("client"))) | map(select(.name != "client-000")) | length')

common_params="--max-files 1000000 --threads 1 --dirs-per-level 50 --duration 60"

if [ -r fs-drift.sh ]; then
  source fs-drift.sh
fi

###

# may be necessary for ansible with >25 forks
ulimit -n 65536 || true

LOG=$(date +OUTPUT-%Y%m%d-%H:%M)
EXPERIMENT=$(date +experiment-%Y%m%d-%H:%M)
RESULTS=/results/

source ansible-env.bash

function run {
  printf '%s\n' "$*"
  "$@"
}

function ssh {
  /usr/bin/ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o PreferredAuthentications=publickey "$@"
}

function scp {
  /usr/bin/scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o PreferredAuthentications=publickey "$@"
}

function nclients {
  n="$1"
  for ((i = 1; i <= n; i++)); do
    if [[ $i > 1 ]]; then
      printf ,
    fi
    printf "client-%03d" "$i"
  done
}

function fsdrift {
  clients="$1"
  shift
  run ssh client-000 "mkdir -p /cephfs/fs-drift && fs-drift/fs-drift.py --top /cephfs/fs-drift --host-set $clients --output-json /root/fs-drift.json $common_params $*"
}

function save {
  #run ssh client-000 "cd /cephfs/network_shared/ && tar czf rsptimes.tar.gz rsptimes*csv"
  #run scp client-000:/cephfs/network_shared/rsptimes.tar.gz "$1/fs-drift/"
  run scp client-000:/root/fs-drift.json "$1/fs-drift/"
}

function do_fsdrift {
  exp="$1"
  i="$2"
  max_mds="$3"
  num_clients="$4"

  instance="$(printf 'max_mds:%02d/num_clients:%02d/i:%02d/%s' "$max_mds" "$num_clients" "$i")"
  dir="${exp}/results/${instance}"
  run mkdir -p "$dir/fs-drift"
  printf '%d\n' "$i" > "$dir"/i
  printf '%d\n' "$max_mds" > "$dir"/max_mds
  printf '%d\n' "$num_clients" > "$dir"/num_clients
  printf '%s\n' "$instance" > "$dir"/instance
  printf '%s\n' "$(date +%Y%m%d-%H:%M)" > "$dir"/date
  run do_playbook playbooks/cephfs-pre-test.yml

  run ans -m shell -a 'df -h /cephfs/' clients &> "$dir"/fs-drift/pre-df
  date +%s > "$dir"/fs-drift/start
  run fsdrift "$(nclients "$num_clients")" |& tee "$dir"/fs-drift/log
  date +%s > "$dir"/fs-drift/end
  run ans -m shell -a 'df -h /cephfs/' clients &> "$dir"/fs-drift/post-df

  run do_playbook --extra-vars instance="$dir" playbooks/cephfs-post-test.yml
  run save "$dir"
}

function main {
  exp="${RESULTS}/${EXPERIMENT}"
  mkdir -p -- "$exp"

  run cp -av -- launch.log ansible_inventory linodes cluster.json group_vars "$exp/"

  {
    run do_playbook playbooks/cephfs-setup.yml
    run do_playbook playbooks/cephfs-setup-fs-drift.yml
    for ((max_mds = 1; max_mds <= MAX_MDS; ++max_mds)); do
      num_clients="$NUM_CLIENTS"
      for ((i = 0; i < 2; i++)); do
        run do_playbook playbooks/cephfs-reset.yml
        ans -m shell -a "ceph fs set cephfs max_mds $max_mds" mon-000
        run do_fsdrift "$exp" "$i" "$max_mds" "$num_clients" || true
      done
    done
  } |& tee "${exp}/experiment.log"
}

ARGUMENTS='--options e:,h,l:,r: --long experiment:,help,results:'
NEW_ARGUMENTS=$(getopt $ARGUMENTS -- "$@")
eval set -- "$NEW_ARGUMENTS"

function usage {
    printf "%s: [--experiment <experiment>]\n" "$0"
}

while [ "$#" -ge 0 ]; do
    case "$1" in
        -e|--experiment)
            shift
            EXPERIMENT="$1"
            shift
            ;;
        -h|--help)
            usage
            exit
            ;;
        --metadata-pg)
            shift
            METADATA_PG="$1"
            shift
            ;;
        --data-pg)
            shift
            DATA_PG="$1"
            shift
            ;;
        -r|--results)
            shift
            RESULTS="$1"
            shift
            ;;
        --)
            shift
            break
            ;;
    esac
done

main "$@"
