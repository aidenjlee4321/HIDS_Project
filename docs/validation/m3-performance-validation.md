# M3 performance and longer-workload review — November 11, 2026

This record extends [M3 verification](../../tests/integration/M3-README.md).
The [workflow](../m3-workflow.md) is the default execution path. Performance and
soak are explicit experiments, not substitutes for full checkpoint acceptance.
Release thresholds and broad native/source coverage remain unresolved.

## Controlled comparison design

`m3_performance_ubuntu.py` runs the actual Service/Runtime classes and production
C++ reader under the existing backend/reader identities. Private fresh state is
created per trial on the same filesystem as installed M3 state. The baseline code
never opens installed HIDS databases. Both versions receive the same invented
six-record execution fixture, warm up with 512 events, then commit 4096 measured
events in batches of 64. Order is before/after/after/before/before/after, with three
measured trials per version. A separate profiled trial is excluded from medians.

Every trial verifies exact identities, normalized-payload equality across versions,
all six registered positions per event, resolved frontier, no timeout/late/resource
rejections and, where supported, all observation metadata. CPU is read from the
actual process counters. No Audit policy or installed application version changes
are needed for this comparison. The standalone benchmark does not recreate the
systemd sandbox/timer or prove real-source execution coverage.

## Initial safeguard/metadata cost

Baseline `cde78d9` predates the storage/timing/rejection continuation; the comparison
therefore measures the combined feature bundle, not storage checks alone. The six
trial results were functionally complete and their normalized payload hashes
matched. Median throughput was 194.810 events/s before and 156.657 events/s after
(19.6% lower). These trials used fresh state without synthetic history files.

The outer foreground connection expired before aggregate workflow reporting, so
this attempt is **not a complete workflow acceptance pass**. Its private benchmark
result and per-trial state were retained:
`/var/tmp/hids-m3-workflow/run-20261111T150049Z-45d1baecc42c/performance.json`.
Canonical configuration was independently checked against the pre-run baseline.
This exposed the need for disconnect-independent VM job supervision, now implemented.

The separate current-backend profile showed storage observation/accounting work in
addition to SQLite transaction cost. Inspection found repeated whole-directory
summation and WAL-name filtering on the hot path. The optimization below removes
that repeated calculation without changing transaction/inspection boundaries.

## Storage-accounting optimization

The guard now maintains a byte total and a separate WAL-file map. Active-file
updates adjust the total by the exact size difference; the existing periodic full
scan rebuilds both caches. Every previous active-file ownership/mode/link/size check,
filesystem-free inspection, reserve, threshold and checkpoint policy remains.
Inspection errors still return unknown and block ordinary writes. No transaction
batching, durability reduction, deletion, eviction or automatic authorization was added.

A new test covers 200 retained files, WAL creation/growth/removal, periodic rescans,
unsafe metadata and recovery. The focused suite passed 71 M3 and 37 workflow tests
before the paired optimization experiment. Standard component acceptance passed:
`hids-m3-lab-e71902cb2953`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-e71902cb2953/run-20261111T154050Z-9adfdd2551b8/report.json`.
This includes actual pinned-WAL warning/stop/reclaim, quota-only degraded startup,
event metadata/rejection insert faults, native sanitizers, transport and crash cases.

The optimization comparison uses product checkpoint `ff90498` against the working
optimized backend. Both have the same metadata/safety features and native binary.
Both receive 200 identical private synthetic 4-KiB history files per fresh trial.
These model retained-file accounting cost, not actual historical Audit databases.

| Trial order | Before events/s | Optimized events/s | Before backend CPU s | Optimized backend CPU s |
|---|---:|---:|---:|---:|
| First pair | 161.988 | 178.700 | 9.81 | 6.49 |
| Middle pair, reversed order | 169.689 | 180.787 | 9.49 | 6.31 |
| Last pair | 156.199 | 167.643 | 10.19 | 6.78 |
| Median | 161.988 | 178.700 | 9.81 | 6.49 |

Observed median throughput improved 10.3%; median backend CPU per measured 4096
executions decreased 33.8%. All native payloads remained identical and all correctness
checks passed. Three trials per variant and overlapping ranges do not establish a
universal gain or an approved release threshold. Do not compare these history-file
medians directly with the earlier fresh-state bundle comparison.

The supervised experiment passed with cleanup verified:
`hids-m3-lab-dc2d1e0d4977`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-dc2d1e0d4977/run-20261111T154332Z-4d841a8f46f5/report.json`.
The adjacent `performance.json` retains individual timings, CPU/RSS/disk samples,
profile summaries, normalized-payload hashes and evidence paths.

## Completed two-hour workload

A short supervised varied-load run passed before starting the longer test:
`hids-m3-lab-d7354231ef6b`; its workload took 28.252 seconds including the separate
32-lock pressure phase and ten seconds of paced/varied delivery. The job continued
and completed after the initiating Mac connection closed.

