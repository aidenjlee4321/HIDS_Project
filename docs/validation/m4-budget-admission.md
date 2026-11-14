# M4 WAL and aggregate-state admission acceptance

Date: 2026-11-12. Result: passed, including a retained-backup accounting fix.
Scope: normal approved M4 budgets, private synthetic state, actual SQLite WAL
frames and actual file metadata. No live collection, schema change or deployment.

## Bug found and fixed

The first-rule migration counted the complete M4 parent directory before creating
its backup, but the running store's guard inventoried only `store/`. Retained
backup bytes were therefore absent from runtime aggregate admission. This did
not satisfy the approved policy to include backups in M4 state accounting.

A regression created a private, synthetic backup-area file of 192 MiB logical
length and expected `state_budget`. Before the fix it failed with reason None,
reproducing the omission. Runtime and migration now share a bounded private
inventory over `store/` and `backups/` under the M4 state parent. It counts each
file using max(logical length, allocated blocks), including sidecars and manifests.
It never reads backup payloads, deletes evidence, changes budgets or repairs modes.
Unexpected parent entries, links, invalid ownership/modes and exceeded inventory
bounds fail closed. Inventory is limited to 4096 entries and four directory levels.

Implementation: [M4 inventory](../../engine/detection/m4_storage.py),
[live guard selection](../../engine/detection/m4_live.py) and
[migrator](../../engine/detection/m4_migrate.py). The generic store accepts a guard
class; M4 selects this inventory. The shared M3 guard has only an inventory-method
hook whose default remains its original directory iteration. No M3 source scope,
policy values, protocol, schema or default admission decision changed.

The synthetic filesystem harness now puts its external filesystem filler outside
the M4 state container, on the same private ext4 image. This distinguishes external
filesystem occupancy from actual M4 state and keeps the new strict inventory
honest; no production guard is bypassed to make the filesystem test pass.

## Tests and actual sandbox boundaries

Three implementation regressions extend the focused suite to 28 cases and total
M4 scope to 96:

- Retained-backup logical bytes trigger state admission before import/progress;
  shrinking only the newly created test filler restores normal import/evaluation.
  Original events remain unchanged and unevaluated.
- An unsafe backup link produces unknown/blocked admission without following it
  for payload access or changing stored history.
- A real pinned SQLite reader prevents WAL reuse; normal guarded transactions
  reach critical admission before the WAL ceiling. Pending evaluation remains
  pending while blocked; releasing the reader/checkpointing permits one finding.

For targeted WAL growth, each transaction repeats the same `user_version=2`
header marker. SQLite appends real WAL frames while event/rule/finding rows and
cursor contents remain unchanged. This is test-only metadata churn, not an
application event workload or a throughput benchmark; production has no injection
flag or background header-churn loop.

Actual Ubuntu sandbox scope:

```sh
sudo python3 -B tests/integration/m4_trial_ubuntu.py --phase synthetic --rule --recovery --budgets --expected-manifest MANIFEST
```

The budget option refuses live/non-rule phases. Its separate
[probe](../../tests/integration/m4_budget_probe.py) refuses root execution and
requires canonical private fixture paths plus physical mount aliases for both
fixed M3/M4 paths before opening the destination. It runs under the ordinary
hids-ingest sandbox: source read-only, production sockets hidden, no added
capabilities. Root must verify the previously recorded guest UUID and pinned SSH
endpoint before invoking this older trial entry; the filesystem scope also checks
the exact UUID in its own CLI preflight.

| Boundary | Observed bytes / behavior |
|---|---|
| Normal WAL ceiling | 16,941,696 bytes, unchanged |
| WAL critical refusal | 10,592,256 bytes after 2569 completed header-write transactions; reserve/critical logic stops before ceiling |
| Normal aggregate ceiling | 268,435,456 bytes, unchanged |
| Aggregate critical refusal | 201,523,200 accounted bytes, including retained backup area; no import/progress writes |
| Reader release and checkpoint | WAL admission returns normal; history unchanged |
| New synthetic backup filler restored to zero length | Aggregate admission returns normal; evidence remains retained |
| Final synthetic store | 18 events, two findings, zero pending; old 16 events remain unevaluated |

The 192 MiB filler is a real private file with a sparse logical length; its length
is intentionally counted by the approved max(length, allocation) accounting.
It does not represent 192 MiB of collected data or require that much physical
allocation. The guard remains application admission, not a hard quota against
external writers or a guarantee against a race after inspection.

## Executed checks and protected evidence

Local full M4 scope passed 96 tests. Verified Ubuntu workflow passed 96 M4 tests,
87 M3 regressions and demo at
`/home/ivy/hids-m4-fixture.etjurv8x/results/run-20261112T115519Z-17d147837cf9/report.json`.

Source `hids-src-20261112T115456Z-ce7e5703ad08`, manifest
`36e5eb8c468165549fe1ff00043e38262c1828c6961bb6df01384a813c46774a`.
Actual namespace/migration/crash/budget report
`/var/tmp/hids-m4-handoff._191n2r0/report.json` returned passed/restoration verified:
all four worker SIGKILL boundaries, late A/repeat idempotency, old-plan refusal,
mode/generation controls and both budget recoveries passed together.

The updated real-filesystem full/read-only scope was re-run from the same source:
`/var/tmp/hids-m4-filesystem.jfcco7he/report.json` returned passed/cleanup verified/
production preserved, including actual SQLITE_FULL at import and finding writes,
pending retry and read-only startup. Parent log
`/root/hids-m4-budget-fs-job.rk88ot19/run.log`. No root/data filesystem was filled
or remounted; the new image remains retained and its loop device detached.

## Independent real-state verification and remaining gates

Independent inspection checked exact Linux 2 guest UUID, 29 installed hashes,
357 real M3 database files, exact M3 config/Audit config/plugin/rules baseline,
all four original Audit inodes/byte prefixes, no active M4 unit and no host M4
trial config. Real M4 remains 19 events/two bindings/one rule/three evaluations/
one finding with integrity/foreign keys passing. All 16 original event rows equal
the intact v1 backup. Reading the new guard's metadata inventory on the real state
reported normal admission and exactly 196,608 accounted bytes, equal to the
complete parent inventory; no writer was opened and no code was installed there.

This corrects runtime retained-backup admission and exercises selected WAL/state
refusal/recovery. It does not change the trial budgets into release defaults,
authorize unattended operation or finish representative native workloads,
long-duration/resource acceptance, API authentication, packaging or distribution
review. No commits or pushes were made.
