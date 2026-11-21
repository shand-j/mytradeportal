#!/bin/sh
set -eu

chown 10001:10001 /mnt/data
exec su -m -s /bin/sh rustfs -c '/etc/rustfs/entrypoint.sh'
