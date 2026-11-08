# M2 lifecycle and activation implementation

**Recorded:** November 7, 2026
**Status:** Production source entry points wired; offline validation only; M2 not accepted on Ubuntu

This follows the historical [component checkpoint](m2-component-validation.md)
and implements the lifecycle work authorized by the owner. It changes no M1
contract, fixture, regression test or validation evidence. No service was installed,
enabled or started, no account/group was created, and no live journal was opened.

## Entry points and activation

- `collector/src/journal/reader_main.cpp` builds `m2-reader`: Linux-only non-root
  service identity/group and executable-path verification, protected root-owned
  configuration, signal handling and `ReaderRuntime` orchestration.
- `engine/ingestion/m2_service.py` runs via `python3 -B -m engine.ingestion.m2_service`:
  separate ingestion identity, SQLite owner, data listener, root control listener,
  serialized control/event loop and bounded shutdown.
- `engine/ingestion/m2_control.py` is the root-only local activation/status client.
  It does not read logs, write SQLite, grant permissions or start any service.

Source units now reference these actual entry points. `hids-ingest.socket` defines
only a root-owned mode-0600 control socket at `/run/hids/control.sock`; systemd
passes its listening FD 3 to the unprivileged backend. The backend checks activation
FD metadata/path and Linux peer credentials before decoding control requests.
The client authenticates the systemd-created root listener; data IPC independently
checks the backend-created hids-ingest socket and reader credentials. See upstream
[descriptor inheritance](https://www.freedesktop.org/software/systemd/man/259/sd_listen_fds.html)
and [service socket configuration](https://raw.githubusercontent.com/systemd/systemd/v259/man/systemd.service.xml).

The systemd/tmpfiles files remain **source artifacts, not deployment authority**.
No unit has an Install section and Restart remains disabled. Later privileged setup
must establish the approved accounts/groups, paths, installed code and a protected
`/etc/hids/m2.json`. `packaging/m2-config.example.json` intentionally contains null
placeholders: an owner must supply the stable source UUID and measured storage
budgets. The programs reject placeholders; there are no invented production budgets.

After separately approved deployment, the operational sequence is root activation
followed by explicit reader-service start. Activation does not spawn services.
An inactive reader exits without opening the journal. Restart uses an existing
still-authorized interval; there is no background journal/service restart loop.

## Lifecycle and failure behavior

Root control activate/deactivate/status requests are serialized with event writes.
Ready control traffic is prioritized. Revocation commits before closing the reader
lease; later event submissions cannot commit. The reader checks authorization before
each bounded poll. A poll already issued before revocation may finish, but its result
cannot advance revoked progress. No claim of instantaneous cancellation inside a
kernel/library call is made.

One authenticated PID/connection owns the reader lease. Five-second incomplete
request/response inactivity expires it; partial bytes do not renew it. Ordinary
disconnect/crash/lease expiry preserves an anchored cursor and records an interruption,
without asserting lost events. Replacement readers authenticate and reconcile
persisted progress. A crash during uncommitted boundary initialization produces a
blocking gap rather than silently choosing a later tail. An empty-unanchored restart
is rejected before journal open and its gap is persisted. Equivalent saved cursors
are verified through the existing native interface.

Lost event ACK retries retain the exact pending bytes/identity/observation. Duplicate
receipts never rewind progress. Lost boundary ACK replay is accepted only for the
identical already-persisted boundary/timestamps; a different tail cannot replace it.
Native observation time is captured after the entry is obtained, rather than before
a blocking wait. Rotation with unprovable continuity stops and reports a gap.

Signal handlers only set cancellation flags. Reader polling/waits and backend
selector waits are cooperative and bounded; shutdown releases only owned sockets,
children and handles. SQLite lock waits use the existing timeout. Real disk stalls,
libsystemd behavior and service-manager shutdown still need Ubuntu validation; local
fixtures do not prove a hard real-time shutdown guarantee.

The ingestion loop caps four clients, one reader, one pending frame/response per
connection, 4096-byte receive chunks, 65536-byte event frames and 2048-byte responses.
It stops reads while an output is blocked. Storage/protocol failures stop event
acceptance and preserve root-only status diagnostics. Failed storage commits remain
unconfirmed; no attempt is made to repair/reuse uncertain state automatically.

## Tests and evidence

Host: macOS 14.5 ARM64, Apple Clang 15, Python 3.9.6, SQLite 3.43.2. Production
entry points were invoked only with `--help`; this does not open a journal or state
file. The native Linux/libsystemd branch and actual cross-account privileges remain
unverified. macOS fixture peer checks are explicit test doubles, never production
fallbacks. Linux credential policy negative tests use mocked values without account
or identity changes.

Exact build/test commands are in
[`validate_m2_offline.sh`](../../tests/integration/validate_m2_offline.sh). It builds
all entry points and fixtures with strict C++20 warnings, reruns native/M1 suites,
then runs M2 component, reader-runtime, service-loop and subprocess tests. Sanitizer
mode adds ASan/UBSan; it installs nothing. On macOS the unchanged native regressions
use the pre-existing private UAPI/shim paths; the shim is kept out of socket/runtime
translation units. Private binaries/databases/sockets stay outside the repository.

Coverage added:

- Root/reader activation denial, no pre-authorization journal opens.
- Activation/boundary/cancellation and ready-deactivation/event ordering races.
- Persistent empty state, real owned-child crash/restart, lease expiry and replacement.
- Lost event/boundary ACK, identical retries and conflicting tail refusal.
- Cursor invalidation/rotation and durable gap versus recoverable interruption.
- Commit uncertainty, cancellation, bounded cooperative shutdown and slow peers.
- Separate ingestion groups excluding root/journal privileges.
- Full fake-journal reader process → authenticated fixture IPC → Python SQLite →
  complete read-only fixture equality.

During development the new slow-peer assertion was corrected to include the
additional bounded revocation-reconciliation stage, and a misplaced inline comment
that hid a test closing brace was fixed. Existing M1 tests were not changed.
The complete sanitized runner passed locally: native collector/backend/link smoke,
62 M1 vectors/native fixture, 35 M2 vectors and reader lifecycle C++ suite;
17 M1 Python, 3 M1 policy, 17 M2 Python, 1 original M2 fixture pipeline,
15 lifecycle/security and 5 real owned-process fixture tests passed. Twelve Linux-
only M1 integration cases skipped on macOS. No sanitizer finding was reported.
The complete non-sanitized runner also passed with the same results. Private
build artifacts were retained at `/tmp/hids-m2-offline.pGi6UGee` (strict) and
`/tmp/hids-m2-offline.g59EYQqH` (ASan/UBSan).

## Remaining Ubuntu gates

Obtain separate authorization before Ubuntu execution or deployment. Then verify
GCC/libsystemd compilation and systemd unit syntax, approved account/GID/group and
root-owned configuration/FD setup, data/control permissions and real SO_PEERCRED.
Only separately authorized live testing may establish actual tail races, empty
journal semantics, rotation/vacuum, source readability, revocation/shutdown and
resource measurements. No current result establishes comprehensive or lossless
monitoring, production reliability or completed M2 acceptance.

An unclean ingestion crash may leave its pathname data socket behind. Startup
deliberately refuses that unexpected object rather than blindly unlinking it;
separately authorized operator cleanup may be needed. Normal shutdown removes
only the socket inode owned by that process. No automatic privileged cleanup or
service supervision has been introduced.

## Files created and modified

Created:

- `collector/include/hids/journal/runtime.hpp`
- `collector/src/journal/reader_main.cpp`
- `collector/src/journal/runtime.cpp`
- `docs/validation/m2-lifecycle-validation.md`
- `engine/ingestion/m2_control.py`
- `engine/ingestion/m2_service.py`
- `packaging/m2-config.example.json`
- `packaging/systemd/hids-ingest.socket`
- `tests/integration/m2_runtime_fixture.cpp`
- `tests/integration/test_m2_lifecycle.py`
- `tests/integration/test_m2_runtime_processes.py`
- `tests/unit/m2_runtime_test.cpp`

Modified:

- `collector/include/hids/journal/transport.hpp`
- `collector/include/hids/journal_collector.hpp`
- `collector/src/journal/linux_journal_io.cpp`
- `collector/src/journal/transport.cpp`
- `collector/src/journal_collector.cpp`
- `docs/README.md`
- `docs/implementation/m2-journald-spec.md`
- `engine/database/m2_store.py`
- `engine/ingestion/m2_receiver.py`
- `packaging/systemd/hids-ingest.service`
- `packaging/systemd/hids-journal.service`
- `tests/integration/M2-README.md`
- `tests/integration/validate_m2_offline.sh`