The two-hour installed varied workload passed as `hids-m3-lab-d901ab055ee0`:

| Measurement | Executed result |
|---|---:|
| Paced phase, guest monotonic seconds | 7200.018 |
| Exact accepted executions / observation rows | 4096 / 4096 |
| Exact registered positions | 24,576 |
| Writer-pressure phase | 32 locks over 16.642 seconds |
| Additional writer locks during varied pacing | 9 |
| Collector RSS range | 4752–4752 KiB |
| Backend RSS range | 22,268–24,368 KiB |
| Collector CPU during paced phase | 8.24 seconds |
| Backend CPU during paced phase | 110.83 seconds |
| Event database | 1053 × 4096-byte pages |
| Retained resource observations | 119 |
| Observed storage states | Normal |

The fixture identities and all positions matched exactly; frontier equaled scanned
bytes, observation metadata covered every accepted execution, and there were zero
timeout/late/resource/rejected dispositions in the paced interval. The initial
incomplete A survived bounded writer pressure while 32 independent B executions
committed, then was rejected rather than accepted as complete. Burst sizes varied
between 16/64/128/32 events with proportional quiet periods. CPU values cover the
backend/collector processes, not the separate root health helper or the whole VM.
Backend memory stepped once and then largely plateaued; this is bounded two-hour
fixture evidence, not a proof that every workload is leak-free.

All configuration/policy/permissions/installed-file checks in the runner passed,
and the VM job exited successfully with M3/checker units stopped. Protected reports:

- Workflow: `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-d901ab055ee0/run-20261111T154948Z-1f529113c1cc/report.json`
- Full load measurements: `/run/hids-m3-load.f5olk63h/report.json`

The larger page/position budgets were temporary and the original lab configuration
was restored. This does not approve continuous-monitoring release defaults or turn
an intermittent fixture workload into representative real-host/native coverage.

## Full checkpoint and workflow follow-up

The full live checkpoint passed as `hids-m3-lab-64cdab1c5913`, including all applicable
Python/native/crash, actual live-Audit/capacity, resource, parser-fault, health
isolation/periodic/lifecycle and load gates. Report:
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-64cdab1c5913/run-20261111T175414Z-bb82fe7787f2/report.json`.

Later host-side watcher validation requires a job to exit before reporting success,
even when its completed report already exists. Focused tests passed 71 M3 and 39
workflow cases. The restrictive job umask also exposed two old negative-mode tests;
their synthetic unsafe fixtures now set their intended mode explicitly, preserving
the actual privacy checks and job umask 0077.

The successful jobs also exposed an efficiency regression: a unique job output
folder had unintentionally given each detached job its own binary cache. Cache
identity and integrity were correct, but reuse across jobs was impossible. The
host driver now passes an explicit shared VM cache root, separate from per-job
reports. Artifacts from the completed full checkpoint were ownership/hash-verified
and copied into the shared cache without changing or deleting the originals.
Two independent corrected detached component jobs then passed with the same shared
cache key, `cache_hit=true`, and zero cached-artifact build commands. Fresh native
sanitizer checks and all component tests still ran:

| Job | Guest elapsed seconds | Private report |
|---|---:|---|
| `hids-m3-lab-4a24052fefc0` | 26.654 | `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-4a24052fefc0/run-20261111T175913Z-d9d2cddb6bed/report.json` |
| `hids-m3-lab-fe7cfe8d30ac` | 30.454 | `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-fe7cfe8d30ac/run-20261111T180143Z-6db245e6445b/report.json` |

These runs used 71 M3 Python and 39 workflow tests. The final independent check
confirmed the earlier protected Audit-policy manifest still matched, Audit active,
exact source/configuration values restored (256 activations, 512 pages, 1024
positions), config root:ingest 0640, state directory 0700 and ingest-owned files
0600. All 29 installed application/service artifacts matched their accepted hashes,
all M3/checker units were inactive and temporary fault/probe binaries were absent.
There were 244 retained SQLite files including control. Remaining interval capacity
must be checked before future full runs; deliberately raise the VM-only lab budget
if needed rather than deleting history. No further test/implementation work remains
for this performance/workflow checkpoint; broader M3 gates below remain open.

## Remaining scope

Performance/soak results do not close representative real-host/native workloads,
rotation/source-retention preservation, physical power-loss/device faults, hard
filesystem quotas, approved release thresholds or packaging/distribution/license
gates. No fundamental architecture, retention/deletion or source-policy decision
was reversed. The accounting optimization preserved inspection cadence, safety
reserves, durability and explicit activation requirements. Mac changes remained
within the approved project/private temporary-output scope; no Mac system setup,
credential configuration or software installation was required. No Git publication
was performed for this checkpoint without a new specific approval.
