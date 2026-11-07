#!/usr/bin/env bash
# Offline native regressions plus actual synthetic Unix-socket integration. No netlink subscription.
set -euo pipefail
if [[ $(id -u) == 0 ]]; then
    echo 'FAIL: run as an ordinary user, never sudo' >&2
    exit 77
fi
if [[ $(uname -s) != Linux ]]; then
    echo 'FAIL: this acceptance runner requires Ubuntu/Linux' >&2
    exit 77
fi
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$repo_dir"
umask 077
build_dir=$(mktemp -d /tmp/hids-m1-build.XXXXXXXX)
export PYTHONDONTWRITEBYTECODE=1
export HIDS_M1_PRODUCER="$build_dir/m1_producer"
compiler=${CXX:-c++}
command -v "$compiler"
"$compiler" --version
uname -rm
python3 -B - <<'PY'
from pathlib import Path
import hashlib,json,os,platform,sqlite3,sys
from engine.ingestion.m1_security import ordinary_user,private_directory
ordinary_user()
private_directory(Path(os.environ['HIDS_M1_PRODUCER']).parent, require_linux=True)
if sys.version_info < (3,10) or sqlite3.sqlite_version_info < (3,22,0):
    raise SystemExit('FAIL: unsupported Python/SQLite version')
release={}
for line in Path('/etc/os-release').read_text().splitlines():
    if '=' in line:
        key,value=line.split('=',1)
        release[key]=value.strip('"')
if platform.machine()!='aarch64' or release.get('ID')!='ubuntu' or release.get('VERSION_ID')!='26.04':
    raise SystemExit('FAIL: acceptance requires Ubuntu 26.04 ARM64; do not relabel another environment')
print('OS',release.get('PRETTY_NAME','Ubuntu 26.04'))
print('Python',sys.version.split()[0],'SQLite',sqlite3.sqlite_version)
manifest=Path('M1_SOURCE_MANIFEST.json')
if manifest.exists():
    files=json.loads(manifest.read_text())['files']
    root=Path.cwd().resolve()
    for name,wanted in files.items():
        relative=Path(name)
        target=root/relative
        if relative.is_absolute() or '..' in relative.parts or not target.resolve().is_relative_to(root) or target.is_symlink():
            raise SystemExit('FAIL: unsafe transfer manifest path')
        if hashlib.sha256(target.read_bytes()).hexdigest()!=wanted:
            raise SystemExit('FAIL: transferred source differs: '+name)
    print('Source manifest verified:',len(files),'files; SHA-256',hashlib.sha256(manifest.read_bytes()).hexdigest())
for name,wanted in [('json.hpp','aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63'),
                    ('LICENSE.MIT','46a65cffd1ea955132d95a8dd921640714a8d6b537d2e4e482d31145ae95b603'),
                    ('PROVENANCE.md','b9f053dd87b9d2289d075aabce9421b5e15dea2614f23f2a712929ceaaf41600')]:
    actual=hashlib.sha256((Path('collector/third_party/nlohmann')/name).read_bytes()).hexdigest()
    if actual!=wanted: raise SystemExit('FAIL: dependency digest '+name)
    print(name,actual)
PY
flags=(-std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include -I collector/third_party)
if [[ ${1:-} == --sanitize ]]; then
    printf 'int main() { return 0; }\n' > "$build_dir/sanitizer_probe.cpp"
    if ! "$compiler" -fsanitize=address,undefined "$build_dir/sanitizer_probe.cpp" -o "$build_dir/sanitizer_probe"; then
        echo 'FAIL: requested sanitizer support unavailable; nothing installed' >&2
        exit 1
    fi
    "$build_dir/sanitizer_probe"
    flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
elif [[ $# != 0 ]]; then
    echo 'Usage: bash tests/integration/validate_m1.sh [--sanitize]' >&2
    exit 64
fi
for unit in process_collector process_connector_protocol linux_process_connector; do
    "$compiler" "${flags[@]}" -c "collector/src/$unit.cpp" -o "$build_dir/$unit.o"
done
"$compiler" "${flags[@]}" collector/src/process_collector.cpp collector/src/process_connector_protocol.cpp tests/unit/process_collector_test.cpp -o "$build_dir/process_collector_test"
"$build_dir/process_collector_test"
"$compiler" "${flags[@]}" collector/src/process_connector_protocol.cpp tests/unit/linux_process_connector_test.cpp -o "$build_dir/linux_process_connector_test"
"$build_dir/linux_process_connector_test"
"$compiler" "${flags[@]}" collector/src/process_collector.cpp collector/src/process_connector_protocol.cpp collector/src/linux_process_connector.cpp tests/unit/process_collector_link_smoke.cpp -o "$build_dir/process_collector_link_smoke"
"$build_dir/process_collector_link_smoke"
"$compiler" "${flags[@]}" collector/src/pilot/contract.cpp collector/src/pilot/transport.cpp tests/unit/m1_contract_test.cpp -o "$build_dir/m1_contract_test"
"$build_dir/m1_contract_test" tests/fixtures/process/m1-exec-envelope.json tests/fixtures/process/m1-contract-cases.json
"$compiler" "${flags[@]}" collector/src/pilot/contract.cpp collector/src/process_connector_protocol.cpp tests/integration/m1_native_fixture.cpp tests/unit/m1_native_fixture_test.cpp -o "$build_dir/m1_native_fixture_test"
"$build_dir/m1_native_fixture_test" tests/fixtures/process/synthetic-exec-001.json
"$compiler" "${flags[@]}" collector/src/pilot/contract.cpp collector/src/pilot/transport.cpp collector/src/process_connector_protocol.cpp tests/integration/m1_native_fixture.cpp tests/integration/m1_producer.cpp -o "$HIDS_M1_PRODUCER"
python3 -B - <<'PY'
from pathlib import Path
import hashlib,os
print('Built producer SHA-256',hashlib.sha256(Path(os.environ['HIDS_M1_PRODUCER']).read_bytes()).hexdigest())
PY
python3 -B -m unittest discover -s tests/unit -p 'test_m1_python.py' -v
python3 -B -m unittest discover -s tests/integration -p 'test_m1_harness_policy.py' -v
python3 -B -m unittest discover -s tests/integration -p 'test_m1_integration.py' -v
python3 -B tests/integration/run_m1.py --producer "$HIDS_M1_PRODUCER"
echo "PASS: acceptance runner completed; private build artifacts: $build_dir"
