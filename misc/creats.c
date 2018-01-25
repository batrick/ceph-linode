#include <fcntl.h>
#include <unistd.h>
#include <sys/syscall.h>

#include <limits.h>
#include <stdlib.h>
#include <stdio.h>

#ifndef __NR_getrandom
#  define __NR_getrandom 318
#endif

int main (int argc, char *argv[])
{
    const char *prefix = argv[1];
    unsigned long count = strtoul(argv[2], NULL, 10);
    while (count--) {
        size_t i;
        unsigned char buf[20];
        char xbuf[sizeof buf + 1];
        long rc = syscall(__NR_getrandom, buf, sizeof buf, 0);
        if (rc == -1 || (size_t)rc < sizeof buf) {
            abort();
        }
        for (i = 0; i < sizeof buf; i++)
            snprintf(&xbuf[i*2], 3, "%02X", (unsigned)buf[i], (unsigned)buf[i+1]);

        char path[PATH_MAX];
        snprintf(path, PATH_MAX, "%s%s", prefix, xbuf);
        rc = open(path, O_EXCL|O_CREAT|O_CLOEXEC|O_WRONLY|O_NOCTTY, S_IRUSR|S_IWUSR);
        if (rc == -1)
            abort();
        close(rc);
    }
    return 0;
}
