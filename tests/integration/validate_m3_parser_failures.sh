#!/usr/bin/env bash
# Test-only allocation/API faults against a sanitized fixture. No native sources.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$repo_dir"
umask 077
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/hids-m3-parser-failures.XXXXXXXX")
flags=(-std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include)
case ${1:-} in
    '') ;;
    --sanitize) flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer) ;;
    *) echo 'Usage: bash tests/integration/validate_m3_parser_failures.sh [--sanitize]' >&2; exit 64 ;;
esac
sources=()
libraries=()
if [[ ${HIDS_M3_AUPARSE:-0} == 1 ]]; then
    flags+=(-DHIDS_M3_AUPARSE)
    if [[ -n ${HIDS_AUDIT_INCLUDE_DIR:-} ]]; then flags+=(-I "$HIDS_AUDIT_INCLUDE_DIR"); fi
    sources+=(collector/src/audit/auparse_execution.cpp)
    libraries+=("${HIDS_AUPARSE_LIBRARY:--lauparse}")
    for symbol in init next_event first_record next_record first_field next_field get_record_text get_type_name get_field_name get_field_str; do
        libraries+=("-Wl,--wrap=auparse_$symbol")
    done
fi
"${CXX:-c++}" "${flags[@]}" \
    collector/src/audit/record_parser.cpp collector/src/audit/event_assembler.cpp \
    collector/src/audit/execve_validation.cpp collector/src/audit/execution.cpp \
    collector/src/audit/plugin_input.cpp collector/src/audit/plugin_session.cpp \
    tests/unit/m3_parser_failure_test.cpp ${sources[@]+"${sources[@]}"} ${libraries[@]+"${libraries[@]}"} \
    -o "$build_dir/m3-parser-failures"
"$build_dir/m3-parser-failures"
printf 'Retained private test binary: %s\n' "$build_dir"
