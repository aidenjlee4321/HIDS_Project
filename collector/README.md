# Native C++ process-source milestone

This directory now contains a narrow production-oriented C++20 process connector
adapter. It is separate from the [temporary research tools](../scripts/research/README.md)
and based on the scoped [Ubuntu evidence](../docs/research/process-connector.md)
and [provisional ADR-006](../docs/decisions/006-provisional-process-collection.md).
It is **not** a running HIDS service or an end-to-end collection pipeline.

## Implemented boundary

| File | Responsibility |
|---|---|
| `include/hids/process_collector.hpp` | Internal native event/status types, trusted sink and testable I/O boundary; serialized adapter API |
| `src/process_collector.cpp` | Single-session lifecycle, bounded polling, ACK/delivery separation, per-CPU diagnostics and graceful source failure |
| `src/process_connector_protocol.cpp` | Linux UAPI control encoding and bounded, alignment-safe native validation/decoding |
| `include/hids/linux_process_connector.hpp`, `src/linux_process_connector.cpp` | Dedicated Linux socket, kernel-assigned port, syscall error reporting, sender validation and descriptor ownership |

The adapter requests FORK, EXEC and EXIT once per explicit `start()`. It preserves
thread ID (kernel PID), process ID (TGID), optional event-supplied parent IDs,
CPU/connector sequence, native monotonic nanoseconds and raw EXIT encoding.
EXEC parents remain absent, and unavailable native parent zeros stay native zeros.
These are internal C++ source representations, **not** ECS fields, normalized
events, an IPC contract or a persistence schema. There is no wall-clock substitution.

`Collector` borrows `ConnectorIo` and `Sink`; both must outlive it. `Sink` is a
trusted internal consumer, not a public subscription endpoint. Callbacks must not
throw, block, destroy/reenter the adapter or retain references to transient callback
arguments. Copy only justified data into a bounded downstream consumer. The adapter
has no event queue, stdout/event logging, filesystem writes, service installation,
network API or automatic privilege escalation. Root-only human HIDS data access
remains required; the eventual service/IPC/retention layer must enforce it.

The intended ownership order is backend, sink, then collector; destruction runs
collector cleanup before its dependencies. All adapter operations, including
start/stop/destruction, require one serialized owner thread. Signal handlers must
only notify that owner (for example, set a signal-safe flag); do not call the
adapter or socket operations from a handler. No application signal handler or
threading/supervision model is installed by this library.

## Availability, gaps and shutdown

`start()` returns true when LISTEN was sent, not when the kernel acknowledged it.
Initial status is `unconfirmed`. ACK success sets `subscription_acknowledged`;
validated events set `delivery_observed`. Neither substitutes for the other.

| Session observations | State | ACK flag | Delivery flag |
|---|---|---|---|
| LISTEN sent, no ACK or event observed | `unconfirmed` | false | false |
| Successful ACK before any event | `acknowledged` | true | false |
| Event before/without an observed ACK | `observing` | false | true |
| ACK and event both observed, in either order | `observing` | true | true |
| Incomplete reception interval | `degraded` | Retained independently | Retained independently |
| Open/control/terminal receive failure | `unavailable` | Retained session fact | Retained session fact |

A later ACK never clears degradation or changes delivered evidence into a stronger
delivery guarantee. These are internal C++ states, not an ECS or IPC contract.
A filtered LISTEN ACK can remain absent indefinitely, without claiming source
failure solely because the stream is quiet. `observing` describes delivered
records, not health freshness or complete monitoring. Periodic health/liveness
assessment remains open.

Each `poll_once()` processes at most one 16-KiB datagram and clamps the requested
poll timeout to 0–100 ms, returning to the caller so other sources can be scheduled.
Fixed per-CPU tracking covers CPU IDs 0–4095; other CPU IDs still reach the sink
with a tracking-unavailable diagnostic. No receive loop or unbounded queue lives
inside the adapter. Sink latency is the caller's responsibility.

The dedicated socket is created atomically with `SOCK_DGRAM | SOCK_CLOEXEC`;
there is no post-creation `fcntl()` window and no non-CLOEXEC fallback on failure.

