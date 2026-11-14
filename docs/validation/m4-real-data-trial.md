# M4 bounded real-data Ubuntu acceptance

## Approval and implemented boundary

The owner accepted the [production storage/trial packet](../implementation/m4-production-review.md)
with “yes, now continue.” This authorizes its exact five-table storage layout,
additional protected event copy, separate real-data store identity, conservative
trial budgets and bounded Ubuntu acceptance. Earlier synthetic approvals remain
intact. It does not approve unattended monitoring, supported security rules,
release thresholds, dashboard authentication, commits/pushes or Mac system changes.

Implemented `engine/detection/m4_service.py` and the uninstalled, non-autostart
`packaging/systemd/hids-m4-trial.service`. The entry reads only root-owned mode-0640
`/etc/hids/m4.json`, runs under the existing `hids-ingest` identity without reader IPC
group membership, takes a closed UUID selection and uses fixed source
`/var/lib/hids/m3` / destination `/var/lib/hids/m4/store`. It requires the source
read-only namespace and hidden M3 sockets before opening a destination.

Real data uses application id `0x48344c31`, schema version 1, `audit_plugin` origin
and `hids.m4.live.*` binding/event/content hash domains. The shared reader/store
implementation now has explicit class-level mode identities; original lab
constructors still reject production paths/live mode and keep their distinct marker.
The real store rejects lab sources and every rule definition. Rule/evaluation/alert
tables must remain empty. No fixture database conversion or schema migration occurs.

The approved 512-page/2 MiB cap, existing guard-derived WAL/state limits and
1 GiB warning / 512 MiB critical / 256 MiB minimum admission settings are enforced
on each writer open. Configuration cannot enlarge the 16-event/120-second scope
or substitute smaller free-space guards. Per-page import is capped by remaining
event allowance. Continuous trial entry stops at its limit; time expiry/interruption
without completion returns explicit incomplete status. `--once` is a single bounded
round with an explicit completion Boolean, not a promise of monitoring readiness.
The acceptance harness additionally enforces its global 120-second live window.

## Test evidence before real access

All 53 M4 tests passed locally: 49 previous cases plus four production config/store
cases (closed selection and limits, disabled state, fixed paths and mode separation,
real marker/budgets/rule denial). The private marker unit test models normal free
space because the Mac remains below the unchanged real admission guard. It does
not lower the production policy or claim the Mac can run that trial.

Ubuntu workflow passed all 53 M4 tests, all 87 M3 Python regressions and the demo,
no skips, 1.923 summed phase seconds:

- Snapshot `hids-src-20261112T061256Z-8f7488380ea6`.
- Manifest SHA-256:
  `959b49f17a7cb352299259d7603acf2b469847fc57f6251b18f5f5adf71c1724`.
- Report:
  `/home/ivy/hids-m4-fixture.etjurv8x/results/run-20261112T022551Z-d1661f923359/report.json`.

Production-shaped synthetic namespace acceptance then passed, protected report
`/var/tmp/hids-m4-handoff.v3ya_27c/report.json`. A synthetic M3 source/destination
was bind-mounted over the fixed production paths only inside transient worker
namespaces. Original production M3 state remained hidden/unmodified there.
Actual root-config mode 0644 and wrong generation were refused before import.
Correct 0640 selection imported B, retained its old sweep boundary, and found late
A across worker starts. The real marker was used only in that explicitly synthetic
test namespace. Counts ended at two unevaluated events and zero alerts.

The final harness change made restoration failures explicitly mark the report
failed/needs_attention. Only the harness changed after the above unit/synthetic
snapshot; entry/reader/store/unit-test source was byte-compared with the passing
snapshot. Final live harness snapshot:

- `hids-src-20261112T061638Z-613203e85c0d`.
- Manifest SHA-256:
  `9cf00b090557979a365346961e80d941f76787419672923e0a2dde7d43ae5bf3`.

## Actual kernel → M3 → M4 trial

