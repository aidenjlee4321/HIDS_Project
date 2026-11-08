#!/usr/bin/env bash
# Fixture/offline checks only. Never starts a service or opens a live journal.
set -euo pipefail
# The development wrapper provides traced execution; direct runs remain valid.
if ! declare -F hids_run >/dev/null; then
    hids_run() { "$@"; }
fi
if [[ $(id -u) == 0 ]]; then echo 'Run as an ordinary user, never sudo' >&2; exit 77; fi
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$repo_dir"
umask 077
export PYTHONDONTWRITEBYTECODE=1
build_dir=$(mktemp -d /tmp/hids-m2-offline.XXXXXXXX)
compiler=${CXX:-c++}
flags=(-std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include -I collector/third_party)
case ${1:-} in
    --sanitize) flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer) ;;
    '') ;;
    *) echo 'Usage: bash tests/integration/validate_m2_offline.sh [--sanitize]' >&2; exit 64 ;;
esac
if [[ $# -gt 1 ]]; then exit 64; fi
native_flags=()
systemd_flags=()
if [[ $(uname -s) == Darwin ]]; then
    : "${HIDS_NATIVE_UAPI:?Set existing temporary Linux UAPI include path for offline native regression tests}"
    : "${HIDS_NATIVE_SHIM:?Set existing macOS native-regression shim path}"
    native_flags=(-isystem "$HIDS_NATIVE_UAPI" -include "$HIDS_NATIVE_SHIM")
else
    systemd_flags=(-lsystemd)
fi
hids_run "$compiler" --version
hids_run python3 -B -c 'import platform,sqlite3,sys;print(platform.platform());print(sys.version);print("SQLite",sqlite3.sqlite_version)'
hids_run "$compiler" "${flags[@]}" ${native_flags[@]+"${native_flags[@]}"} collector/src/process_collector.cpp collector/src/process_connector_protocol.cpp tests/unit/process_collector_test.cpp -o "$build_dir/native"
hids_run "$build_dir/native"
hids_run "$compiler" "${flags[@]}" ${native_flags[@]+"${native_flags[@]}"} collector/src/process_connector_protocol.cpp tests/unit/linux_process_connector_test.cpp -o "$build_dir/backend"
hids_run "$build_dir/backend"
hids_run "$compiler" "${flags[@]}" ${native_flags[@]+"${native_flags[@]}"} collector/src/process_collector.cpp collector/src/process_connector_protocol.cpp collector/src/linux_process_connector.cpp tests/unit/process_collector_link_smoke.cpp -o "$build_dir/link_smoke"
hids_run "$build_dir/link_smoke"
hids_run "$compiler" "${flags[@]}" collector/src/pilot/contract.cpp collector/src/pilot/transport.cpp tests/unit/m1_contract_test.cpp -o "$build_dir/m1_contract"
hids_run "$build_dir/m1_contract" tests/fixtures/process/m1-exec-envelope.json tests/fixtures/process/m1-contract-cases.json
# Keep the macOS Linux shim out of M1/M2 socket transport translation units.
hids_run "$compiler" "${flags[@]}" ${native_flags[@]+"${native_flags[@]}"} collector/src/process_connector_protocol.cpp tests/integration/m1_native_fixture.cpp tests/unit/m1_native_fixture_test.cpp collector/src/pilot/contract.cpp -o "$build_dir/m1_native"
hids_run "$build_dir/m1_native" tests/fixtures/process/synthetic-exec-001.json
m2=(collector/src/pilot/contract.cpp collector/src/pilot/transport.cpp collector/src/journal/contract.cpp collector/src/journal/transport.cpp collector/src/journal_collector.cpp)
hids_run "$compiler" "${flags[@]}" "${m2[@]}" collector/src/journal/linux_journal_io.cpp tests/unit/m2_journal_test.cpp ${systemd_flags[@]+"${systemd_flags[@]}"} -o "$build_dir/m2_unit"
hids_run "$build_dir/m2_unit" tests/fixtures/journal/ssh-event.json tests/fixtures/journal/contract-cases.json
hids_run "$compiler" "${flags[@]}" "${m2[@]}" tests/integration/m2_fixture_producer.cpp -o "$build_dir/m2_fixture"
export HIDS_M2_FIXTURE_PRODUCER="$build_dir/m2_fixture"
hids_run "$compiler" "${flags[@]}" "${m2[@]}" collector/src/journal/runtime.cpp tests/unit/m2_runtime_test.cpp -o "$build_dir/m2_runtime_unit"
hids_run "$build_dir/m2_runtime_unit" tests/fixtures/journal/ssh-event.json
hids_run "$compiler" "${flags[@]}" "${m2[@]}" collector/src/journal/runtime.cpp tests/integration/m2_runtime_fixture.cpp -o "$build_dir/m2_runtime_fixture"
export HIDS_M2_RUNTIME_FIXTURE="$build_dir/m2_runtime_fixture"
hids_run "$compiler" "${flags[@]}" "${m2[@]}" collector/src/journal/runtime.cpp collector/src/journal/linux_journal_io.cpp collector/src/journal/reader_main.cpp ${systemd_flags[@]+"${systemd_flags[@]}"} -o "$build_dir/m2-reader"
hids_run "$build_dir/m2-reader" --help
hids_run python3 -B -m engine.ingestion.m2_service --help
hids_run python3 -B -m engine.ingestion.m2_control --help
hids_run python3 -B -m unittest discover -s tests/unit -p 'test_offline_launch.py' -v
hids_run python3 -B -m unittest discover -s tests/unit -p 'test_m1_python.py' -v
hids_run python3 -B -m unittest discover -s tests/integration -p 'test_m1_harness_policy.py' -v
if [[ $(uname -s) == Linux ]]; then
    hids_run "$compiler" "${flags[@]}" collector/src/pilot/contract.cpp collector/src/pilot/transport.cpp collector/src/process_connector_protocol.cpp tests/integration/m1_native_fixture.cpp tests/integration/m1_producer.cpp -o "$build_dir/m1_producer"
    export HIDS_M1_PRODUCER="$build_dir/m1_producer"
fi
if [[ $(uname -s) == Linux ]]; then
    hids_run python3 -B tests/integration/m1_capability_launcher.py
else
    hids_run python3 -B -m unittest discover -s tests/integration -p 'test_m1_integration.py' -v
fi
hids_run python3 -B -m unittest discover -s tests/unit -p 'test_m2_python.py' -v
hids_run python3 -B -m unittest discover -s tests/integration -p 'test_m2_fixture_pipeline.py' -v

hids_run python3 -B -m unittest discover -s tests/integration -p 'test_m2_lifecycle.py' -v
hids_run python3 -B -m unittest discover -s tests/integration -p 'test_m2_runtime_processes.py' -v
printf 'Offline checks completed. Private artifacts: %s\n' "$build_dir"
printf 'Skips do not satisfy Linux acceptance; no live journal was opened.\n'
