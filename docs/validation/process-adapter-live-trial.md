# Intended-account process adapter: one bounded live trial

November 13, 2026. **Passed for the exact owned-child experiment; not production
readiness.** Owner explicitly approved the [trial scope](../implementation/process-adapter-trial-review.md)
after offline preparation, then directed continuation toward a first installable
build and reassessment. No existing approval was reversed.

## Provenance and actual boundary

Linux 2, AArch64, kernel `7.0.0-43-generic`; compiler GCC 15.2.0.
[Offline snapshots/reports](process-adapter-trial-preparation.md) establish source
provenance. Tested executable SHA-256:
`b5e3327b74c9018a2228438c8193bfd093464a95451aad6a4e7c56336452b5ca`.
Supervisor source SHA-256:
`0360421ce53eeb0961dbbd467dc64ee1ecdc3d5a6f6d0ab46a421f92ce27f7fc`.
The root launch verified that digest before evaluating the supervisor, and the
supervisor checked the tested binary before pinning and before live launch.

Created `hids-process`, UID 992/GID 969 on this VM only, `/nonexistent` home,
`/usr/sbin/nologin`, no home directory creation and no supplementary memberships.
IDs are observations, never portable constants. Actual execution uses NSS lookup,
NoNewPrivileges and empty effective/permitted/inheritable/bounding/ambient capability
sets, independently checked before the source starts. Root-private directory read
was denied. The test executable itself also enforces the exact role and grant.

The supervisor used existing setpriv, a fresh root-controlled executable directory,
root-only report directory, fixed environment, no core dumps, private stdout/stderr,
16 KiB file, 128 MiB address-space, five-second CPU, 64-FD and eight-process limits.
These are experiment containment limits, not measured release performance targets.
The probe had approximately one second pre-child and five seconds collection,
with finite polling and owned-child cleanup bounds. The supervisor had a 15-second
wait followed by graceful cancellation before a final failure-only kill deadline.
No deadline, signal cleanup or forced termination was needed.

## Outcomes

| Observation | Actual result |
|---|---|
| Owned fork/exec/exit | All three received; three native records retained |
| Any delivery | True, tracked separately from the owned fixture |
| Subscription ACK | False; no ACK was received |
| Detected incomplete interval / event-cap overflow | Both false in this trial |
| Open / control sends / close | One / two / one |
| Open, LISTEN send, IGNORE send, close errno | All zero |
| IGNORE completion | Unconfirmed; successful send/close is not completion proof |
| Probe exit / supervisor timeout / forced termination | 0 / false / false |
| Forced fixture cleanup | False |

The kernel stream transiently included system-wide lifecycle metadata. Only the
owned child TID=TGID records were retained; no enrichment, args/environment or
source-log samples were collected by this probe. Original monotonic time remains
raw and wall activity time absent. No normalized IPC, Python ingestion, SQLite,
rule evaluation or dashboard integration was exercised in this source trial.

Private VM location: `/opt/hids-process-trial.x4tahko7/private/`:
`prepared.json`, `live-attempt.json`, `native.json`, `summary.json`,
`preservation.json`, `cleanup.json`, stdout and stderr. Native payload remains on
the VM; only aggregate outcomes were returned. Reports remain root-owned 0600,
inside root-only 0700. The durable exclusive attempt marker prevents another
launch in the same trial directory. No live retries were performed.

## Preservation and cleanup

The existing lab preservation helper was run before and after, under the existing
M3 workflow lock, and compared with the original dashboard acceptance baseline.
It verified installed artifacts, existing M3/M4 database/configuration hashes (excluding transient SHM),
Audit rules/service state, original Audit inode-prefix preservation, and inactive
M3 units. This lab helper reads the previously authorized historical Audit
prefixes; it is separate from product metadata preflight and from the process probe.
No logs were copied/deleted or policy rewritten.

All 357 M3 SQLite files remain. M4 retained history/backup remains unchanged.
Audit remains active; the M3 service/socket/checker/timer remain inactive. A later
independent UID scan found zero processes for the new role. No `hids-process.service`
exists. Actual role checks also denied read access to the M3 control store, M4
history store and native report. The role remains inert; no removal was requested.
No API/browser deployment, Mac system change, commit or push occurred.

## Remaining gate

The result supports a zero-capability intended identity on this host. It does not
establish sustained loads, concurrent subscribers, namespace variants, kernel
cleanup fixes, real unsubscribe completion, production supervision or packaging.
Do not mark the generic setup source eligible merely because this fixture passed.
The next boundary is the versioned live process normalization/IPC/storage contract
and selected-source runtime integration, not another repeat of the same experiment.

Additional non-collecting checks validated the native report structure and owned-only
identifiers privately, including lossless raw timestamp strings and absent activity
wall time. Attempt-marker reuse raised FileExistsError without changing the marker
or launching a process. `report-and-marker-checks.json` retains the aggregate proof.