The explicit `tests/integration/m4_trial_ubuntu.py --phase live --live-audit`
experiment ran from that verified snapshot, under the existing serialized VM lab
lock. A detached root acceptance unit kept restoration independent of SSH;
interruption handlers and a separate outer runtime limit protected cleanup.

Protected evidence:

- Trial report: `/var/tmp/hids-m4-handoff.c61hthcc/report.json`.
- Parent console: `/root/hids-m4-live-job.ngctca87/console.log`.
- Parent unit: `hids-m4-live-acceptance-8dc0e9f177f5`, observed inactive/dead with
  ExecMainStatus 0 after completion.
- Selected source: `bb89fb26-4145-4c8b-8265-05e4e1cf00df`.
- Activation: `c850bb51-d518-42b9-81d7-8556c28ffcc0`.
- Generation: `01be1b3f-6aa6-4fa0-bec0-a1d68c2cb846`.

The harness created one explicitly authorized new M3 activation, temporarily used
the established lab-only Audit plugin/RAW setup and per-child execution rules,
and performed exactly 16 controlled `/usr/bin/true` executions. The root lab
procedure changed policy; product M3/M4 code did not configure logging. Original
policy was restored afterward, with no forced rotation or evidence cleanup.

All 16 actual kernel execution groups reached committed M3 storage and then the
separate real M4 store. The harness matched the exact target PID set and every
normalized payload, source/activation/generation and original event-metadata field.
The actual backend UID read the committed WAL view through the read-only namespace;
source write-open was denied and M3 socket access was hidden. M3 commits preceded
handoff and no M4 call was inserted into M3's accept/ACK path. Kernel loss counter
and auditd PID remained unchanged. This is not a sustained contention benchmark.

Result: **passed**, 16 imported / 16 explicitly unevaluated / 0 pending evaluations /
0 rules / 0 alerts, in 0.978 seconds for the capture/import window. A second worker
start preserved the same 16 events and stopped at the configured event cap; it did
not reevaluate or duplicate them. Broader duplicate replay and transaction-crash
behavior retains its separate synthetic acceptance scope.

## Independent final preservation and state

A separate privileged inspection rechecked original Audit configuration/plugin
hashes and rules against the protected pre-M3 baseline, all four original source
inode/byte prefixes, all 29 original installed artifacts and the original M3
configuration/512 lab budget. The harness also byte-hashed every prior event
database before/after; all 355 original SQLite files remain. Control history grew
by the intended activation; total M3 databases are now **356**, including control.
No original event database/source was removed or overwritten.

The real destination `/var/lib/hids/m4/store/handoff.sqlite` remains protected:
parent/store 0700, files/sidecars 0600, owner `hids-ingest`. Independent read-only
inspection under the database owner verified the real application id/version,
integrity_check `ok`, empty foreign_key_check and table counts 1 binding / 16 events /
0 rules / 0 evaluations / 0 alerts. No security finding has been generated.

Temporary `/etc/hids/m4.json` and the lab Audit plugin/rules were removed after
retaining a root-private selected-config copy. Audit configuration was restored;
Audit remains active and all four M3/checker units are inactive. Transient worker
units were collected. No M4 unit was installed/enabled, no automatic restart was
configured and the acceptance worker is stopped. Verified snapshot inventory/hash
checks passed again on the protected staged code. No Git changes were published.

## Remaining scope and next work

This closes the approved bounded first real-data import trial, not M4 detection or
v0.1. The code is a manually selected bounded importer; it is not unattended
monitoring. Additional live trials need explicit selection and must preserve this
history rather than deleting the first destination to obtain a fresh test.

Next M4 product work is a useful evidence-backed one-event rule with reviewed
requirements, benign explanations, severity and activation/version semantics.
The existing equality demo is not a supported threat rule, and the approved alert
DDL still supports only its informational lab-demo form. Review any rule/schema
extension before enabling real findings. Retention/expiry, broader slow/busy/VFS/
physical-device tests, sustained resource/fairness evidence, release budgets,
packaging and root-only API/UI remain open. Preserve D-08/D-12/D-13/D-15.
