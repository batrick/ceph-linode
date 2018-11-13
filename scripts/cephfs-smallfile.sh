#!/bin/bash

set -e

# client-000 is used to run smallfile master
#clients=$(< linodes jq --raw-output 'map(select(.name | startswith("client"))) | map(select(.name != "client-000")) | map(.name) | join(",")')
MAX_MDS=$(< linodes jq --raw-output 'map(select(.name | startswith("mds"))) | length')
MAX_MDS=$((MAX_MDS-1)) # leave one for standby
NUM_CLIENTS=$(< linodes jq --raw-output 'map(select(.name | startswith("client"))) | map(select(.name != "client-000")) | length')

common_params="--same-dir N --response-times y --threads 16 --pause 2000 --files 1000 --hash-into-dirs Y --dirs-per-dir 3 --files-per-dir 1000 --file-size 4"
oplist="create overwrite append read symlink stat mkdir rmdir chmod setxattr getxattr ls-l rename delete-renamed"

if [ -r smf.sh ]; then
  source smf.sh
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

function smallfile {
  clients="$1"
  shift
  run ssh client-000 "smallfile/smallfile_cli.py --top /cephfs/ --host-set $clients --output-json /root/smf.json $common_params $*"
}

function save {
  run ssh client-000 "cd /cephfs/network_shared/ && tar czf rsptimes.tar.gz rsptimes*csv"
  run scp client-000:/cephfs/network_shared/rsptimes.tar.gz "$1/smf/"
  run scp client-000:/root/smf.json "$1/smf/"
}

function do_smallfile {
  exp="$1"
  i="$2"
  max_mds="$3"
  num_clients="$4"
  for op in $oplist; do
    instance="$(printf 'max_mds:%02d/num_clients:%02d/i:%02d/%s' "$max_mds" "$num_clients" "$i" "$op")"
    dir="${exp}/results/${instance}"
    run mkdir -p "$dir/smf"
    printf '%d\n' "$i" > "$dir"/i
    printf '%d\n' "$max_mds" > "$dir"/max_mds
    printf '%d\n' "$num_clients" > "$dir"/num_clients
    printf '%s\n' "$instance" > "$dir"/instance
    printf '%s\n' "$(date +%Y%m%d-%H:%M)" > "$dir"/date
    run do_playbook playbooks/cephfs-pre-test.yml

    run ans -m shell -a 'df -h /cephfs/' clients &> "$dir"/smf/pre-df
    date +%s > "$dir"/smf/start
    run smallfile "$(nclients "$num_clients")" --operation "$op" |& tee "$dir"/smf/log
    date +%s > "$dir"/smf/end
    run ans -m shell -a 'df -h /cephfs/' clients &> "$dir"/smf/post-df

    run do_playbook --extra-vars instance="$dir" playbooks/cephfs-post-test.yml
    run save "$dir"
  done

  run smallfile "$clients" --operation cleanup
}

function main {
  exp="${RESULTS}/${EXPERIMENT}"
  mkdir -p -- "$exp"

  run cp -av -- launch.log ansible_inventory linodes cluster.json group_vars "$exp/"

  {
    run do_playbook playbooks/cephfs-setup.yml
    for ((max_mds = 1; max_mds <= MAX_MDS; ++max_mds)); do
      for ((num_clients = 1; num_clients < NUM_CLIENTS; num_clients*=2)); do
        if [[ $max_mds == 1 && $num_clients > 4 ]]; then
          break
        fi
        for ((i = 0; i < 2; i++)); do
          run do_playbook playbooks/cephfs-reset.yml
          ans -m shell -a "ceph fs set cephfs max_mds $max_mds" mon-000
          run do_smallfile "$exp" "$i" "$max_mds" "$num_clients" || true
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
