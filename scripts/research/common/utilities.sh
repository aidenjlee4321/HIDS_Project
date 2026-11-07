#!/usr/bin/env bash
# Research helpers only. Deliberately no set -e: failed probes must be recorded.

section() { printf '\n========== %s ==========\n' "$*"; }
note() { printf '%s\n' "$*"; }
stamp() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
have() { command -v "$1" >/dev/null 2>&1; }

init_report() {
    local name=$1 purpose=$2 arg
    PRIVILEGED=0
    for arg in "$@"; do
        case "$arg" in
            --privileged) PRIVILEGED=1 ;;
            --help) printf 'Usage: bash %s.sh [--privileged]\n' "$name"; return 2 ;;
        esac
    done
    if (( $# > 3 )) || { (( $# == 3 )) && [[ $3 != --privileged ]]; }; then
        printf 'Unknown arguments. Use --help.\n' >&2; return 1
    fi
    if (( EUID == 0 )); then
        printf 'Run as an ordinary user; use --privileged for selected read-only checks.\n' >&2
        return 1
    fi
    [[ $(uname -s) == Linux ]] || { printf 'These probes require Linux; not run.\n' >&2; return 1; }
    have timeout || { printf 'Required Ubuntu coreutils command timeout is missing.\n' >&2; return 1; }
    umask 077
    # A fresh private directory avoids collisions and existing-file/symlink overwrites.
    REPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/hids-research.XXXXXXXX") || return 1
    REPORT="$REPORT_DIR/$name-$(date -u '+%Y-%m-%d-%H%M%S').txt"
    : > "$REPORT" || return 1
    printf 'Report: %s\n' "$REPORT"
    exec 3>&2
    exec >> "$REPORT" 2>&1
    export LC_ALL=C SYSTEMD_PAGER=cat SYSTEMD_COLORS=0
    section "$name — temporary research utility v1"
    note "Purpose: $purpose"
    note "Collection start (UTC): $(stamp)"
    note "Observer numeric UID=$UID EUID=$EUID; optional privileged reads=$PRIVILEGED"
    note 'Observations below are scoped to this identity, host environment and time.'
    note 'No automatic capability verdict: command failure may mean permission, missing tool, unsupported option, or another error.'
    note 'Output per check capped at 200 lines / 32768 bytes; truncation may split records. Each command has a 10-second timeout.'
}

# No eval or user-supplied shell strings. Commands retain argument boundaries.
record() {
    local label=$1 rc
    shift
    section "$label"
    printf 'Check time: %s\nCommand:' "$(stamp)"
    printf ' %q' "$@"
    printf '\n'
    if ! have "$1"; then
        note "Unavailable utility: $1. Check not performed; capability Unknown."
        return 0
    fi
    timeout --signal=TERM --kill-after=2s 10s "$@" 2>&1 |
        head -c 32768 | head -n 200 | cat -v
    rc=${PIPESTATUS[0]}
    note "Command exit status: $rc (124/137: timeout; 141 may be output cap)."
    if (( rc != 0 )); then
        note 'Failed/incomplete check: inspect diagnostic above; cause and underlying capability remain unresolved unless explicitly established.'
    else
        note 'Observed command completion; empty output is not proof of absent activity or complete access.'
    fi
    return 0
}

privileged_read() {
    local label=$1
    shift
    # Compare argument boundaries, not a joined command string. A PID-scoped
    # query must match this script's positive numeric controlled-child PID.
    if { (( $# == 2 )) && [[ $1 == auditctl && ( $2 == -s || $2 == -l ) ]]; } ||
       { (( $# == 3 )) && [[ $1 == journalctl && $2 == --no-pager && $3 == --disk-usage ]]; } ||
       { (( $# == 8 )) && [[ $1 == ausearch && $2 == -m && $3 == EXECVE &&
           $4 == -x && $5 == /usr/bin/sleep && $6 == -ts && $7 == recent && $8 == --raw ]]; } ||
       { (( $# == 8 )) && [[ $1 == ausearch && $2 == -p && $3 =~ ^[1-9][0-9]*$ &&
           $3 == "${TEST_PID:-}" && $4 == -m && $5 == EXECVE &&
           $6 == -ts && $7 == recent && $8 == --raw ]]; }; then
        :
    else
        note 'Internal error: privileged read not allowlisted.'
        return 0
    fi
    if (( PRIVILEGED )); then
        if have sudo; then
            if [[ ${SUDO_READY:-unknown} == unknown ]]; then
                printf 'Authorizing optional read-only probes with sudo (no credential invalidation).\n' >&3
                if sudo -v 2>&3; then SUDO_READY=yes; else SUDO_READY=no; fi
            fi
            if [[ $SUDO_READY == yes ]]; then
                record "$label (sudo read only)" sudo -n -- "$@"
            else
                note "$label: sudo authorization failed; privileged comparison not investigated."
            fi
        else
            note 'sudo unavailable; privileged check not investigated.'
        fi
    else
        note "$label: elevated comparison not investigated (use --privileged)."
    fi
}

environment_info() {
    section 'OS and kernel (no hostname or machine ID)'
    record 'OS release' cat /etc/os-release
    record 'Kernel release and architecture' uname -s -r -m
    record 'systemd version' systemctl --version
    record 'Journal client build version (not proof of daemon version)' journalctl --version
    note 'journald ships with systemd; package version below is context, not independent runtime attestation.'
    record 'Installed source packages' dpkg-query -W '-f=${binary:Package} ${Version} ${db:Status-Status}\n' systemd auditd
}

audit_info() {
    record 'auditd service properties (no service log tail)' systemctl show auditd.service -p LoadState -p ActiveState -p SubState
    record 'Audit status as ordinary observer' auditctl -s
    record 'Current active Audit rules as ordinary observer' auditctl -l
    privileged_read 'Audit subsystem status' auditctl -s
    privileged_read 'Active Audit rules' auditctl -l
    note 'Active rules are not a dump of persistent rule files; no configuration is changed. Missing auditctl is not proof of missing kernel Audit.'
}

kernel_info() {
    local config=/boot/config-$(uname -r) base file
    section 'Kernel build configuration'
    if [[ -r $config ]]; then
        record 'Selected running-kernel config entries' grep -E '^(CONFIG_(CONNECTOR|PROC_EVENTS|BPF|BPF_SYSCALL|TRACEPOINTS|FTRACE)=|# CONFIG_(CONNECTOR|PROC_EVENTS|BPF|BPF_SYSCALL|TRACEPOINTS|FTRACE) is not set)' "$config"
    elif [[ -r /proc/config.gz ]] && have zcat; then
        record 'Selected compressed kernel config entries' bash -c 'set -o pipefail; zcat /proc/config.gz | grep -E "^(CONFIG_(CONNECTOR|PROC_EVENTS|BPF|BPF_SYSCALL|TRACEPOINTS|FTRACE)=|# CONFIG_(CONNECTOR|PROC_EVENTS|BPF|BPF_SYSCALL|TRACEPOINTS|FTRACE) is not set)"'
    else
        note 'Kernel config unavailable/inaccessible at standard paths; support Unknown, not unsupported.'
    fi
    note 'An explicit not-set entry is build evidence of disabled support; missing entries or read failures are Unknown. Build support does not establish runtime usability.'
    record 'Existing proc/trace/debug mounts' findmnt -rn -t proc,tracefs,debugfs -o TARGET,FSTYPE,OPTIONS
    for base in /sys/kernel/tracing /sys/kernel/debug/tracing; do
        record "Path access: $base" stat -c '%A %u:%g %n' "$base"
        for file in events/sched/sched_process_exec/id events/sched/sched_process_exec/format events/sched/sched_process_fork/id events/sched/sched_process_exit/id; do
            record "Tracepoint metadata: $base/$file" cat "$base/$file"
        done
    done
    note 'Tracepoint read failure does not establish nonexistence: mounts, search permissions and access restrictions can hide it. Elevated tracefs reads are deliberately not attempted.'
    record 'bpftool availability/version only' bpftool version
    note 'Not investigated: connector subscription/delivery, BPF loading, runtime tracing, tracepoint enabling or execution-history completeness. No kernel interface is activated.'
}

finish_report() {
    section 'Important limitations / interpretation'
    note 'These are bounded research observations, not HIDS coverage, ECS mappings or normalized events.'
    note 'Not observed in this sample is distinct from not emitted, inaccessible, unavailable, unsupported and not investigated. Interpret diagnostics manually.'
    note 'Root access does not test future service-account access. Same-user proc access says nothing about other users.'
    note 'Reports may contain sensitive paths, rule keys and account identifiers. Review/redact a separate copy before sharing; never commit raw reports.'
    note "Collection end (UTC): $(stamp)"
}
