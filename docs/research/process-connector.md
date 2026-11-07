# Process connector research: one controlled Ubuntu lifecycle

**Status:** Owner-reported Ubuntu experiment; source review and offline reproduction  
**Documented:** November 6, 2026  
**Experiment wall-clock date/time:** Not supplied  
**Scope:** Research evidence, not comprehensive monitoring or a reliability benchmark

## Evidence and provenance

The owner supplied the results below after running the temporary
[process-connector-test.cpp](../../scripts/research/process-connector-test.cpp).
This documentation task did not rerun the kernel experiment. The full original
report, compiler transcript, executable digest and exact source revision used for
the VM build were not supplied. The recorded observations are preserved exactly;
source-based explanations and architecture proposals are identified separately.
No personal usernames, host identifiers or unrelated process payloads are included.
PID/session-like numbers are local experimental references, not global identities.

## Environment and compilation

| Item | Reported environment / evidence boundary |
|---|---|
| Distribution | Ubuntu 26.04.1 LTS |
| Kernel | `7.0.0-42-generic` |
| Architecture | ARM64 (`aarch64` on Linux) |
| Kernel build date | October 15, 2026, as previously supplied by owner |
| Connector configuration | `CONFIG_CONNECTOR=y` |
| Process events configuration | `CONFIG_PROC_EVENTS=y` |
| Linux connector headers | Available; experiment uses `linux/cn_proc.h`, `linux/connector.h`, `linux/netlink.h`, including extended `proc_input` |
| Compiler | Existing Ubuntu C++ compiler successfully built the experiment; executable identity and version not supplied |
| Compilation flags | Repository recipe: `-std=c++20 -O2 -Wall -Wextra -Wpedantic`; actual invocation/transcript not supplied for independent verification |
| Execution identity | Ordinary user, without sudo; do not infer production service-account access |

The documented compilation recipe is:

```sh
c++ -std=c++20 -O2 -Wall -Wextra -Wpedantic \
    process-connector-test.cpp -o /path/to/private-directory/process-connector-test
```

This is a reproduction recipe, not a claim that an exact compiler version or
command transcript was captured. Header availability and a successful build do
not independently verify the installed kernel's source or all runtime semantics.

## Methodology in the reviewed research program

1. Create one `AF_NETLINK` / `SOCK_DGRAM` / `NETLINK_CONNECTOR` socket; bind a
   local port and the `CN_IDX_PROC` multicast group. Set close-on-exec.
2. Send one extended `proc_input` LISTEN control with the FORK, EXEC and EXIT
   mask, connector ID `CN_IDX_PROC` / `CN_VAL_PROC`, and an ACK cookie. No legacy
   unfiltered fallback, sudo retry or additional subscription is attempted.
3. Wait at most one second for a matching connector ACK. Validate kernel sender
   and cookie; a generic netlink success is not a connector subscription ACK.
   Explicit errors stop; an absent ACK is recorded as inconclusive before the
   single controlled delivery experiment continues.
4. Create one direct child with `fork()` and execute `/usr/bin/sleep 2`. The child
   closes its inherited socket reference and never sends controls. The parent
   keeps its socket and retains the unreaped child's PID until cleanup.
5. Receive for at most five seconds after fork, with a 10,000-datagram work cap
   per receive phase. Stop early after observing all three child event types.
   Display only the exact child's PID/TGID events (at most eight lines). Other
   received non-ACK events participate in internal per-CPU sequence tracking,
   but their process information is not displayed or retained as research data.
6. Validate sender, netlink framing, connector identity and lengths, event size
   and multi-message boundaries. Copy wire structures into aligned objects rather
   than casting a possibly four-byte-aligned event pointer on ARM64. Count malformed
   records, overruns, ENOBUFS and truncated receives; do not read partial payloads.
7. Attempt one explicit IGNORE after any LISTEN attempt, before socket closure.
   Reap the child (terminate only that owned child if still running) and close
   the socket. RAII handles error returns; SIGINT/SIGTERM/SIGHUP only set a flag
   for serialized cleanup. No control operations run in a signal handler.

These are reviewed implementation behaviors. The successful run below exercises
ordinary completion, not every malformed-message or signal-cleanup branch. Prior
offline sanitizer tests exercised those branches without opening connector sockets.
The program is temporary tooling and is not copied into production as an executable.

## Actual reported results

