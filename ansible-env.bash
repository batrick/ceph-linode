export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_INVENTORY=ansible_inventory
export ANSIBLE_SSH_RETRIES=20

SSH_COMMON_ARGS="-o ConnectTimeout=60 -o ConnectionAttempts=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
ANSIBLE_ARGS="--timeout=60 -vvv --forks=50 --become"

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
