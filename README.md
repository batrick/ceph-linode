# Repository of scripts to deploy Ceph in Linode

The repository has a collection of scripts that automate the deployment of Ceph
within Linode. The primary use-case for this work is to allow rapid testing of
Ceph at scale.

The repository has a number of utilities rougly organized as:

* `linode.py`: script to rapidly create/configure/nuke/destroy Linodes.

* `launch.sh`: a helper script for launching a Ceph cluster or repaving
  an existing one.

* `pre-config.yml`: an ansible playbook to pre-configure Linodes with useful
   packages or utilities prior to installing Ceph via ceph-ansible.

* `group_vars`: template group variables for ceph-ansible. These samples
  contain some suggested configurations to get started rapidly. See the
  ceph-ansible docs for other options.

* `playbooks/`: ansible playbooks for running serial tests and collecting test
  artifacts and performance data. Note that most of these playbooks were
  written for testing CephFS.

* `scripts/` and `misc/`: miscellaneous scripts. Notably, workflow management
  scripts for testing CephFS are located here.

* `graphing/`: graphing scripts using gnuplot and some ImageMagik utilities.
  These may run on the artifacts produced by the ansible playbooks in
  `playbooks`.


## How-to Get Started:

> :fire: **Note** :fire: For non-toy deployments, it's recommended to use a
> dedicated linode for running ceph-ansible. This reduces latency of
> operations, internet hiccups, allows you to allocate enough RAM for
> memory-hungry ansible, and rapidly download test artifacts for archival.
> Generally, the more RAM/cores the better. **Also**: make sure to [enable a
> private IP
> address](https://www.linode.com/docs/platform/manager/remote-access/#adding-private-ip-addresses)
> on the ansible linode otherwise ansible will not be able to communicate with
> the ceph cluster.

> :fire: **Note** :fire: Linode recently updated their GUI for viewing Linodes and the associated API. `ceph-linode` has not yet been updated to this new API. Always view your Linodes using [the old gateway](https://manager.linode.com/).

* Setup a Linode account and [get an API key](https://www.linode.com/docs/platform/api/api-key).

  Put the key in `~/.linode.key`:

  ```bash
  cat > ~/.linode.key
  ABCFejfASFG...
  ^D
  ```

* Setup an ssh key if not already done:

  ```bash
  ssh-keygen
  ```

* Install necessary packages:

  **Fedora**:

    ```bash
    dnf install screen git ansible python3-notario python3-pip python3-netaddr jq rsync htop wget
    pip3 install linode_api4
    ```

  **Arch Linux**:

    ```bash
    pacman -Syu screen git ansible python3-netaddr python3-pip jq rsync htop wget
    pip3 install notario linode_api4
    ```

* Clone ceph-linode:

  ```bash
  git clone https://github.com/batrick/ceph-linode.git
  ```

* Clone ceph-ansible:

  ```bash
  git clone -b v4.0.0rc9 https://github.com/ceph/ceph-ansible.git
  ```

  It's recommended to use a tagged version to limit the possibility of
  compatibility bugs between the version of Ceph you're using and the version
  of ceph-ansible it's deployed with.

* Copy `cluster.json.sample` to `cluster.json` and modify it to have the desired
  count and Linode plan for each daemon type. If you're planning to do testing
  with CephFS, it is recommend to have 3+ MDS, 2+ clients, and 8+ OSDs. The
  ansible playbook `playbooks/cephfs-setup.yml` will configure 4 OSDs to be
  dedicated for the metadata pool.

> :fire: **Note** :fire: The OSD memory target set by ceph-ansible is always at least 4GB, otherwise set appropriately and automatically based on the available memory on the OSD. If you use smaller OSDs (4GB or smaller), then you must configure the memory target manually via the `ceph_conf_overrides` in `group_vars/all`.

* Add a `group_vars` directory in this checkout with the necessary settings. A
  sample has been provided in this checkout which has worked in the past but
  may need updated. See [ceph-ansible documentation for more
  information](https://docs.ceph.com/ceph-ansible/master/).

* Start using:

    ```bash
    ./launch.sh --ceph-ansible /path/to/ceph-ansible
    ```

## SSH to a particular machine

```bash
./ansible-ssh mon-000
```

Or any named node in the `linodes` JSON file.

## Execute ansible commands against the cluster

```bash
source ansible-env.bash
ans -m shell -a 'echo im an osd' osds
ans -m shell -a 'echo im an mds' mdss
ans -m shell -a 'echo im a client' clients
...
```

You can also easily execute playbooks:

```bash
source ansible-env.bash
do_playbook foo.yml
```

## How-to nuke and repave your cluster:

Sometimes you want to start over from a clean slate. Destroying the cluster can
incur unnecessary costs though as Linodes are billed by the hour, no matter how
little of an hour you use. It is often cheaper to *nuke* the Linodes by
deleting all configurations, destroying all disks, etc.

If you used `launch.sh`, you can do this easily via:

```bash
./launch.sh --nuke ...
```

It will recreate the cluster without destroying any of your Linodes.

Otherwise, you can manually nuke the cluster if you want using:

```bash
python3 linode.py nuke
```

## How-to destroy your cluster:

```bash
python3 linode.py destroy
```

The script works by destroying all the Linodes that belong to the group named
in the `LINODE_GROUP` file, created by `linode-create.py`.
