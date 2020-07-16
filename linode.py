import argparse
import binascii
import errno
import json
import logging
import os
import sys
import socket
import time
from os.path import expanduser
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from threading import BoundedSemaphore

from linode_api4 import ApiError, LinodeClient, Config, Disk, Image, Instance, Kernel, Type
from linode_api4.objects.filtering import or_, and_

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

class EAgain(RuntimeError):
    def __str__(self):
        return "EAgain"

def busy_retry(exceptions=[], tries=20, delay=30):
    def wrapper(f):
        def wrapped(*args, **kwargs):
            for i in range(tries-1):
                try:
                    return f(*args, **kwargs)
                except ApiError as e:
                    if e.status in (400, 408, 429):
                        logging.warning(f"retrying due to expected exception: {e}")
                        time.sleep(delay)
                    else:
                        raise
                except exceptions as e:
                    logging.warning(f"retrying due to expected exception: {e}")
                    time.sleep(delay)
            return f(*args, **kwargs)
        return wrapped
    return wrapper

@contextmanager
def releasing(semaphore):
    semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()

class CephLinode():
    user_agent = "https://github.com/batrick/ceph-linode/"

    def __init__(self):
        self._client = None
        self._cluster = None
        self._group = None
        self._images = None
        self._kernels = None
        self._key = None
        self._region = None
        self._ssh_pub_key = None
        self._types = None
        self.create_semaphore = BoundedSemaphore(10)
        self.config_semaphore = BoundedSemaphore(10)

    @property
    def key(self):
        if self._key is not None:
            return self._key

        self._key = os.getenv("LINODE_API_KEY")
        if self._key is None:
            try:
                with open(expanduser("~/.linode.key")) as f:
                    self._key = str(f.read().strip())
                    return self._key
            except:
                raise RuntimeError("please specify Linode API key")

    @property
    def client(self):
        if self._client is not None:
            return self._client

        self._client = LinodeClient(token=self.key,user_agent=self.user_agent)
        return self._client

    @property
    def group(self):
        if self._group is not None:
            return self._group

        try:
            with open("LINODE_GROUP") as f:
                self._group = f.read().strip()
        except IOError as e:
            self._group = "ceph-"+binascii.b2a_hex(os.urandom(3)).decode('utf-8')
            with open("LINODE_GROUP", "w") as f:
                f.write(self.group)
        return self._group

    @property
    def cluster(self):
        if self._cluster is not None:
            return self._cluster

        try:
            with open('cluster.json') as cl:
                self._cluster = json.load(cl)
                return self._cluster
        except IOError as e:
            print('file cluster.json not found')
            sys.exit(1)

    @property
    def ssh_priv_keyfile(self):
        return os.getenv("HOME") + "/.ssh/id_rsa"

    @property
    def ssh_pub_keyfile(self):
        return os.getenv("HOME") + "/.ssh/id_rsa.pub"

    @property
    def ssh_pub_key(self):
        if self._ssh_pub_key is not None:
            return self._ssh_pub_key

        with open(self.ssh_pub_keyfile) as f:
            self._ssh_pub_key = f.read().strip()
            return self._ssh_pub_key

    def instances(self, cond=None):
        if cond is not None:
            return self.client.linode.instances(and_(Instance.group == self.group, cond))
        else:
            return self.client.linode.instances(Instance.group == self.group)

    def _get_region(self):
        if self._region is not None:
            return self._region

        choice = self.cluster['region']
        if choice is None:
            choice = 'us-west'

        for r in self.client.regions():
            if choice.lower() in r.id:
                self._region = r
                return self._region

        raise RuntimeError("cannot find region")

    def _get_machine_type(self, machine):
        # avoid pointless cache expiration of client types
        if self._types is None:
            self._types = list(self.client.linode.types())

        if machine.get('type'):
            t = machine['type']
        elif self.cluster.get('type'):
            t = self.cluster['type']
        else:
            t = 1024

        t = str(t)
        for _type in self._types:
            if t == _type.label or t == str(_type.memory):
                return _type
        logging.error(f"unknown plan type, choose among:\n{[_type.label for _type in self._types]}")
        raise RuntimeError("unknown plan type")

    def _get_machine_kernel(self, machine):
        # avoid pointless cache expiration of client types
        if self._kernels is None:
            self._kernels = list(self.client.linode.kernels())

        if machine.get('kernel'):
            k = machine['kernel']
        elif self.cluster.get('kernel'):
            k = self.cluster['kernel']
        else:
            k = "linode/grub2"

        best = None
        for kernel in self._kernels:
            if kernel.id == k:
                return kernel
            elif k in kernel.label:
                best = kernel
        assert best is not None
        return best

    def _get_machine_image(self, machine):
        # avoid pointless cache expiration of client types
        if self._images is None:
            self._images = list(self.client.images())

        if machine.get('image'):
            i = machine['image']
        elif self.cluster.get('image'):
            i = self.cluster['image']
        else:
            i = "linode/centos8"

        best = None
        for image in self._images:
            if image.id == i:
                return image
            elif i in image.label:
                best = image
        assert best is not None
        return best

    def _parse_common_options(self, key=None, **kwargs):
        if key is not None:
            self._key = key

    @busy_retry(EAgain)
    def _do_create(self, machine, i):
        label = f"{machine['prefix']}-{i:03d}"

        existing = self.instances(Instance.label == label)
        assert(len(existing) <= 1)
        if existing:
            logging.info(f"{label}: already exists as {existing[0].id}")
            instance = existing[0]
            ltype = instance.type
        else:
            ltype = self._get_machine_type(machine)
            region = self._get_region()
            spec = {
                "ltype": ltype,
                "region": region,
                "label": label,
                "group": self.group,
            }
            with releasing(self.create_semaphore):
                logging.info(f"{label}: creating {ltype} in {region}")
                instance = self.client.linode.instance_create(**spec)

        with releasing(self.config_semaphore):
            if not instance.tags:
                # N.B.: ideally we'd have a f"{machine['group']}" tag but different Linode users cannot share tags. Go figure.
                instance.tags = [self.group, f"{self.group}-{machine['group']}"]
                instance.save()

            if not instance.ips.ipv4.private:
                logging.info(f"{label}: allocating private IP")
                instance.ip_allocate()

            swap_size = machine['swap_size'] if machine.get('swap_size') is not None else 128
            root_size = machine['root_size'] if machine.get('root_size') is not None else ltype.disk - swap_size
            if root_size + swap_size < ltype.disk:
                raw_size = ltype.disk - (root_size+swap_size)
            else:
                raw_size = 0

            logging.debug(f"{label}: disk plan: {ltype.disk} {root_size} {swap_size} {raw_size}")

            disks = []

            root = list(filter(lambda d: d.label == 'root', instance.disks))
            if root:
                root = root[0]
                assert(root.size == root_size)
                disks.append(root)
            else:
                image = self._get_machine_image(machine)
                logging.info(f"{label}: creating root disk")
                (d,*_) = instance.disk_create(size=root_size, label='root', image=image, authorized_keys=[self.ssh_pub_key])
                disks.append(d)

            swap = list(filter(lambda d: d.label == 'swap', instance.disks))
            if swap:
                swap = swap[0]
                assert(swap.size == swap_size)
                assert(swap.filesystem == 'swap')
                disks.append(swap)
            else:
                logging.info(f"{label}: creating swap disk")
                disks.append(instance.disk_create(size=swap_size, label='swap', filesystem="swap"))

            raw = list(filter(lambda d: d.label == 'raw', instance.disks))
            if raw:
                raw = raw[0]
                assert(raw.size == raw_size)
                assert(raw.filesystem == 'raw')
                disks.append(raw)
            elif raw_size > 0:
                logging.info(f"{label}: creating raw disk")
                disks.append(instance.disk_create(size=raw_size, label='raw', filesystem="raw"))

            logging.info(f"{label}: disks {disks}")

            config = list(filter(lambda c: c.label == 'ceph', instance.configs))
            if config:
                config = config[0]
                logging.info(f"{label}: ceph config already setup")
            else:
                kernel = self._get_machine_kernel(machine)
                logging.info(f"{label}: creating ceph config")
                instance.config_create(kernel=kernel,label='ceph',disks=disks)

            if instance.status == 'running':
                logging.info(f"{label}: already running")
            else:
                logging.info(f"{label}: booting")
                instance.boot(config=config)

            return instance

    def _create(self, *args, **kwargs):
        try:
            return self._do_create(*args, **kwargs)
        except Exception as e:
            logging.exception(e)
            os._exit(1)

    def launch(self, **kwargs):
        logging.info(f"launch {kwargs}")
        self._parse_common_options(**kwargs);

        running = []
        with ThreadPoolExecutor(max_workers=50) as executor:
            count = 0
            for machine in self.cluster['nodes']:
                for i in range(machine['count']):
                    logging.info(f"creating node {machine['group']}.{i}")
                    running.append(executor.submit(self._create, machine, i))
                    count += 1
                    if count % 10 == 0:
                        # slow ramp up
                        time.sleep(10)

        logging.info(f"{[f.result() for f in running]}")

        linodes = []
        with open("ansible_inventory", mode = 'w') as f:
            groups = set([node['group'] for node in self.cluster['nodes']])
            for group in groups:
                f.write(f"[{group}]\n")
                group_tag = f"{self.group}-{group}"
                for future in running:
                    linode = future.result()
                    if group_tag in linode.tags:
                        if socket.gethostname().endswith('.linode.com'):
                            # assumes deployment node is at same site as ceph cluster
                            ip = linode.ips.ipv4.private[0].address
                        else:
                            ip = linode.ips.ipv4.public[0].address
                        f.write(f"\t{linode.label} ansible_ssh_host={ip} ansible_ssh_port=22 ansible_ssh_user='root' ansible_ssh_private_key_file='{self.ssh_priv_keyfile}' ceph_group='{group}'")
                        if group == 'mons':
                            f.write(f" monitor_address={ip}")
                        f.write("\n")
                        l = {
                          'id': linode.id,
                          'label': linode.label,
                          'ip_private': linode.ips.ipv4.private[0].address,
                          'ip_public': linode.ips.ipv4.public[0].address,
                          'group': linode.group,
                          'ceph_group': group,
                          'user': 'root',
                          'key': self.ssh_priv_keyfile,
                        }
                        linodes.append(l)

        with open("linodes", mode = 'w') as f:
            f.write(json.dumps(linodes))

    @busy_retry()
    def _do_destroy(self):
        # use list of instances because deletion invalidates the PaginatedList
        for i in list(self.instances()):
            logging.info(f"destroy {i.label}")
            i.delete()

    def _destroy(self, *args, **kwargs):
        try:
            return self._do_destroy(*args, **kwargs)
        except Exception as e:
            logging.exception(e)
            os._exit(1)

    def destroy(self, **kwargs):
        logging.info(f"destroy {kwargs}")
        self._parse_common_options(**kwargs);

        self._do_destroy()

        # clear inventory file or else launch.sh won't create linodes
        ansible_inv_file = os.getenv('ANSIBLE_INVENTORY')
        if not ansible_inv_file:
            ansible_inv_file = 'ansible_inventory'
        try:
            os.unlink(ansible_inv_file)
            logging.info('removed ansible inventory file %s' % ansible_inv_file)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise e

    @busy_retry()
    def _do_nuke(self, sema, node):
        with releasing(sema):
            while True:
                changed = False
                node.invalidate()

                if node.status == 'running':
                    node.shutdown()
                    changed = True

                for config in node.configs:
                    config.delete()
                    changed = True

                for disk in node.disks:
                    disk.delete()
                    changed = True

                if node.tags:
                    node.tags = []
                    node.save()
                    changed = True

                if not changed:
                    break

                time.sleep(10)

    def _nuke(self, *args, **kwargs):
        try:
            return self._do_nuke(*args, **kwargs)
        except Exception as e:
            logging.exception(e)
            os._exit(1)

    def nuke(self, **kwargs):
        logging.info(f"nuke {kwargs}")
        self._parse_common_options(**kwargs);

        nuke_semaphore = BoundedSemaphore(10)
        with ThreadPoolExecutor(max_workers=50) as executor:
            executor.map(lambda node: self._nuke(nuke_semaphore, node), self.instances())

        # clear inventory file or else launch.sh won't create linodes
        ansible_inv_file = os.getenv('ANSIBLE_INVENTORY')
        if not ansible_inv_file:
            ansible_inv_file = 'ansible_inventory'
        try:
            os.unlink(ansible_inv_file)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise e

    def wait(self, **kwargs):
        logging.info(f"wait {kwargs}")
        self._parse_common_options(**kwargs);
        raise NotImplementedError()

    def list(self, **kwargs):
        logging.info(f"list {kwargs}")
        self._parse_common_options(**kwargs);
        raise NotImplementedError()

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--key', dest='key', help='Linode API Key')
    subparsers = parser.add_subparsers(dest='cmd')

    l = subparsers.add_parser('launch')
    d = subparsers.add_parser('destroy')
    n = subparsers.add_parser('nuke')
    w = subparsers.add_parser('wait')
    l = subparsers.add_parser('list')
    kwargs = vars(parser.parse_args())

    L = CephLinode()
    return getattr(L, kwargs.pop('cmd'))(**kwargs)

if __name__ == "__main__":
    main(sys.argv)
