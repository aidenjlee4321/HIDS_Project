#!/usr/bin/env bash
# Sanitized generated boundary cases only; never opens an Audit source.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$repo_dir"
umask 077
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/hids-m3-native-contract.XXXXXXXX")
flags=(-std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include)
case ${1:-} in
    '') ;;
    --sanitize) flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer) ;;
    *) echo 'Usage: bash tests/integration/validate_m3_native_contract.sh [--sanitize]' >&2; exit 64 ;;
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
    tests/unit/m3_native_contract_test.cpp ${sources[@]+"${sources[@]}"} ${libraries[@]+"${libraries[@]}"} \
    -o "$build_dir/m3-native-contract"
"$build_dir/m3-native-contract" "$build_dir/results.tsv"
printf 'Retained private binary and case report: %s\n' "$build_dir"
