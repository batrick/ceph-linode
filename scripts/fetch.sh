#!/bin/bash

MAX_JOBS=15

function run {
    printf '%s\n' "$*" > /dev/tty
    "$@"
}

function queue_task {
    jobs -p -r
    while [ "$(jobs -p -r | wc -w)" -ge "$MAX_JOBS" ]; do
        # Can't use `wait` because it waits for ALL jobs to finish.
        sleep 0.5
    done
    run "$@" &
}

function get {
    run scp -i ~/ansible.id_rsa -o PreferredAuthentications=publickey -o ConnectTimeout=60 -o ConnectionAttempts=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$@"
}

function fetch_host {
    #         ceph-osd-14 ansible_ssh_host=50.116.48.233 ansible_ssh_port=22 ansible_ssh_user='root' ansible_ssh_private_key_file='/home/pdonnell/.ssh/id_rsa'
    local host="$(cut -f1 -d' ' <<<"$1")"
    local ipaddr="$(grep --only-matching '[[:digit:]]\+\.[[:digit:]]\+.[[:digit:]]\+.[[:digit:]]\+' <<< "$1")"

    run ssh -i ~/ansible.id_rsa -o PreferredAuthentications=publickey -o ConnectTimeout=60 -o ConnectionAttempts=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "root@${ipaddr}" 'gzip /var/log/ceph/*.log /crash/*.core'
    run mkdir -p -m 755 ./logs/"$host" ./stats/"$host" ./crash/"$host"
    run get -r "root@${ipaddr}:/var/log/ceph/*.log*gz" ./logs/"$host"/
    run get -r "root@${ipaddr}":/crash/ ./crash/"$host"/
    run get "root@${ipaddr}":/root/stats.db ./stats/"$host"/
}

run mkdir -p -m 755 ./crash
run mkdir -p -m 755 ./logs
run mkdir -p -m 755 ./stats

grep 'mds-[[:digit:]]\+ ansible_ssh_host=' ansible_inventory | (while read line; do
    run queue_task fetch_host "$line"
done; wait)

grep 'client-[[:digit:]]\+ ansible_ssh_host=' ansible_inventory | (while read line; do
    run queue_task fetch_host "$line"
done; wait)

wait
