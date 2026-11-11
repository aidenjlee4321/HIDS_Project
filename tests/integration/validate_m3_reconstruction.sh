#!/usr/bin/env bash
# Native structural fixtures only. No source opening, accounts, sockets or SQL.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$repo_dir"
umask 077
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/hids-m3-reconstruction.XXXXXXXX")
flags=(-std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include)
case ${1:-} in
    '') ;;
    --sanitize) flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer) ;;
    *) echo 'Usage: bash tests/integration/validate_m3_reconstruction.sh [--sanitize]' >&2; exit 64 ;;
esac
sources=()
libraries=()
if [[ ${HIDS_M3_AUPARSE:-0} == 1 ]]; then
    flags+=(-DHIDS_M3_AUPARSE)
    if [[ -n ${HIDS_AUDIT_INCLUDE_DIR:-} ]]; then flags+=(-I "$HIDS_AUDIT_INCLUDE_DIR"); fi
    sources+=(collector/src/audit/auparse_execution.cpp)
    libraries+=("${HIDS_AUPARSE_LIBRARY:--lauparse}")
fi
"${CXX:-c++}" "${flags[@]}" \
    collector/src/audit/record_parser.cpp collector/src/audit/event_assembler.cpp \
    collector/src/audit/execve_validation.cpp collector/src/audit/execution.cpp \
    collector/src/audit/plugin_input.cpp collector/src/audit/plugin_session.cpp \
    collector/src/audit/current_tail.cpp \
    tests/unit/m3_audit_reconstruction_test.cpp ${sources[@]+"${sources[@]}"} ${libraries[@]+"${libraries[@]}"} -o "$build_dir/m3-reconstruction-test"
"$build_dir/m3-reconstruction-test"
printf 'Private offline build artifacts: %s\n' "$build_dir"
