# M4 first informational finding: implementation and observed acceptance

Status: owner-approved implementation; bounded synthetic/live trial passed.
Post-cleanup access and independent history/preservation verification passed on
2026-11-12. The earlier concern about missing recent HIDS history was not borne out.

## Approved and implemented scope

The owner accepted the first-rule packet with “i agree, let's move on”.
The exact `/usr/bin/dash`, euid 0, success condition is informational, non-demo,
and disabled by default. Root selects its immutable id/revision/hash for a new
activation. Missing Audit login identity is disclosed, never inferred.

Implementation: shared live identities, exact rule validator/evaluator, schema-v2
store with frozen prospective plans, explicit backed-up migrator, and bounded
service entry. CLI and library imports share the same LiveSource class identity.
Old bindings receive empty plans; old events are not backfilled. Pending work is
limited to the selected binding and survives interruption, including at its cap.
Migration runs under the existing writer lock, verifies a WAL-aware standalone
v1 backup, retains its manifest before changing the source, and atomically commits
v2 without changing historical rows. Backup growth participates in admission.

## Executed checks and observed results

- Local and Ubuntu: 86 M4 tests; Ubuntu additionally 87 M3 regressions and demo.
  The 18 new implementation cases include actual migration SIGKILL boundaries,
  backup/history preservation, frozen-plan refusal before source reading,
  strict rule identity, selected pending recovery and atomic finding persistence.
- Verified source snapshot `hids-src-20261112T074600Z-c74de580914d`, manifest
  `712e56e21ac5673303ab0a771c963528543131afd23afe247d7c8a6807fd0dd3`.
  Mac source archive remains under `/private/tmp/hids-m4-host-workflow/`.
- Ubuntu regression report returned passed at
  `/home/ivy/hids-m4-fixture.etjurv8x/results/run-20261112T040607Z-135c2df3bfc9/report.json`.
- Synthetic real-namespace trial returned passed/restoration verified at
  `/var/tmp/hids-m4-handoff.7xfvf2p8/report.json`: 16 old unevaluated events,
  two new non-demo findings, late A after B, repeat idempotency and negative controls.
- Explicit real migration returned version 2 and verified backup counts of
  16 events, one binding, zero rules/evaluations/alerts. Backup path returned:
  `/var/lib/hids/m4/backups/before-v2-33b3c8e73d1a460c9a35987ed6016c81/handoff.sqlite`.
  Historical logical hash returned:
  `20952d7aa9df324f5a1aee632c6eb201020b38740ced1e7244ba8d7fb02d3064`.
- Bounded live job `hids-m4-rule-acceptance-6df483c9cf` returned success;
  `/var/tmp/hids-m4-handoff.ak_vyvdf/report.json` returned passed/restoration verified,
  three actual executions imported, one finding and 16 old unevaluated events.
  Cases: root dash, non-root dash and root true. Harness assertions cover two
  nonmatches, exact payload/metadata, old rows, duplicate restart and restoration.
  Parent log returned at `/root/hids-m4-rule-job.xl4fstqf/run.log`.

The original results below were subsequently checked against the surviving VM
state; see the resolved incident and independent inventory below.
No unattended service, general threat coverage, release gate or publication is implied.

## Resolved intermediate failures

The root migration helper inherited worker restrictions which removed CAP_SETUID
on this target. No-data probes identified the seccomp-derived settings, including
an empty address-family filter. The short helper now retains source/destination
mount restrictions and only SETUID/SETGID until immediately dropping to the data
owner; it verifies zero capabilities before data access. Worker restrictions stay
unchanged. A separate Python `-m` duplicate-class identity issue was fixed by moving
live classes to a shared module. Full regression and namespace scopes then passed.

## Post-cleanup access incident (resolved)

