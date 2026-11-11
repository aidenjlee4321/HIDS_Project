#!/usr/bin/env bash
set -euo pipefail
# Explicit root-only VM acceptance harness. Temporarily configures a plugin,
# RAW output and one process-scoped rule, restoring the original configuration.
# Requires no pre-existing Audit rules and existing hids-ingest/hids-ipc identities.
plugin=${1:?Pass the absolute path to the built M3 plugin}
[[ $plugin == /* && -f $plugin && -x $plugin ]]
umask 077
test "$(id -u)" = 0
guest=$(mktemp -d /run/hids-m3-test.XXXXXXXX)
child=
conf=/etc/audit/plugins.d/hids-m3-acceptance.conf
changed=
[[ $(auditctl -l) == 'No rules' && ! -e $conf && ! -L $conf ]]
cp /etc/audit/auditd.conf "$guest/auditd.conf"
cleanup() {
    if [[ -n $changed ]]; then
        if [[ -f $guest/plugin.stderr ]]; then cat "$guest/plugin.stderr"; fi
        rm -f -- "$conf"
        cat "$guest/auditd.conf" > /etc/audit/auditd.conf
        auditctl --signal reload
        cmp -s "$guest/auditd.conf" /etc/audit/auditd.conf
        auditctl -l
        systemctl is-active auditd
    fi
    if [[ -n $child ]]; then kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi
    rm -rf -- "$guest"
}
trap cleanup EXIT
chmod 755 "$guest"
install -m755 "$plugin" "$guest/plugin"
cp -R engine "$guest/engine"
chmod -R a+rX "$guest/engine"
ing_uid=$(id -u hids-ingest)
ing_gid=$(id -g hids-ingest)
ipc=$(getent group hids-ipc | cut -d: -f3)
read_uid=$(id -u nobody)
read_gid=$(id -g nobody)
install -d -m750 -o "$ing_uid" -g "$ipc" "$guest/ipc"
install -d -m700 -o "$ing_uid" -g "$ing_gid" "$guest/state"
cat > "$guest/receiver.py" <<'PY'
import sys
import json
import base64
import os
from pathlib import Path
from engine.ingestion.m2_receiver import PeerPolicy
from engine.ingestion.m3_receiver import Receiver
from engine.ingestion.m3_progress import Progress
root, uid, gid, ipc, reader, reader_group = sys.argv[1:]
root = Path(root)
with_path = Progress(root / "state/events.sqlite", "a", "g", 0)
try:
    Receiver(with_path, {"activation":"a","generation":"g","lease":"l"},
             PeerPolicy(int(reader), int(reader_group))).serve_named(
                 root / "ipc/socket", int(uid), int(ipc), connect_timeout=15)
    count, = with_path.db.execute("select count(*) from m3_execution").fetchone()
    print(f"Native execution rows: {count}; positions: {with_path.positions()}")
    accepted = [json.loads(row[0]) for row in with_path.db.execute("select payload from m3_execution")]
    executable = base64.b64encode(os.fsencode(os.path.realpath("/usr/bin/true"))).decode("ascii")
    matches = [row for row in accepted if row["exe_base64"] == executable and row["comm_base64"] == "dHJ1ZQ==" and row["success"]]
    assert len(matches) == 1
    assert matches[0]["path_count"] == 2
    print("PASS: live auditd execution reconstructed through libauparse and committed to SQLite")
    scanned, frontier = with_path.positions()
    assert scanned == frontier > 0
    print("PASS: Ubuntu non-root plugin, mutual Linux peer credentials, named socket and durable SQLite row")
finally:
    with_path.close()
PY
chmod 644 "$guest/receiver.py"
setpriv --reuid "$ing_uid" --regid "$ing_gid" --groups "$ipc" --no-new-privs python3 -B "$guest/receiver.py" "$guest" "$ing_uid" "$ing_gid" "$ipc" "$read_uid" "$read_gid" &
child=$!
for _ in {1..40}; do [[ ! -S $guest/ipc/socket ]] || break; sleep .1; done
test -S "$guest/ipc/socket"
cat > "$guest/launch" <<LAUNCH
#!/bin/sh
exec /usr/bin/setpriv --reuid "$read_uid" --regid "$read_gid" --groups "$ipc" --no-new-privs "$guest/plugin" "$guest/ipc/socket" a g l "$read_uid" "$read_gid" "$ing_uid" "$ing_gid" "$ipc" 2>> "$guest/plugin.stderr"
LAUNCH
chmod 755 "$guest/launch"
changed=1
sed 's/^[[:space:]]*log_format[[:space:]]*=.*/log_format = RAW/' "$guest/auditd.conf" > /etc/audit/auditd.conf
printf 'active = yes\npath = %s/launch\ntype = always\nformat = string\n' "$guest" > "$conf"
chmod 640 "$conf"
auditctl --signal reload
sleep 1
python3 - <<'PY2'
import os
import subprocess
import time
rule = ["always,exit", "-F", "arch=b64", "-S", "execve,execveat",
        "-F", f"ppid={os.getpid()}", "-k", "hids_m3_acceptance"]
subprocess.run(["auditctl", "-a", *rule], check=True)
try:
    subprocess.run(["/usr/bin/true", "plugin probe", "x" * 10000], check=True)
    time.sleep(2)
finally:
    subprocess.run(["auditctl", "-d", *rule], check=True)
PY2
rm -f -- "$conf"
cat "$guest/auditd.conf" > /etc/audit/auditd.conf
auditctl --signal reload
for _ in {1..30}; do kill -0 "$child" 2>/dev/null || break; sleep .1; done
if kill -0 "$child" 2>/dev/null; then
    echo 'Receiver still waiting after plugin removal'
    exit 1
fi
wait "$child"
child=
