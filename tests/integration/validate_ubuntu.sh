#!/usr/bin/env bash
# Offline only. Results are outside the immutable snapshot. No sudo or installs.
set -euo pipefail
if [[ $(id -u) == 0 ]]; then echo 'Run as an ordinary user, never sudo' >&2; exit 77; fi
if [[ $(uname -s) != Linux ]]; then echo 'Ubuntu validation requires Linux' >&2; exit 77; fi
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
exec python3 -B "$repo_dir/scripts/dev.py" _validate --repo "$repo_dir" "$@"
