#!/usr/bin/env bash
set -u
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 1
source "$SCRIPT_DIR/common/utilities.sh"
TEST_PID=
cleanup() {
    # Only our still-running Bash child job; never pkill/killall or a process group.
    local child
    if [[ -n $TEST_PID ]]; then
        for child in $(jobs -pr); do
            if [[ $child == "$TEST_PID" ]]; then
                kill -TERM "$TEST_PID" 2>/dev/null || :
                wait "$TEST_PID" 2>/dev/null || :
                break
            fi
        done
        TEST_PID=
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
init_report process-research 'Compare existing process evidence with one controlled same-user sleep snapshot; activate no telemetry.' "$@"
rc=$?; (( rc == 2 )) && exit 0; (( rc == 0 )) || exit "$rc"
environment_info
audit_info
record 'Baseline: recent existing Audit EXECVE events for literal /usr/bin/sleep' ausearch -m EXECVE -x /usr/bin/sleep -ts recent --raw
privileged_read 'Baseline: recent existing Audit EXECVE events for literal /usr/bin/sleep' ausearch -m EXECVE -x /usr/bin/sleep -ts recent --raw
note 'Baseline only, collected before child creation: recent means the ausearch recent window (normally ten minutes). The literal executable filter may miss records using a resolved path. Matching multi-record events may include arguments/context; previous sleep invocations may match. This is not evidence for the controlled execution or an all-process history.'
section 'Controlled process snapshot — ordinary user only'
if [[ -x /usr/bin/sleep ]]; then
    EXPECTED_EXE=
    section 'Resolve expected executable before child creation'
    note "Check time: $(stamp)"
    note 'Command: readlink -f -- /usr/bin/sleep'
    if have readlink && EXPECTED_EXE=$(readlink -f -- /usr/bin/sleep) && [[ $EXPECTED_EXE == /* ]]; then
        note "Observed resolved expected executable: $EXPECTED_EXE"
    else
        EXPECTED_EXE=
        note 'Executable resolution failed/unavailable; expected executable Unknown. Exec cannot be confirmed; executable-filtered journal check will be skipped.'
    fi
    START=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
    /usr/bin/sleep 3600 &
    TEST_PID=$!
    EXEC_CONFIRMED=0
    OBSERVED_EXE=
    if [[ -n $EXPECTED_EXE ]]; then
        note "Polling command: readlink -f -- /proc/$TEST_PID/exe (up to 20 attempts, 0.05-second pauses)."
        # Bounded wait for the forked Bash child to exec the resolved sleep binary.
        for attempt in {1..20}; do
            OBSERVED_EXE=$(readlink -f -- "/proc/$TEST_PID/exe" 2>/dev/null) || OBSERVED_EXE=
            if [[ $OBSERVED_EXE == "$EXPECTED_EXE" ]]; then
                EXEC_CONFIRMED=1
                break
            fi
            /usr/bin/sleep 0.05
        done
    fi
    if (( EXEC_CONFIRMED )); then
        note "Exec confirmation: Observed expected executable for child PID=$TEST_PID: $OBSERVED_EXE"
    elif [[ -n $EXPECTED_EXE ]]; then
        note "Exec confirmation: NOT confirmed after 20 polls; expected=$EXPECTED_EXE; last readable path=${OBSERVED_EXE:-Unknown}. Access failure, child exit or scheduling may explain this; remaining reads are unconfirmed child snapshots."
    else
        note 'Exec confirmation: NOT investigated because expected executable resolution failed; remaining reads are unconfirmed child snapshots.'
    fi
    note "Created direct child PID=$TEST_PID, parent=$$, argv=/usr/bin/sleep 3600; start observation=$START"
    record 'Selected child status: UID/GID order real/effective/saved/filesystem' grep -E '^(Name|State|Tgid|Pid|PPid|Uid|Gid|Groups|Threads|NSpid):' "/proc/$TEST_PID/status"
    record 'Child executable' readlink "/proc/$TEST_PID/exe"
    record 'Child arguments (NUL-separated converted to lines)' bash -c 'tr "\000" "\n" < "$1"' _ "/proc/$TEST_PID/cmdline"
    record 'Child raw stat (field 22: start ticks since boot)' cat "/proc/$TEST_PID/stat"
    record 'Clock ticks per second' getconf CLK_TCK
    record 'Boot time for interpreting start ticks (no boot ID)' grep '^btime ' /proc/stat
    record 'Child ps summary' ps -p "$TEST_PID" -o pid=,ppid=,comm=,stat=,nlwp=,lstart=,etimes=
    record 'Controlled child: PID-specific Audit EXECVE query (ordinary observer)' ausearch -p "$TEST_PID" -m EXECVE -ts recent --raw
    privileged_read 'Controlled child: PID-specific Audit EXECVE query' ausearch -p "$TEST_PID" -m EXECVE -ts recent --raw
    note 'Controlled PID query is separate from the pre-experiment baseline. Recent is not a boot/time-unique identity: inspect event timestamps and context before attributing matches; delayed Audit writes may be missed. No matches do not establish that execution was not recorded.'
    END=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
    if [[ -n $EXPECTED_EXE ]]; then
        record 'Scoped current-boot journal records for child and resolved executable' journalctl --no-pager -b --since "$START" --until "$END" -n 30 -o json --output-fields=__REALTIME_TIMESTAMP,__MONOTONIC_TIMESTAMP,_PID,_COMM,_EXE,MESSAGE "_PID=$TEST_PID" "_EXE=$EXPECTED_EXE"
        note 'Journal filters are ANDed; PID alone is not durable identity. No matching records does not prove no execution or no journal access. An emitting-process record is not necessarily an execution event. Querying an expected executable does not itself confirm exec.'
    else
        note 'Executable-filtered journal check not investigated: expected executable path unresolved; no guessed _EXE filter used.'
    fi
    cleanup
else
    note '/usr/bin/sleep unavailable/not executable; controlled experiment not performed.'
fi
kernel_info
finish_report