During authorized storage cleanup, UTM's `Linux` VM UUID
`A4420D91-A2D9-4517-B3F1-19BC06D42F35` was permanently removed. `Linux 2`, UUID
`46330E53-4A53-4A94-B9D4-0ADEFD192AB7`, remains. Recent test SSH used `.7`;
remaining Linux 2's configured MAC `9a:b8:88:b2:58:11` maps to `.6` in DHCP/ARP,
while `.7` maps to MAC ending `12`. This raises a concrete risk that recent VM
history/evidence was on the removed VM. Its contents were not verified before
removal. Neither VM label nor copied host key establishes test-state continuity.

On resumption both SSH endpoints were unreachable. Linux 2's console initially
had no active display; a restart reached its encrypted-disk prompt. Automated
credential input misbehaved and did not establish successful unlock. No snapshot
rollback, disk replacement or further deletion was performed. Source code remains
in the canonical Mac repository and verified temporary snapshots.

Next: unlock Linux 2; inspect its real host/storage identity and retained HIDS
state before collection, setup or recovery changes. Verify which historical
reports/databases survive and whether another backup exists. If absent, preserve
this loss explicitly; rebuild/retest only as new evidence, never recreate or claim
old security history. Independent installation/policy/source-prefix/store checks
remain pending. No commits or pushes were made.


### Independent verification after access recovery, 2026-11-12

Linux 2 booted after disk unlock; the original pinned SSH endpoint `.7` became
reachable. Its guest `/sys/class/dmi/id/product_uuid` is
`46330e53-4a53-4a94-b9d4-0adefd192ab7`, exactly the remaining UTM Linux 2 UUID.
The running QEMU process references that UUID and `Linux 2.utm` disk. Its launch
MAC ends `11`, but guest networking reports an address ending `12` and `.7`.
The reason for that difference was not changed or established in this read-only
assessment. Static configuration/DHCP mapping alone was insufficient to infer a
lost VM. The prior concern about recent HIDS data loss was premature.

Read-only checks established:

- All 357 M3 SQLite files are present and each passes SQLite quick_check.
- All 29 installed artifacts match their recorded SHA-256 baseline.
- All four original Audit log inodes and recorded byte prefixes match the retained
  native-workload baseline. Audit configuration/plugin inventory and rules match
  baseline exactly; Audit is active and M3 configuration matches the 512 budget.
- Live M4 database is version 2: 19 events, two bindings, one rule, three completed
  evaluations (one matched, two no_match), one non-demo informational finding.
  Full integrity_check and foreign_key_check pass; its main bytes were unchanged
  across the owner-identity read-only inspection.
- All 16 original event rows equal their v1 migration-backup counterparts and
  remain unevaluated. The backup is intact v1/16 events with integrity_check ok.
  Database, backup and manifest remain UID 994/mode 0600; backup directory 0700.
  The finding discloses unavailable Audit login identity.
- All seven explicitly checked key report/log paths from the recorded native,
  reboot, initial live import, v2 synthetic/live, parent-job and regression runs
  remain present. The VM workflow report tree contains 40 reports.
- M3 service/socket/checker/timer are inactive; no transient M4 units remain and
  `/etc/hids/m4.json` is absent. No new collection or test workload was run.
- Mac canonical source/uncommitted work, 40 local workflow reports, two export
  directories and 15 M4 source archives remain available.

No missing HIDS implementation, database or key evidence was identified within
this inventory. Do not recreate the 16 old events, 357 databases, migration backup
or finding: they already survive. No application deployment, database migration,
configuration repair, snapshot rollback, new collection, deletion, commit or push
was performed for the inventory. Boot/login and read-only administration can add
ordinary host logs; this was not a disk-forensic no-write acquisition.

Recommended next work: preserve a separately approved backup of the now-verified
VM state, include guest UUID and source/store identities in future access
preflight, and continue the remaining M4 recovery/contention/resource evidence.
Further removal of VM files requires checking their contents/identity and owner
approval. No new backup or rebuild was started by this assessment.