| Notification | PID / TGID | Parent PID / TGID | CPU | Connector sequence | `timestamp_ns` |
|---|---|---|---|---|---|
| FORK | `13184` / `13184` | `13178` / `13178` | `2` | `1` | `3468494407399` |
| EXEC | `13184` / `13184` | Not provided by this event | `3` | `2` | `3468495538951` |
| EXIT | `13184` / `13184` | `13178` / `13178` | `3` | `3` | `3470501429782` |

The reported parent PID/TGID is preserved on events that provide it; it is not
filled into EXEC as though EXEC emitted it. In kernel terminology PID is a thread
ID and TGID is a process ID; this single-thread child's values are equal.

| Reported outcome / diagnostic | Value |
|---|---|
| Experiment exit status | `0` |
| FORK / EXEC / EXIT notifications | All three received |
| Malformed or unexpected messages | `0` |
| Overruns | `0` |
| ENOBUFS errors | `0` |
| Truncated messages | `0` |
| Untracked CPU observations | `0` |
| Reported per-CPU sequence discontinuities | `2` — interpretation below; not a lost-event count |
| Controlled child cleanup | Successfully reaped, exit status `0` |

The timestamps are the **actual supplied kernel monotonic nanosecond values**,
not wall-clock dates, Unix epoch times, collection timestamps or storage times.
No wall-clock conversion is available or invented. Keep boot/clock provenance
when eventually designing normalized time handling. A successful program exit
records its bounded checks, not complete delivery or formally acknowledged LISTEN.

## Acknowledgements and delivered events

**Observed:** LISTEN ACK was not observed. Nevertheless FORK, EXEC and EXIT for
the controlled child were received. This is evidence of effective notification
delivery in the tested context; do not describe the subscription as formally
acknowledged. IGNORE was sent before closing the socket; kernel completion of
IGNORE remains unconfirmed.

