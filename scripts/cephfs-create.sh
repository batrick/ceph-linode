#!/bin/bash

set -e

MAX_MDS=$(< linodes jq --raw-output 'map(select(.label | startswith("mds"))) | length')
MAX_MDS=$((MAX_MDS-1)) # leave one for standby
NUM_CLIENTS=$(< linodes jq --raw-output 'map(select(.label | startswith("client"))) | length')

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
      printf ' '
    fi
    printf "client-%03d" "$((i-1))"
  done
}

function do_test {
  run ans -m shell -a 'chdir=/root /root/creats.sh --distributed 16 10000' "$1"
}

function do_tests {
  exp="$1"
  i="$2"
  max_mds="$3"
  num_clients="$4"
  instance="$(printf 'max_mds:%02d/num_clients:%02d/i:%02d/%s' "$max_mds" "$num_clients" "$i" "$size")"
  dir="${exp}/results/${instance}"
  run mkdir -p "$dir/"
  printf '%d\n' "$i" > "$dir"/i
  printf '%d\n' "$max_mds" > "$dir"/max_mds
  printf '%d\n' "$num_clients" > "$dir"/num_clients
  printf '%s\n' "$instance" > "$dir"/instance
  printf '%s\n' "$(date +%Y%m%d-%H:%M)" > "$dir"/date
  run do_playbook playbooks/cephfs-pre-test.yml

  run ans -m shell -a 'df -h /cephfs/' clients &> "$dir/pre-df"
  date +%s > "$dir/start"
  run do_test "$(nclients "$num_clients")" |& tee "$dir/log"
  date +%s > "$dir/end"
  run ans -m shell -a 'df -h /cephfs/' clients &> "$dir/post-df"

  run do_playbook --extra-vars instance="$dir" playbooks/cephfs-post-test.yml
}

function main {
  exp="${RESULTS}/${EXPERIMENT}"
  mkdir -p -- "$exp"

  run cp -av -- ansible_inventory linodes cluster.json "$exp/"

  {
    run do_playbook playbooks/cephfs-setup.yml
    run ans --module-name=copy --args="src=misc/creats.sh dest=/root/ owner=root group=root mode=755" clients
    run ans --module-name=copy --args="src=misc/creats.c dest=/root/ owner=root group=root mode=755" clients
    for ((max_mds = 2; max_mds <= MAX_MDS; ++max_mds)); do
      for ((num_clients = 4; num_clients <= NUM_CLIENTS; num_clients*=2)); do
        for ((i = 0; i < 2; i++)); do
          run do_playbook playbooks/cephfs-reset.yml
          ans -m shell -a "ceph fs set cephfs max_mds $max_mds" mon-000
          run do_tests "$exp" "$i" "$max_mds" "$num_clients" || true
        done
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
