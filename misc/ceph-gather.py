import glob
import os
import socket
import sqlite3
import struct
import sys
import time
from contextlib import closing

CLIENT_ADMIN_SOCKET_GLOB = "/var/run/ceph/ceph-client*.asok"
MDS_ADMIN_SOCKET_GLOB = "/var/run/ceph/ceph-mds*.asok"
SC_CLK_TCK = os.sysconf(os.sysconf_names['SC_CLK_TCK'])

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS Daemon (
    id INTEGER PRIMARY KEY,
    asok TEXT UNIQUE NOT NULL,
    config TEXT NOT NULL,
    hostname TEXT NOT NULL,
    type TEXT NOT NULL,
    SC_CLK_TCK INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS DaemonStats (
    id INTEGER NOT NULL REFERENCES Daemon(id),
    timestamp DATETIME NOT NULL DEFAULT (strftime('%s', 'now')),

    pid INTEGER NOT NULL, -- 1
    comm TEXT NOT NULL, -- 2
    state TEXT NOT NULL, -- 3
    minflt INTEGER NOT NULL, -- 10
    cminflt INTEGER NOT NULL, -- 11
    majflt INTEGER NOT NULL, -- 12
    cmajflt INTEGER NOT NULL, -- 13
    utime INTEGER NOT NULL, -- 14
    stime INTEGER NOT NULL, -- 15
    cstime INTEGER NOT NULL, -- 16
    starttime INTEGER NOT NULL, -- 22
    vsize INTEGER NOT NULL, -- 23
    rss INTEGER NOT NULL, -- 24
    nswap INTEGER NOT NULL, -- 24
    delayacct_blkio_ticks INTEGER NOT NULL, -- 42
    uptime INTEGER NOT NULL, -- /proc/uptime in clock ticks (* SC_CLK_TCK)

    PRIMARY KEY (id, timestamp, pid)
);
CREATE INDEX IF NOT EXISTS DaemonStats_TimestampIndex ON DaemonStats (timestamp);
CREATE TABLE IF NOT EXISTS ClientStatus (
    id INTEGER NOT NULL REFERENCES Daemon(id),
    mds_sessions TEXT NOT NULL,
    perf_dump TEXT NOT NULL,
    status TEXT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT (strftime('%s', 'now')),
    PRIMARY KEY (id, timestamp)
);
CREATE INDEX IF NOT EXISTS ClientStatus_TimestampIndex ON ClientStatus (timestamp);
CREATE TABLE IF NOT EXISTS MDSStatus (
    id INTEGER NOT NULL REFERENCES Daemon(id),
    session_ls TEXT NOT NULL,
    subtrees TEXT NOT NULL,
    ops TEXT NOT NULL,
    perf_dump TEXT NOT NULL,
    status TEXT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT (strftime('%s', 'now')),
    PRIMARY KEY (id, timestamp)
);
CREATE INDEX IF NOT EXISTS MDSStatus_TimestampIndex ON MDSStatus (timestamp);
"""

class AdminSocket:
    #SO_PEERCRED = 17 # Pulled from /usr/include/asm-generic/socket.h

    def __init__(self, path):
        self.path = path
        self.getid()

    def getid(self):
        with closing(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)) as sock:
            sock.connect(self.path)
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
            self.pid, self.uid, self.gid = struct.unpack('3i',creds)
            # Do something so we don't see an error: "AdminSocket: error reading request code: (0) Success"
            sock.sendall("{\"prefix\": \"help\", \"format\": \"json\"}\x00")
            length = struct.unpack('>i', sock.recv(4))[0]
            sock.recv(length, socket.MSG_WAITALL)

    def cmd(self, c):
        with closing(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)) as sock:
            sock.connect(self.path)
            sock.sendall("{\"prefix\": \"%s\", \"format\": \"json\"}\x00" % c)
            length = struct.unpack('>i', sock.recv(4))[0]
            return sock.recv(length, socket.MSG_WAITALL)

class DaemonStatus:
    def __init__(self, path, db):
        self.asok = AdminSocket(path)
        self.path = path
        self.db = db

        diff = self.asok.cmd("config diff")
        cur = self.db.cursor()
        cur.execute("INSERT OR IGNORE INTO Daemon (asok, type, hostname, config, SC_CLK_TCK) VALUES (?, ?, ?, ?, ?);", (self.path, self.type, socket.gethostname(), diff, SC_CLK_TCK))
        rows = cur.execute("SELECT id FROM Daemon WHERE asok = ?;", (self.path,));
        self.id = cur.fetchone()[0]
        assert(self.id >= 0)
        assert(cur.fetchone() == None)
        db.commit()

    def logstatus(self):
        results = [self.id]
        for command in self.commands:
            results.append(self.asok.cmd(command))
        self.db.execute(self.update, results)

        with open("/proc/uptime") as uptimef:
            uptime = int(float(uptimef.read().split()[0]) * SC_CLK_TCK)

        # refresh pid in case of crashes
        self.asok.getid()
        procpath = "/proc/%s/" % self.asok.pid
        for pid in os.listdir(os.path.join(procpath, "task")):
            with open(os.path.join(procpath, "task", pid, "stat")) as statf:
                data = statf.read().split()
                fields = {
                    "id": self.id,
                    "pid": data[1-1],
                    "comm": data[2-1],
                    "state": data[3-1],
                    "minflt": data[10-1],
                    "cminflt": data[11-1],
                    "majflt": data[12-1],
                    "cmajflt": data[13-1],
                    "utime": data[14-1],
                    "stime": data[15-1],
                    "cstime": data[16-1],
                    "starttime": data[22-1],
                    "vsize": data[23-1],
                    "rss": data[24-1],
                    "nswap": data[36-1],
                    "delayacct_blkio_ticks": data[42-1],
                    "uptime": uptime,
                }
                keys = sorted(fields.keys())
                sql = "INSERT INTO DaemonStats (%s) VALUES (? %s);" % (','.join([k for k in keys]), ", ?" * (len(keys)-1))
                self.db.execute(sql, [fields[k] for k in keys])

class ClientStatus(DaemonStatus):
    type = "client"
    commands = ("mds_sessions", "perf dump", "status")
    update = "INSERT INTO ClientStatus(id, mds_sessions, perf_dump, status) VALUES (?, ?, ?, ?);"

class MDSStatus(DaemonStatus):
    type = "mds"
    commands = ("session ls", "ops", "perf dump", "status", "get subtrees")
    update = "INSERT INTO MDSStatus(id, session_ls, ops, perf_dump, status, subtrees) VALUES (?, ?, ?, ?, ?, ?);"

def main():
    db = sqlite3.connect(sys.argv[1])
    db.executescript(SCHEMA)

    daemons = []
    for path in glob.glob(CLIENT_ADMIN_SOCKET_GLOB):
        daemons.append(ClientStatus(path, db))
    for path in glob.glob(MDS_ADMIN_SOCKET_GLOB):
        daemons.append(MDSStatus(path, db))

    if len(daemons) == 0:
        sys.exit(0)

    while True:
        for daemon in daemons:
            daemon.logstatus()
        db.commit()
        time.sleep(2)

if __name__ == "__main__":
    main()
