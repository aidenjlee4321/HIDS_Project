# Development workflow

These standard-library tools automate **source snapshots and offline tests only**.
They do not deploy HIDS, authorize sources, read the live journal, install packages,
change memberships/permissions, or use Git. M1/M2 production implementation and existing contracts are unchanged.

## Initial setup

Use the existing Python 3.9+ and Bash on macOS. The Ubuntu wrapper requires the
existing Ubuntu 26.04 ARM64 compiler/C++20, Python 3.10+, SQLite 3.22+ and
libsystemd development header/link library. Missing prerequisites fail; nothing is
installed. Local native regressions still need the **previously prepared** Linux
UAPI headers and macOS shim:

```sh
export HIDS_NATIVE_UAPI=/absolute/path/to/existing/include/uapi
export HIDS_NATIVE_SHIM=/absolute/path/to/existing/mac-shim.h
```

No headers/shims are downloaded by this workflow. Follow
[existing validation guidance](../tests/integration/M2-README.md).

The canonical repository defaults to the script's parent repository. Local state
is outside it, at `~/.local/state/hids-dev`; override `HIDS_DEV_STATE` or
`--state-dir`. Each new directory in the private state hierarchy is created with mode 0700,
including missing intermediate directories. Existing state directories must be
owned by the invoking user with exactly mode 0700; symlinks are rejected before
use. Automation never chmods or repairs an existing directory. Public existing
ancestors outside the configured private state root need not be mode 0700.

If the default state is incorrectly permissioned, leave it and its evidence intact.
Choose a fresh, unused private state path for the entire next cycle, for example:

```sh
export HIDS_DEV_STATE=/private/tmp/hids-dev-next-cycle-unique-name
python3 scripts/dev.py test
python3 scripts/dev.py snapshot
# Transfer only when separately authorized:
python3 scripts/dev.py transfer
```

Use the same override for later status/report commands. Partial initialization
retains private directories; retry rechecks them without permission repair.
 The shared folder is discovered among existing
`Desktop/Downloads/Documents/CCDC-Transfer` directories. It is currently at
`/Users/aidenlee/Desktop/CCDC-Transfer`; override `HIDS_TRANSFER_DIR` or `--share`
when needed. Multiple/missing candidates require an explicit choice.

Optional shell-session shorthand (no installation or shell-file edits required):

```sh
alias hids-dev='python3 /Users/aidenlee/Downloads/hids/scripts/dev.py'
```

## Normal cycle

From the canonical repository:

```sh
python3 scripts/dev.py test
python3 scripts/dev.py snapshot
python3 scripts/dev.py transfer
python3 scripts/dev.py status
```

Use `test --sanitize` for ASan/UBSan. `test` invokes the M2 offline runner
(which includes native/M1 suites), then workflow unit tests. It preserves stdout
and stderr separately, aggregate exit codes, explicitly wrapped command exit
codes and skip details in private `state/runs/<run>/`. The DEBUG trap is not used:
a completed control construct's status is not the status of its predicate. `hids_run` records the invoked command's result directly;
ERR records unwrapped failures and EXIT records the shell aggregate separately.
Unwrapped conditions and branches that never execute receive no claimed result.
Shell UID/EUID/GID/EGID are printed explicitly, and the report records the Python
validator's UID/EUID/GID/EGID. The runner's phase exit code determines failure.
A local pass with Linux skips is explicitly `passed_with_skips`, never Ubuntu acceptance.

Snapshots use unique UTC/random names under `state/snapshots/`. `--name` selects an
explicit name for creation or transfer; transfer defaults to the latest local
snapshot. Never reuse names. `bash scripts/create_snapshot.sh snapshot` and
`... transfer` delegate to the same implementation.

The source allowlist includes C++/Python/shell sources, fixtures, docs, service/socket/
config source artifacts and licenses across existing component directories.
Hidden files, caches, build/dependency trees, raw TXT reports and binaries are
excluded. Symlinks/special files/hardlinks in selected sources are rejected; files
above 32 MiB require reviewing the automation policy. This is not a package/install
bundle and contains no generated runtime data.

Every source file is SHA-256 compared to the canonical source during creation.
`SOURCE_MANIFEST.json` lists the complete file inventory; `SOURCE_MANIFEST.sha256`
contains its digest. Snapshots contain independent regular files, never symlinks
or hardlinks. Their source byte hashes and exact file/directory inventory are
checked before/after transfer. Immutability means append-only tooling plus
verification: no read-only permissions are imposed or existing files chmodded.
Do not edit a snapshot. Canonical changes after creation require a new snapshot.