**Source-based explanation:** In inspected upstream v7.0, `cn_proc_ack()` uses
`PROC_EVENT_NONE`; a restricted event filter can suppress that message. It also
returns without sending when the listener count is below one, including after a
final IGNORE. These behaviors can explain absent ACKs but do not prove the cause
on this installed Ubuntu build. ACK and event delivery are separate observations.
[Upstream cn_proc ACK and filter implementation](https://github.com/torvalds/linux/blob/v7.0/drivers/connector/cn_proc.c).

## Sequence-discontinuity investigation

### Kernel generation and CPU scope

Upstream v7.0 `send_msg()` increments a CPU-local unsigned counter, assigns the
sequence and emitting CPU, then sends through multicast filtering. Its local lock
orders sends on that CPU. A sequence is not a per-child or global event counter.
Other event types and filtered ACKs can consume numbers before delivery; sequence
gaps alone cannot distinguish filtering from loss. CPU identifies the notification's
emitting CPU, not a durable process affinity.
[Upstream cn_proc sequence generation](https://github.com/torvalds/linux/blob/v7.0/drivers/connector/cn_proc.c).

The generic connector propagates the connector sequence into its netlink header;
that does not create a separate global sequence stream.
[Upstream connector serialization](https://github.com/torvalds/linux/blob/v7.0/drivers/connector/connector.c).

### Research-program accounting

`Report::event()` in the reviewed research source:

- Returns for `PROC_EVENT_NONE` ACKs before sequence accounting.
- Keeps separate `{seen, last}` state for CPU IDs 0–4095; larger IDs increment
  `untracked_cpu` instead of indexing outside the array.
- Counts a discontinuity only when `seen` is already true and unsigned 32-bit
  `(current - last)` differs from one; then replaces `last`. This handles normal
  counter wraparound. Duplicate/backward sequences also count as discontinuities.
- Does **not** increment for the first observation on a CPU, regardless of its
  initial sequence value. There is no expected global initial value of zero/one.
- Accounts for non-ACK records **before** checking whether they belong to the child.
  Tracking runs during both ACK-wait and child phases. The reported total covers
  more received traffic than the three displayed child records.

### What the supplied trace explains

| Displayed observation | Effect if these are the only inputs to a fresh tracker |
|---|---|
| CPU 2, sequence 1 (FORK) | Establish CPU 2 baseline; add zero |
| CPU 3, sequence 2 (EXEC) | Establish CPU 3 baseline; add zero |
| CPU 3, sequence 3 (EXIT) | Same-CPU delta is one; add zero |

**Finding:** Replaying only these three records through the current research
`Report::event()` produces **zero**, not two. An offline local ARM64 sanitizer
check verified this without rerunning the kernel experiment. A second synthetic
case adds two gaps in undisplayed unrelated traffic and obtains two while retaining
only three displayed child events. That is a demonstration of accounting scope,
not a reconstruction of the VM run.

CPU 2 → CPU 3 is consistent with execution moving between CPUs (FORK can be emitted
in the forking parent's context). It does not itself increment this per-CPU counter.
The displayed CPU 3 sequence 2 → 3 is contiguous; different CPUs' numbers must not
be compared as one stream. Thus neither first observations nor migration alone
explains the reported two.

**Unresolved:** The aggregate value of two is retained exactly. It could reflect
other internally received records and filtered sequence positions, or a different
source/binary used for the VM run. The child-only summary omits the preceding
same-CPU values, so the exact cause cannot be identified from supplied evidence.
No first-observation counting defect was found in the canonical implementation;
no research code change or repeat kernel run was needed to change the number.
The production tracker has regression tests for first samples, migration, hidden
traffic, wraparound, duplicate and discontinuous sequences. An original binary
source/digest and privacy-preserving CPU/previous/current diagnostics would improve
attribution if a separately justified investigation is approved later.

### Evidence of incomplete reception versus a loss count

`ENOBUFS`, `NLMSG_OVERRUN` and truncated datagrams are direct indications that
reception/usable evidence is incomplete. Malformed records indicate a validation
failure, not a known number of kernel events lost. A missing independently expected
child event within a bounded run indicates an observation gap; it does not alone
locate the failure. The supplied run observed all three expected child types and
reported none of those receive diagnostics.

A non-contiguous same-CPU sequence is a diagnostic lead. To attribute a missing
notification, establish the relevant prior sequence and account for subscribed
mask, filtered ACKs/types, ordering/duplicates, collection interval and loss signals.
Even a positive gap cannot be reported as an exact count of missing subscribed
process events under this filtered interface. Two discontinuities are two tracker
comparisons that failed its adjacency test, **not proof of two lost events**.
Zero receive-error counters equally do not establish lossless system-wide capture.

## Architectural interpretation and limits

**Evidence supports:** On this specific Ubuntu environment, one ordinary-user
socket received lifecycle notifications without sudo or changes to logging/Audit
configuration. The interface can be investigated as the primary live lifecycle
candidate; see [ADR-006](../decisions/006-provisional-process-collection.md).

**Provisional direction authorized by the owner:** cn_proc for live lifecycle,
`/proc` for best-effort context/enrichment, Audit for complementary security and
authentication records, and journald for complementary existing system logs.
This is not comprehensive monitoring. C++ owns native collection/validation and
future normalization; Python receives and independently validates normalized
contracts. The internal native C++ representation is not an ECS or IPC contract.
No observed field becomes mandatory solely because this experiment exposed it.

**Limits and unresolved questions:**

- This is one controlled experiment, not a reliability benchmark. Long-running,
  high-volume and concurrent-subscriber operation were not tested. Complete
  event-delivery guarantees, recovery and historical backfill are not established.
- cn_proc supplies live notifications, not historical process information. Events
  before subscription or during gaps are not recovered by this interface.
- Executable paths and command lines require additional collection. Short-lived
  processes can disappear before `/proc` enrichment; PID reuse, threads, reparenting,
  namespaces and boot identity require further design and validation.
- The current FORK/EXEC/EXIT mask does not deliver every identity/security event.
  The successful child observation does not establish multi-user attribution,
  all available payloads or access under a future hardened service account.
- Ordinary-user subscription to a system-wide source means root-only dashboard
  access cannot itself prevent independent local observation of process timing
  and relationships. This environment-specific property and its privacy boundary
  are documented in the [threat model](../threat-model.md#74-independent-process-observation).
- The [November 2 cleanup proposal](https://lkml.iu.edu/hypermail/linux/kernel/2611.0/02751.html)
  and [November 3 automated concurrency review](https://lkml.iu.edu/hypermail/linux/kernel/2611.0/06934.html)
  are not proof of installed fixes or kernel safety. Keep controls serialized,
  unsubscribe explicitly, avoid automatic reconnect/repeated subscriptions and
  do not stress-test to resolve the counter. SIGKILL/crash cleanup is not guaranteed.
- Compiler identity/version, exact VM build invocation, full sanitized report and
  source/executable provenance remain missing. No additional ECS mapping or
  timestamp fallback policy is finalized by this document.
