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
    local ipaddr="$1"
    local host="$2"

    run ssh -i ~/ansible.id_rsa -o PreferredAuthentications=publickey -o ConnectTimeout=60 -o ConnectionAttempts=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "root@${ipaddr}" 'systemctl stop ceph-gather.service; logrotate -f /etc/logrotate.d/ceph & gzip /crash/*.core /root/stats.db & wait;'
    run mkdir -p -m 755 ./logs/"$host" ./stats/"$host" ./crash/"$host"
    run get -r "root@${ipaddr}:/var/log/ceph/*.log*gz" ./logs/"$host"/
    run get -r "root@${ipaddr}":/crash/ ./crash/"$host"/
    run get "root@${ipaddr}":/root/stats.db.gz ./stats/"$host"/
}

run mkdir -p -m 755 ./crash
run mkdir -p -m 755 ./logs
run mkdir -p -m 755 ./stats

function fetch_group {
    < linodes jq -rc ".[] | select(.name | contains(\"$1\")) | .ip_public, .name" | (while read ip; do
        read name
        run queue_task fetch_host "$ip" "$name"
    done; wait)
}

fetch_group mds
fetch_group client

wait
