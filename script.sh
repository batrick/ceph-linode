#!/bin/bash
WATCH="clients mdss"

    ans --module-name=shell --args='yum groupinstall -y "Development tools"' clients
    ans --module-name=yum --args='name="autoconf,automake,bc,gdb" state=latest update_cache=yes' clients

    ans --module-name=yum --args="name=htop state=latest update_cache=yes" all
    ans --module-name=command --args="mkdir -p /root/.config/htop" all
    ans --module-name=copy --args='src=htoprc dest=/root/.config/htop/htoprc owner=root group=root mode=644' all

    ans --module-name=shell --args='ceph --admin-daemon /var/run/ceph/*asok config set mon_allow_pool_delete true' mons
    ans --module-name=shell --args='ceph osd pool rm rbd rbd --yes-i-really-really-mean-it' mon-000

    ans --module-name=copy --args='src=ceph-gather.py dest=/ owner=root group=root mode=755' all
    ans --module-name=copy --args='src=ceph-gather.service dest=/etc/systemd/system/ owner=root group=root mode=644' all
    ans --module-name=copy --args="src=./kernel_untar_build.sh dest=/ owner=root group=root mode=755" clients

    ans --module-name=shell --args="chmod 000 /mnt" all
    ans --module-name=command --args="systemctl start ceph-fuse@-mnt.service" clients
    ans --module-name=command --args="systemctl start ceph-gather.service" "$WATCH"
    (sleep 30; while ! python2 balancer.py; do sleep 30; done) >> BALANCER 2>&1 &
    date --utc
    time ans --forks=1000 --module-name=command --args="chdir=/mnt/ /kernel_untar_build.sh" clients
    date --utc
    wait
    ans --module-name=command --args="systemctl stop ceph-gather.service" "$WATCH"
    ans --module-name=command --args="systemctl stop ceph-fuse@-mnt.service" clients
