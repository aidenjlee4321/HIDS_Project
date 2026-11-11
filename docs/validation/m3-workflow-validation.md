# M3 workflow acceptance — November 11, 2026

This validates the development-efficiency workflow, not M3 release readiness.
Product baseline: pushed `ff90498`. The workflow changes were uncommitted during
acceptance. Entry points: [current state](../current-state.md) and
[runner guide](../m3-workflow.md).

## Scope and permissions

The owner approved canonical project edits and private temporary outputs on the
Mac. No Mac settings, installed software, SSH credentials/configuration or external
application state were changed. The existing authorized Linux 2 VM was used for
builds, deployment and isolated acceptance. No Git commit or push was performed.

The VM lab activation budget was deliberately raised from 128 to 256 because the
retained history left insufficient capacity. Original bytes are protected at
`/root/hids-workflow-budget.8035odje/config.json`; no history was deleted. Each
successful runner restored the new 256-budget baseline exactly.

## Local and failure checks

The final local focused run passed 70 M3 Python tests and 34 workflow tests
(21 existing workflow tests plus 13 new controls). Its private report is
`/private/tmp/hids-workflow-acceptance-local/run-20261111T151438Z-c1718fb0d3d4/report.json`.
The new tests exercise complete source inventory, narrow fixture inclusion,
archive metadata normalization, nonzero/skip/zero-test failure, timeout handling,
private logs/hashes, cache integrity, stable dependency identities, preflight
refusal, temporary executable restoration, scoped unit cleanup and pinned SSH keys.

Actual VM preflight refused the initial inadequate activation budget before any
build/deployment phase. Its report is
`/var/tmp/hids-m3-workflow/run-20261111T134052Z-4fc4b07253fa/report.json`.
Additional failed pilot attempts exposed and led to fixes for ordinary-user model
execution, the extensionless launcher omission, rapid test-induced systemd
start-limit contamination and reset behavior for already-unloaded units. Their
reports/logs were retained. These attempts were failures, not partial acceptance.
Final acceptance below was rerun after the fixes.

## Two successful full checkpoint runs

Both runs used `checkpoint --live-audit` through the one-command Mac-to-VM driver.
Every applicable test was re-executed: 70 M3/34 workflow Python tests, 25 native
sanitizer groups, 124 linked native boundary cases, 124 allocation cuts, 11 parser
API faults, 58 actual SIGKILL cases, producer transport, installed event/storage,
real live-Audit/runtime/capacity, 4096-event load, resource limits, both installed
parser faults, health isolation, periodic reporting and lifecycle recovery.

| Measurement | Uncached | Cached |
|---|---:|---:|
| Mac driver elapsed seconds | 183.307 | 134.889 |
| Guest elapsed seconds | 197.268 | 144.614 |
| Guest phase seconds | 194.249 | 141.776 |
| Cached-artifact compile commands | 6 | 0 |
| Required non-build phases passed | 17 | 17 |
| Full retained phase log bytes | 11,177 | 11,178 |
| Phase-summary console bytes | 2,316 | 1,651 |
| Cleanup | Verified | Verified |

Observed Mac driver elapsed time fell 26.4%; guest elapsed time fell 26.7%. This is
one paired VM experiment, not a general speed guarantee. Host/guest clocks are
separate: compare each clock's runs, not host values against guest values. Guest
phase totals omit preparation/deployment/cleanup overhead. Fresh sanitizer builds
still ran; only the six verified production/test helper executables were reused.
The shorter phase summaries retain full private evidence and are not token counts.
Exact token/billing savings were not measured.

The same cache key was used:
`ae541b7862820e3fbd725221f2a43ca968cc7cc13aad44246f59009c0710117e`.
It incorporates 513 compiler-reported transitive inputs, explicit dependency and
compiler fingerprints, flags, native inputs, runner code and package inventory.
Both snapshots had 196 source files. Their manifest digests differ because the
session/permission documentation changed between snapshots; the native/cache
identity and ordered set of required non-build phases matched exactly. All phase
exit codes were zero with no detected skips.

| Evidence | Private location |
|---|---|
| Uncached guest report | `/var/tmp/hids-m3-workflow/run-20261111T135418Z-5d846d0b220f/report.json` |
| Cached guest report | `/var/tmp/hids-m3-workflow/run-20261111T135836Z-b9bcb2914837/report.json` |
| Uncached Mac report | `/private/tmp/hids-m3-host-workflow/runs/run-20261111T151441Z-8e767b31534c/report.json` |
| Cached Mac report | `/private/tmp/hids-m3-host-workflow/runs/run-20261111T151839Z-ccfe3ec719c4/report.json` |

Each guest run verified 29 matched installed application/service files. Independent
post-run checks confirmed those hashes, original Audit policy against both the
run baseline and the earlier protected reboot manifest, Audit active, restored
256-budget HIDS configuration, state directory 0700 and ingest-owned files 0600.
All M3/checker units were inactive and temporary fault/isolation binaries absent.
There were 200 retained SQLite files including control after acceptance.

## Limits and next use

All six efficiency steps are implemented and exercised. This does not establish
hard disk quotas, multi-hour/representative source coverage, approved release
performance thresholds, physical power-loss behavior, packaging/license approval
or later dashboard/detection work. Reboot, quiet-source/rotation, paced/long-duration
and M1/M2 suites remain separately selected gates. Do not describe the checkpoint
profile as every possible HIDS acceptance test.

Future work should begin from the compact handoff, choose the affected test tier,
inspect only summary/failure excerpts initially, and rerun broader acceptance when
changes or failures justify it. A failed run remains failed even if cleanup succeeds.
Commits/pushes and changes outside the owner's approved Mac scope still require
specific permission.
