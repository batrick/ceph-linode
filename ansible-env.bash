export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_INVENTORY=ansible_inventory
export ANSIBLE_SSH_RETRIES=20
# pretty-print JSON to prevent logging hairballs
export ANSIBLE_STDOUT_CALLBACK=debug

SSH_COMMON_ARGS="-o ConnectTimeout=60 -o ConnectionAttempts=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
ANSIBLE_ARGS="--timeout=60 -vv --forks=50 --become"

function repeat {
    while ! "$@"; do
        printf "failed...\n" >&2
        sleep 1
    done
}

function ans {
    time ansible --ssh-common-args="$SSH_COMMON_ARGS" $ANSIBLE_ARGS "$@"
}

function do_playbook {
    time ansible-playbook $ANSIBLE_ARGS "$@"
}
