#!/usr/bin/env bash
set -u
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 1
source "$SCRIPT_DIR/common/utilities.sh"
init_report system-inventory 'Inventory existing Ubuntu logging, process access and kernel build/interface evidence.' "$@"
rc=$?; (( rc == 2 )) && exit 0; (( rc == 0 )) || exit "$rc"
environment_info
audit_info
record 'journald service state' systemctl show systemd-journald.service -p LoadState -p ActiveState -p SubState
record 'Journal storage usage accessible to observer (no records)' journalctl --no-pager --disk-usage
privileged_read 'Journal storage accessibility comparison' journalctl --no-pager --disk-usage
record 'Proc mount options' findmnt -rn -T /proc -o TARGET,FSTYPE,OPTIONS
record 'Observer proc status fields' grep -E '^(Name|State|Pid|PPid|Uid|Gid|Threads):' "/proc/$$/status"
section 'Available inspection utilities'
for tool in ps pgrep readlink stat findmnt journalctl auditctl ausearch bpftool; do
    if have "$tool"; then note "$tool: installed/on PATH"; else note "$tool: unavailable on PATH; related checks not investigated"; fi
done
kernel_info
finish_report
