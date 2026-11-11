#!/usr/bin/env bash
set -euo pipefail
# Explicit root-only acceptance harness. Uses synthetic input and existing identities.
# Run from the repository root, passing the already-built plugin executable.
plugin=${1:?Pass the absolute path to the built M3 plugin}
[[ $plugin == /* && -f $plugin && -x $plugin ]]
umask 077
test "$(id -u)" = 0
guest=$(mktemp -d /run/hids-m3-test.XXXXXXXX)
child=
cleanup() {
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
                 root / "ipc/socket", int(uid), int(ipc), connect_timeout=5)
    assert with_path.db.execute("select count(*) from m3_execution").fetchone() == (1,)
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
sed -e '/^type=EOE/s/$/ /' tests/fixtures/audit/structural-exec.log |
  setpriv --reuid "$read_uid" --regid "$read_gid" --groups "$ipc" --no-new-privs "$guest/plugin" "$guest/ipc/socket" a g l "$read_uid" "$read_gid" "$ing_uid" "$ing_gid" "$ipc"
wait "$child"
child=