Transfer creates only:

```text
CCDC-Transfer/collector-validation/snapshots/<snapshot-id>/
```

Previous M1 snapshots, research and unrelated contents remain untouched. Duplicate
destinations fail even if empty. Interrupted copies remain invalid for inspection;
no automatic delete/overwrite/repair is performed. Choose a new snapshot name.

## Ubuntu offline validation

After separate authorization to run on Ubuntu, use the ordinary VM user:

```sh
cd /mnt/ccdc-transfer/collector-validation/snapshots/<snapshot-id>
bash tests/integration/validate_ubuntu.sh
```

Optionally add `--expected-manifest <Mac-printed-SHA256>` and `--sanitize`.
The wrapper verifies inventory/hash integrity **before** dependency probes or
regressions. It checks ordinary-user/platform/dependency prerequisites, compiles
but does not run a tiny libsystemd link probe, and delegates tests to the existing
M2 offline runner. Production entry points execute only their `--help` paths.
Unexpected skipped tests make Ubuntu results `incomplete` with a nonzero exit.
No service accounts, source activation or journal access are needed.

Only the Linux M1 integration-test subprocess uses the test-only
`tests/integration/m1_capability_launcher.py`. It requires existing `setpriv`
(util-linux); missing tools or failed verification fail validation without installs
or fallback. It allows only zero effective/permitted/ambient capabilities and an
inheritable set of zero or solely the previously observed `cap_wake_alarm` bit.
It executes `setpriv --inh-caps=-all --no-new-privs`, then verifies in the actual
test interpreter that all four UID/GID values and supplementary groups are
preserved, effective/permitted/inheritable/ambient sets are zero, the bounding
set is unchanged and NoNewPrivs is 1. It requires all 12 integration tests to run
without skips. The parent process is unchanged; no privileges are granted and
M1's original security checks remain intact. macOS retains its explicit Linux
integration skips. Local mocked launcher tests do not demonstrate Linux capset
behavior; that requires the next ordinary-user Ubuntu offline run.

Full logs/report/build artifacts remain in private VM local storage, default
`/tmp/hids-dev-results/<run>/`; use `--output` to retain them elsewhere on the VM's
local filesystem. Temporary build paths printed by the existing runner remain
private too. Keep output off the source tree and the shared filesystem.

When running from the recognized shared `collector-validation/snapshots/` layout,
the wrapper publishes **only a machine-readable summary and its hash** to sibling
`collector-validation/reports/<run>/`. It never publishes full logs automatically.
Use `--no-publish` to disable or `--share` to choose the existing transfer root.
If publication fails, tests/logs remain private and the command reports failure;
review and transfer the summary pair manually. No source snapshot is changed.

## Retrieve results

Back on macOS:

```sh
python3 scripts/dev.py report
python3 scripts/dev.py status
```

`report` verifies summary hashes and binds them to a locally pinned snapshot
manifest before importing into private state. Unknown/conflicting snapshots,
contradictory passing reports and malformed metadata fail closed. Reports identify
phase exits, skips and private VM log locations. Summaries are owner-supplied test
evidence, not signed attestations; hashes detect mismatches but do not authenticate
a malicious host or modified verifier. Compare the printed manifest digest across
the handoff when stronger assurance is needed.

No reports means **unvalidated**, not success. Review private stdout/stderr on the
VM for failures; transfer reviewed logs separately if necessary. Do not infer live
source functionality, service-account permissions or production readiness from an
offline pass.

## Troubleshooting and authorization

- Integrity/inventory errors: correct canonical files and create a new snapshot.
- Missing compiler/SDK/shim: report what is absent; obtain approval before installs.
- Read-only share or ownership mapping issues: retain private reports; do not sudo,
  chmod, or reconfigure the share automatically.
- Failed build/test: inspect the corresponding `.stdout.log`, `.stderr.log` and
  command exit records in `validation.json`.
- Partial/duplicate transfer: preserve it and use a new snapshot name.

Actual deployment, account/group setup, permission changes, service starts, live
Ubuntu journal integration and source activation still require explicit separate
authorization. Creating this automation does not run the Ubuntu VM or those actions.
