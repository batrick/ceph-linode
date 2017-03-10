import linode.api as linapi
import logging
import os
import time

from contextlib import closing, contextmanager
from multiprocessing.dummy import Pool as ThreadPool

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

with open("LINODE_GROUP") as f:
    GROUP = unicode(f.read())

def nuke(client, linode):
    changed = False

    while True:
        jobs = client.linode_job_list(LinodeID = linode[u'LINODEID'], pendingOnly = 1)
        jobs = filter(lambda j: not j['HOST_FINISH_DT'], jobs)
        if len(jobs) == 0:
            break
        logging.info("waiting for linode job queue to clear...")
        time.sleep(5)

    if linode[u'STATUS'] != 2:
        client.linode_shutdown(LinodeID = linode[u'LINODEID'])
        changed = True

    configs = client.linode_config_list(LinodeID = linode[u'LINODEID'])
    for config in configs:
        client.linode_config_delete(LinodeID = config[u'LinodeID'], ConfigID = config[u'ConfigID'])
        changed = True

    disks = client.linode_disk_list(LinodeID = linode[u'LINODEID'])
    for disk in disks:
        client.linode_disk_delete(LinodeID = disk[u'LINODEID'], DiskID = disk[u'DISKID'])
        changed = True

    return changed

def newcb():
    # and this is why local by default is stupid (and Python has a moronic design for closures):
    changed = [False]
    def cb(result):
        changed[0] |= result
    def status():
        return changed[0]
    return (status, cb)

def main():
    key = os.getenv("LINODE_API_KEY")
    if key is None:
        raise RuntimeError("please specify Linode API key")

    client = linapi.Api(key = key, batching = False)

    while True:
        # FIXME only nuke linodes which aren't done, and do one last check at the end
        linodes = client.linode_list()
        logging.info("%s", linodes)

        with closing(ThreadPool(25)) as pool:
            status, cb = newcb()

            for linode in linodes:
                if linode[u'LPM_DISPLAYGROUP'] == GROUP:
                    pool.apply_async(nuke, (client, linode), {}, cb)
            pool.close()
            pool.join()

            if not status():
                return

        time.sleep(60)

if __name__ == "__main__":
    main()
