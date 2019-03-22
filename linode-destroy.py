import binascii
import logging
import os
import errno

from multiprocessing.dummy import Pool as ThreadPool

from contextlib import closing

from linode_api4 import LinodeClient

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

with open("LINODE_GROUP") as f:
    GROUP = unicode(f.read().strip())

def main():
    key = os.getenv("LINODE_API_KEY")
    if key is None:
        raise RuntimeError("please specify Linode API key")

    client = LinodeClient(key)

    def destroy(linode):
        linode.delete()
        #client.linode_delete(LinodeID = linode[u'LINODEID'], skipChecks = 1)

    linodes = client.linode.instances()
    logging.info("linodes: {}".format(linodes))

    with closing(ThreadPool(5)) as pool:
        group = filter(lambda linode: linode.group == GROUP, linodes)
        pool.map(destroy, group)
        pool.close()
        pool.join()

    linodes = client.linode.instances()
    logging.info("linodes: {}".format(linodes))

    # clear inventory file or else launch.sh won't create linodes
    ansible_inv_file = os.getenv('ANSIBLE_INVENTORY')
    if not ansible_inv_file:
        ansible_inv_file = 'ansible_inventory'
    try:
      os.unlink(ansible_inv_file)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise e
    
    logging.info('removed ansible inventory file %s' % ansible_inv_file)

if __name__ == "__main__":
    main()