`POLLERR` alone or combined with `POLLIN` triggers a nonblocking receive, not an
automatic close. Netlink pending errors (notably overruns/ENOBUFS) are retrieved
before a queued datagram; a recoverable error leaves queued data for a later poll.
A successful receive is returned normally even when `POLLERR` was in the readiness
snapshot. The returned errno remains authoritative: ENOBUFS reports incomplete
reception and keeps the source open; EINTR reports an interrupted call; EAGAIN/
EWOULDBLOCK is a stale-readiness timeout; other receive errors terminate this source.
POLLNVAL reports EBADF; POLLHUP remains a closed-source indication. No extra receive
loop, error-clearing `SO_ERROR` call or reconnect is introduced. Source reference:
[Linux v7.0 datagram receive/error handling](https://github.com/torvalds/linux/blob/v7.0/net/core/datagram.c),
used by [netlink recvmsg](https://github.com/torvalds/linux/blob/v7.0/net/netlink/af_netlink.c).

Diagnostics carry a typed reason, exact errno where supplied and optional
CPU/previous/current sequences. No raw malformed payloads or unrelated sensitive
values are echoed. First samples establish per-CPU baselines; wraparound is unsigned.
A discontinuity (including a duplicate/backward sequence) is a diagnostic comparison,
not a count of lost events and not sufficient alone to claim an incomplete interval
under this filtered interface.

ENOBUFS, overruns, truncation, malformed/foreign records and unexpected event types
mark the session's evidence incomplete. Later events preserve `degraded` state and
`incomplete_interval`; they do not erase the gap. EINTR is reported as an interrupted
read without automatically asserting event loss. Fatal receive or control errors
stop **only this source**, report `unavailable` with errno and return control. Other
source/service availability needs application-level integration, not a claim from
these unit tests. EACCES/EPERM are not converted into a universal unsupported-kernel
verdict. No root retry, automatic reconnect, logging change or package installation
occurs.

An explicit caller-controlled restart creates a new local `session` and sequence
baseline; it cannot recover previous events. Session numbers are not boot/process
identity. Consumers must retain prior interruption/status evidence; a new session
does not prove a historical gap was filled. Recovery and supervision policy remain
unresolved. Do not loop live start/stop for testing or automatically restart after
an unsubscribe failure while upstream cleanup concerns remain unresolved.

`stop()` is idempotent and attempts exactly one IGNORE after any LISTEN attempt,
then closes the descriptor, including on uncertain/failed LISTEN sends. It never
waits for IGNORE ACK or retries an interrupted control send. Destructor cleanup is
the same. Unsubscribe/close errors remain diagnostics and flag incomplete evidence;
`stopped` means userspace closed its adapter, not verified kernel unsubscription.
The Linux backend prevents two active instances of this adapter in one process,
but does not claim to serialize other processes. A crash, SIGKILL or forcibly
terminated owner cannot guarantee unsubscribe; actual installed-kernel fixes and
production shutdown/recovery still require validation.

## Compile and run offline tests on Ubuntu

Use only the existing compiler and Linux UAPI headers; stop if absent. Nothing
here installs a dependency or selects a final build/package tool. From repository
root, create a private build directory (these commands do not open connector sockets):

```sh
command -v c++
# Continue only when the existing compiler is available.
umask 077
build_dir=$(mktemp -d /tmp/hids-process-build.XXXXXXXX)
c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include \
    -c collector/src/process_collector.cpp -o "$build_dir/process_collector.o"
c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include \
    -c collector/src/process_connector_protocol.cpp -o "$build_dir/process_connector_protocol.o"
c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include \
    -c collector/src/linux_process_connector.cpp -o "$build_dir/linux_process_connector.o"
c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include \
    collector/src/process_collector.cpp collector/src/process_connector_protocol.cpp \
    tests/unit/process_collector_test.cpp -o "$build_dir/process_collector_test"
"$build_dir/process_collector_test"
c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include \
    collector/src/process_connector_protocol.cpp tests/unit/linux_process_connector_test.cpp \
    -o "$build_dir/linux_process_connector_test"
"$build_dir/linux_process_connector_test"
# Link all three real production translation units; never start collection.
c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror -I collector/include \
    collector/src/process_collector.cpp collector/src/process_connector_protocol.cpp \
    collector/src/linux_process_connector.cpp tests/unit/process_collector_link_smoke.cpp \
    -o "$build_dir/process_collector_link_smoke"
"$build_dir/process_collector_link_smoke"
```

Do not define `NDEBUG` when running these assertion-based tests. The backend test
includes the actual backend translation unit with syscall replacements; do not
also link `linux_process_connector.cpp` into that test. Both unit-test suites are offline: no child generation, subscriptions or live
kernel experiments. The separate smoke executable links all three production
translation units, constructs/destroys a stopped collector and never calls `start()`;
it opens no connector socket and uses no syscall replacements. The backend suite
still uses syscall doubles: it asserts the requested SOCK_CLOEXEC flag and checks
FD_CLOEXEC on an actual owned descriptor, not on a live Linux connector socket. Optional
`-fsanitize=address,undefined` can be added only if already supported by the compiler;
no sanitizer/dependency installation is authorized.

Local validation used Apple Clang 15 on macOS ARM64, downloaded official Linux v7.0
UAPI headers and a temporary POSIX test shim outside the repository. Strict warning
checks, both sanitizer suites and the complete production link smoke test passed.
The corrective pass covers atomic CLOEXEC requests/descriptor flags, POLLERR with
and without POLLIN (data, recoverable and terminal errors), ACK-before-event,
event-without-ACK, combined ACK/delivery and subscription errors. This verifies native wire layout/parser
and component behavior under test doubles, **not an Ubuntu production build or
live reliability**. The research experiment's successful Ubuntu run does not
validate this separately implemented adapter.

The owner now reports successful strict Ubuntu ARM64 compilation, both offline
suites and complete production linking with GCC 15.2.0; see the
[validation record](../docs/validation/collector-ubuntu-validation.md). This is
separate from the earlier local sanitizer evidence. Live production connector
operation, intended service-account access and runtime reliability remain unvalidated.

## Not yet implemented / unresolved

No `/proc` enrichment, wall-clock mapping, shared normalized schema, Unix-socket
transport, Python receipt/validation, SQLite, daemon executable, public event viewer,
service accounts/packaging, other source adapters, dashboard, rules or remediation.
C++ will own future normalization and validate its output; Python will independently
validate received normalized contracts and own SQLite writes. Existing Unix sockets/
JSON Lines and other architecture decisions remain in force.

Before production use: validate actual runtime/service identity and hardening,
namespace/boot/process identity, native/normalized
contracts, sensitive enrichment, consumer backpressure, timestamps, shutdown/error
behavior and installed kernel fixes. Long-running/high-volume/concurrent-subscriber
behavior remains untested. Any live validation needs a deliberate bounded plan;
do not repeat the temporary kernel experiment merely to change a sequence counter.

The [v0.1 implementation-readiness plan](../docs/implementation/v0.1-implementation-plan.md)
records next integration tasks and unresolved contract/permission decisions; it
neither expands this adapter's implemented scope nor authorizes a live experiment.
