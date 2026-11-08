#!/usr/bin/env bash
# Source-only snapshot/transfer entry point. No package/service/permission changes.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
action=${1:-snapshot}
if [[ $# -gt 0 ]]; then shift; fi
case "$action" in
    snapshot|transfer) exec python3 -B "$script_dir/dev.py" "$action" "$@" ;;
    *) echo 'Usage: bash scripts/create_snapshot.sh [snapshot|transfer] [options]' >&2; exit 64 ;;
esac
