# Intended-account process adapter trial — approved and exercised

Owner approved this packet before execution on November 13, 2026. It authorizes
one Linux 2 validation experiment, not production deployment,
a finalized normalized event contract, or permission to enable a source in setup.
Existing D-12c/D-14a approvals remain unchanged. The standing owner rule reserves
new fundamental identity and sensitive collection decisions for explicit approval.
No new account or live subscription was created during preparation. The later
approved trial created the dedicated account and passed; see the evidence below.

## Proposed identity and authority

Create a dedicated system account and primary group named `hids-process`, with
no login shell, no home creation and no supplementary groups. Resolve allocated
UID/GID through NSS; do not reuse an existing unexpected account or a different
HIDS identity. Offline inspection found this account absent on Linux 2.
Run the probe as that exact nonzero UID/GID with no supplementary groups,
NoNewPrivileges set and all five Linux capability sets empty. Grant no Audit,
journal, database, root-control socket or dashboard access. No added capability,
root collector, group change or permission fallback is authorized by this packet.
The account may remain inert after the trial; removal is not assumed.

Root prepares a fresh private directory (0700) and empty root-owned regular report
file (0600, one link), then delegates only its write-only descriptor. The probe
checks descriptor ownership, mode, size, offset and access before constructing the
real connector. Root pins the tested executable in a root-controlled private
location, verifies its hash, closes unrelated descriptors and supervises the
bounded process. Do not execute a mutable ordinary-user binary as root.
The root supervisor was subsequently implemented in
`tests/integration/process_adapter_trial_ubuntu.py`. A root-controlled 0750
outer directory permits the exact role to execute the hash-pinned 0550 binary;
the inner report directory remains root-only 0700. The actual role/capability and
private-directory denial checks passed before the one live launch.

## Exact collection and retention scope

One LISTEN attempt, approximately one second for initial delivery, followed by one
owned `/usr/bin/sleep 0.25` child and at most five seconds of event polling.
There are also finite poll-count limits. The unreaped owned child pins its PID
until collection stops. A short natural-exit grace precedes owned-child cleanup;
forced cleanup makes the lifecycle result fail. Interrupted child waits retry.
No unrelated process is signalled. Request graceful stop, one IGNORE attempt and
one socket close. An external deadline first requests graceful cancellation;
if forced termination becomes necessary, report failure and stop experiments.
Do not automatically repeat subscriptions, stress shutdown, reboot or reconnect.

**The kernel subscription transiently receives and decodes system-wide process
lifecycle metadata.** Its event mask is not a PID privacy filter. The probe retains
only events whose TID and TGID equal its own unreaped test child's PID, at most
eight records. Retained native fields are lifecycle kind, TID/TGID, optional native
parent TID/TGID, CPU, sequence, raw kernel monotonic nanoseconds (decimal string),
and optional native exit status/signal. The parent IDs identify the owned probe.
No arguments, environment, command enrichment, `/proc` process scan or source-log
sampling is included. Reading the probe's own capability status is an identity
check. Unrelated events are discarded after decoding; only bounded aggregate
status/diagnostic counts and typed errno values may reflect other traffic.
The production collector also keeps its existing bounded per-CPU sequence state
in memory; the report does not export unrelated event sequences or identifiers.

The report is at most 16 KiB and stays root-private on the VM. No native report or
payload export to Mac/chat/Git, API route, M3/M4 database write, rule execution or
setup eligibility promotion is included. Record sanitized outcomes/provenance in
project documentation. Preserve existing logs, policy, history and backups.

## What a result means

Separate: control-send success, subscription ACK, any delivery, the owned child's
complete fork/exec/exit lifecycle, detected incompleteness, IGNORE-send result and
socket-close result. Missing ACK is not automatically no delivery. Successful
IGNORE send/close does not confirm kernel-side unsubscribe completion. Native
monotonic time is not wall time; no normalization is performed. A passing owned
fixture does not establish sustained reliability, all workloads, concurrent
subscribers, restart recovery, shutdown correctness or supported deployment.

A denial or missing delivery is a useful failed experiment, not permission to add
privileges or change kernel/logging settings. Capture the bounded error and stop.
Keep the source unavailable in first-run selection until separately justified.
No OS Audit, journal or PAM configuration/rules, Mac settings, trust stores,
credentials, commits or pushes change under this scope.

## Evidence supporting a zero-capability trial

Tagged upstream Linux v7.0 [connector implementation](https://raw.githubusercontent.com/torvalds/linux/v7.0/drivers/connector/connector.c)
permits the process connector group through its bind check and enables non-root
receive. The [process connector implementation](https://raw.githubusercontent.com/torvalds/linux/v7.0/drivers/connector/cn_proc.c)
checks initial namespaces and handles per-socket control/filter state. This makes
a zero-capability trial reasonable; it does not prove access on Ubuntu's installed
build. The tagged source also leaves shutdown/listener-accounting questions that
this one graceful trial will not resolve. No claim is made that Ubuntu's signed
7.0.0-43.43 kernel is byte-equivalent to the upstream tag or includes every fix.

[Offline preparation evidence](../validation/process-adapter-trial-preparation.md)
records actual target compilation, probes and explicit limitations.

## Executed outcome

[Live evidence](../validation/process-adapter-live-trial.md): the intended account
with zero capabilities observed the owned child's fork/exec/exit. No ACK was
received; IGNORE completion remains unconfirmed. There is no installed process
service, no running collector, and no permission to promote setup eligibility or
collect/retain arbitrary process history under this one-shot trial.
