# M2 component implementation checkpoint

**Recorded:** November 7, 2026
**Status:** Fixture-testable components; M2 incomplete; no Ubuntu acceptance authorized/performed

The owner authorized repository implementation, fixture testing and source-only
service artifacts under the [M2 specification](../implementation/m2-journald-spec.md).
No live journal, service deployment, host setup or real-record collection was used.
See the [offline runner and limitations](../../tests/integration/M2-README.md).

## Evidence

Local environment: macOS 14.5 ARM64, Apple Clang 15, Python 3.9.6, SQLite 3.43.2.
The owner previously verified Ubuntu libsystemd/runtime/header 259.9 and pkgconf
2.5.1; those prerequisites do not establish M2 compilation or runtime behavior.
The Linux libsystemd branch is not compiled against the real SDK on this host.

Implemented protocol 2 `m2.journal-ssh/0.1.0`, independent validators, exact SSH
filter pairs, injectable reader, native normalization, bounded pending/retry state,
Unix IPC/security primitives, Python-only atomic event/rejection/checkpoint storage
and read-only retrieval. Native process/M1 functionality is unchanged.

Local checks:

| Check | Result |
|---|---|
| Native collector/backend suites and complete production link smoke | Strict and ASan/UBSan passed; existing private UAPI shim, no live connector |
| All 62 M1 contract vectors | Strict and ASan/UBSan passed |
| M1 native fixture/parser/normalization | Strict and ASan/UBSan passed |
| M1 Python storage/contract | 17 passed |
| M1 harness policy | 3 passed |
| Existing Linux M1 two-process integration | 12 skipped on macOS; not new Linux acceptance |
| M2 C++ component suite | 35 shared vectors, exact filter-call sequence, normalization, pending identity, activation/boundary/rotation gap and fake-channel checks passed strictly and with ASan/UBSan |
| M2 Python contract/storage/socket suite | 17 passed, including SQLite faults before/after checkpoint/commit, immutable replay, durable rejection, explicit socket owner/group/mode verification and lost ACK |
| M2 synthetic two-process round trip | Passed locally; C++ normalization/socket → independent Python validation/SQLite → full read-only fixture equality; macOS peer double explicitly scoped |

Initial failures corrected: ambiguous unqualified test `transmit` call, strict
operator-parentheses warning, SQLite connection used from the wrong test thread,
and a test passing the LF delimiter into payload decoding. The offline shell
runner also required Bash 3-compatible handling of empty flag arrays. A temporary pathname
socket bind was sandbox-denied; the approved outside-sandbox fixture rerun passed.
The socket fixture now sets its own directory mode explicitly under `umask 077`.
These are local checks, not Ubuntu service or libsystemd evidence.

Exact commands are in `tests/integration/validate_m2_offline.sh`; optional sanitizer
mode adds `-fsanitize=address,undefined -fno-omit-frame-pointer`. Private temporary
logs/binaries remain outside the repository. No packages were installed.

## Known incomplete work

Production entry points and trusted activation/service orchestration remain
unwired; the unit/tmpfiles files are undeployable source artifacts. No existing
accounts/groups/permissions/services were changed. Additional Linux backend and
control-loop/fault coverage is needed before live acceptance. Actual reader UID
997/group access, cross-account IPC, tail-start races, empty journals, rotation,
revocation and recovery require separately authorized Ubuntu validation.

Do not claim M2 complete. First finish lifecycle orchestration and offline coverage
in the canonical repository, review service artifacts and storage budgets, then
obtain separate setup/live-testing authorization. Preserve all existing snapshots;
no transfer was made during this task.

## File inventory

New C++ files:

- `collector/include/hids/journal_collector.hpp`
- `collector/include/hids/journal/contract.hpp`
- `collector/include/hids/journal/transport.hpp`
- `collector/src/journal_collector.cpp`
- `collector/src/journal/contract.cpp`
- `collector/src/journal/transport.cpp`
- `collector/src/journal/linux_journal_io.cpp`

New Python files:

- `engine/ingestion/m2_contract.py`
- `engine/ingestion/m2_receiver.py`
- `engine/database/m2_store.py`

New source-only packaging files:

- `packaging/systemd/hids-journal.service`
- `packaging/systemd/hids-ingest.service`
- `packaging/systemd/hids-m2.tmpfiles.conf`

New fixtures/tests/documentation:

- `tests/fixtures/journal/ssh-event.json`
- `tests/fixtures/journal/contract-cases.json`
- `tests/unit/m2_journal_test.cpp`
- `tests/unit/test_m2_python.py`
- `tests/integration/m2_fixture_producer.cpp`
- `tests/integration/test_m2_fixture_pipeline.py`
- `tests/integration/validate_m2_offline.sh`
- `tests/integration/M2-README.md`
- `docs/validation/m2-component-validation.md`

Modified existing documentation only:

- `docs/implementation/m2-journald-spec.md`: approval scope, explicit socket setup
  and required SSH filter tests; no M1 changes.
- `docs/README.md`: component checkpoint reference.
