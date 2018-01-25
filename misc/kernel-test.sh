set -ex
ulimit -n 65536

source ansible-env.bash

ans --module-name=shell --args='yum groupinstall -y "Development tools"' clients
ans --module-name=yum --args='name="autoconf,automake,bc,gdb" state=latest update_cache=yes' clients

ans --module-name=yum --args="name=htop state=latest update_cache=yes" all
ans --module-name=shell --args="mkdir -p /root/.config/htop" all
ans --module-name=copy --args='src=misc/htoprc dest=/root/.config/htop/htoprc owner=root group=root mode=644' all

ans --module-name=copy --args='src=misc/ceph-gather.py dest=/root/ owner=root group=root mode=755' all
ans --module-name=copy --args='src=misc/ceph-gather.service dest=/etc/systemd/system/ owner=root group=root mode=644' all
ans --module-name=copy --args="src=misc/kernel_untar_build.sh dest=/root/ owner=root group=root mode=755" clients
ans --module-name=copy --args="src=misc/creats.sh dest=/root/ owner=root group=root mode=755" clients
ans --module-name=copy --args="src=misc/creats.c dest=/root/ owner=root group=root mode=644" clients

ans --module-name=shell --args='ceph tell mds.\* config set mempool_debug true' mon-000
ans --module-name=shell --args='ceph tell mds.\* config set mds_cache_memory_limit $((8*2**30))' mon-000

ans --module-name=shell --args='umount /mnt; mount -t ceph $(grep "mon host" /etc/ceph/ceph.conf | tr -d "[[:space:][:alpha:]=]"):/ /mnt -o secret=$(grep key /etc/ceph/ceph.client.admin.keyring | awk "{print \$3}"),name=admin; true' clients
#ans --module-name=shell --args="rm -f /root/stats.db; systemctl start ceph-gather.service" "clients mdss"
ans --module-name=shell --args="rm -f /root/stats.db; systemctl start ceph-gather.service" mdss

date --utc
time ans --forks=1000 --module-name=shell --args="chdir=/mnt/ /root/kernel_untar_build.sh" clients
date --utc

ans --module-name=shell --args="systemctl stop ceph-gather.service" mdss
#ans --module-name=shell --args="systemctl stop ceph-fuse@-mnt.service" clients
