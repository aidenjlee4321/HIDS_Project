# Production collector: initial Ubuntu offline validation

**Status:** Owner-reported successful compilation and offline tests; runtime validation incomplete  
**Recorded:** November 6, 2026  
**Execution date/time and full transcript:** Not supplied  
**Scope:** Native production adapter only, not the complete HIDS

## Environment

| Property | Supplied result |
|---|---|
| Operating system | Ubuntu 26.04.1 LTS |
| Kernel | `7.0.0-42-generic` |
| Architecture | `aarch64` (ARM64) |
| Compiler | GCC `15.2.0` |
| Validation type | Offline compilation, unit tests and production link smoke test |
| Intended service account | Not tested; execution identity of this offline run not supplied |

These are the owner's results from the actual Ubuntu VM, not a run executed by
this documentation review. Exact compiler invocation, package revisions, stdout/
stderr transcript, source/binary digests and execution time were not attached.
The synchronization previously copied the canonical sources into
`/mnt/ccdc-transfer/collector-validation/`; this records the reported test result,
not an independently attested source-to-binary chain of custody.

## Reported results

| Check | Files / target | Result |
|---|---|---|
| Strict compilation | `collector/src/process_collector.cpp` | Passed with strict warnings and `-Werror` |
| Strict compilation | `collector/src/process_connector_protocol.cpp` | Passed with strict warnings and `-Werror` |
| Strict compilation | `collector/src/linux_process_connector.cpp` | Passed with strict warnings and `-Werror` |
| Collector unit suite | `tests/unit/process_collector_test.cpp` | Passed |
| Linux backend unit suite | `tests/unit/linux_process_connector_test.cpp` | Passed |
| Complete production link smoke | All three production translation units with `tests/unit/process_collector_link_smoke.cpp` | Passed |

The [collector README](../../collector/README.md#compile-and-run-offline-tests-on-ubuntu)
contains the documented recipe (`-std=c++20 -Wall -Wextra -Wpedantic -Werror`).
The owner explicitly confirmed strict compilation and `-Werror`; the complete
verbatim command line was not supplied. Do not invent additional flags or claim
Ubuntu ASan/UBSan execution: those sanitizer runs were previously local macOS
checks with a Linux-header test shim.

## What this establishes

The native adapter, parser and backend compile with the tested Ubuntu ARM64/GCC
toolchain, the two offline suites pass there, and the production objects link
together. This advances the earlier macOS/header-shim evidence. The parser's ABI
assertions and offline tests ran as part of the reported build/test path; this
is useful compatibility evidence, not a guarantee about every Ubuntu installation.

The collector suite uses fake I/O and in-memory native packets. The backend suite
uses syscall doubles, verifies the production SOCK_CLOEXEC request and a real
owned descriptor's FD_CLOEXEC flag, and simulates poll/receive failures. The smoke
test constructs a stopped collector and deliberately never calls `start()`.
None of these targets opens a live process-connector subscription. These behaviors
are established by source inspection; the reported pass is the owner's evidence.

## Explicit limits

- Production **live connector operation remains unvalidated**: socket subscription,
  live ACK/delivery behavior, event reception, real-socket CLOEXEC behavior and
  kernel-side IGNORE completion were not tested by this offline run.
- **Intended service-account access remains unvalidated**, including cn_proc,
  journal/Audit permissions and effects of service hardening/namespaces. An
  interactive account's earlier research success cannot substitute for this.
- **Runtime reliability remains unvalidated**: long-running/high-volume operation,
  real event loss, scheduling/backpressure, concurrent subscribers, crash/SIGINT
  integration, restart/recovery and actual kernel cleanup behavior remain open.
- There is no `/proc` enrichment, normalized contract, IPC/Python receipt,
  persistence, detection, authenticated API or dashboard in this validation.
  It does not establish any [v0.1 release completion criterion](../release-scope.md#v01-completion-criteria)
  for the complete end-to-end product on its own.
- A passing test of mocked error handling does not demonstrate lossless delivery,
  actual source availability, a healthy quiet machine or historical recovery.

The earlier [temporary cn_proc research](../research/process-connector.md) did
observe one live ordinary-user controlled lifecycle. That was a different program
and experiment; its results do not make this production adapter live-validated.
No new experiment, installation, privilege grant or Ubuntu configuration change
was performed to write this record.

## Follow-up evidence and planning

Preserve the original build/test transcript, exact flags, source and executable
hashes and execution identity/date when available; do not rerun a kernel experiment
merely to improve provenance or change a sequence count. The next engineering
steps and approval gates are in the
[v0.1 implementation plan](../implementation/v0.1-implementation-plan.md).
Future live validation requires a separately authorized, bounded plan under the
intended identity; do not automatically retry as root or stress-test the connector.
