# M3 plugin-stream rotation and source-preservation acceptance

## Scope and authority

The current M3 specification supersedes file-tail ingestion, file-generation byte
cursors and replay with the owner-approved outbound Audit plugin and EOE-only
completion. Stream generations identify plugin connections, not log files. This
acceptance exercises administrative Audit file rotation while that stream remains
active; it does not implement the historical file-tail or archival design.

The Linux 2 lab authorization covers reversible source tests with exact policy
restoration. Production HIDS still makes no Audit configuration/rule changes and
never deletes original source logs. Source files remain under host administration.

## Implemented safety checks

`tests/integration/m3_rotation_ubuntu.py --live-audit` requires root, inactive M3
units, active Audit, no existing rules and a recognized numeric ROTATE layout.
Preflight uses the highest existing suffix, including gaps, and reserves one
additional retention slot beyond both requested rotations. It also requires at
least 1 MiB below the active log's configured size ceiling, rechecks headroom
before each signal, and rejects symlinks, hardlinks and unknown rotation layouts.
This is a controlled quiet-host lab check, not protection against concurrent
administrator policy changes or an arbitrary audit storm.

The test retains root-only inode/device, size, ownership/mode and SHA-256 prefix
metadata. It copies no raw records. After each rotation and cleanup it locates
all original inodes and verifies their complete pre-test byte prefixes. Renaming
and appending are allowed; disappearance, truncation, overwrite and broadening
human access fail acceptance. It neither deletes logs nor temporarily raises the
host's rotation limit. Configuration, the exact PID-scoped test rule and temporary
plugin are restored/removed on exit; M3 units stop and Audit remains active.

The workflow exposes this as a separate `--experiment rotation --live-audit`
scope. Missing live opt-in fails before host staging or guest deployment. Default
component/checkpoint runs do not consume finite source-retention headroom.

## Completed Ubuntu evidence

Ubuntu 26.04 AArch64, auditd/libauparse 4.1.2; existing dependencies and installed
least-privilege M3 services. Original host policy: ENRICHED, 8 MiB active-file
ceiling, five retained files, ROTATE, no rules. The test temporarily selects RAW
and the canonical plugin launcher, then restores the exact original policy.

Passed detached job `hids-m3-lab-3f7219f72b2f`:

- Guest workflow report:
  `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-3f7219f72b2f/run-20261111T184842Z-f6461e5c7ee4/report.json`.
- Protected source metadata/report: `/root/hids-m3-rotation.z0l87vok/report.json`.
- Verified source snapshot SHA-256:
  `915e2037578a3dbf5b2ccab8cf042d6ff1fc2568e8c85ece021188d4e0df27d6`.
- Full workflow 22.052 guest seconds; explicit rotation phase 1.592 seconds.
  Native artifact cache hit; sanitizer/parser/crash checks still ran afresh.
- Two real `auditctl --signal rotate` operations passed with the same reader PID,
  plugin-stream generation and Audit daemon PID; source readiness remained true.
- Three distinct PID-scoped real executions were accepted exactly once, each
  with a durable EOE, expected executable/comm and successful outcome. One is the
  baseline; the next two are generated immediately before each rotation. The
  second rotation holds SQLite's writer lock through the signal for a short
  bounded interval, then verifies acceptance after releasing it. This does not
  claim an exhaustive lossless execution census or a separate post-final-rotation
  execution probe.
- Original active inode 1180401 (134,517-byte initial prefix) ended at `.2`;
  original `.1` inode 1182568 (8,389,050 bytes) ended at `.3`. All original bytes
  were retained. Four source files remained, below the five-file policy limit.
- Kernel lost count stayed zero and daemon PID stayed 1629. Final event counters:
  three observed executions; zero timeouts, late records or resource incidents.
  Six other groups were rejected with `execve_missing_argc`, rather than silently
  accepted. These
  counters are retained honestly; this is not a claim of zero rejected groups.
- Exact Audit policy/rules and HIDS configuration restoration, installed hashes,
  state ownership/modes and inactive M3/checker units passed workflow cleanup.
- Focused regressions: 78 M3 Python tests and 40 workflow tests. Eight new isolated
  source-safety tests cover suffix gaps, byte/retention headroom, links/layouts,
  prefix preservation, truncation/overwrite/disappearance, permissions and continued
  cleanup after an independent restoration failure. The
  first Mac run caught an unsupported `Path.hardlink_to` test helper on existing
  Python; replacing it with standard `os.link` fixed the test. No host software was
  installed. Native checks: 25 groups, 124 field-boundary cases, 124 allocation
  cuts, 11 API faults and 58 actual SIGKILL cases.

The persistent **VM-only** activation budget was deliberately raised 256 → 512
before this run, preserving all 244 prior SQLite files. Original configuration is
protected at `/root/hids-workflow-budget.9sdud64k/config.json`. The workflow restores
that 512 baseline; this is capacity provision, never history-deletion permission.
Host/guest timestamps differ; elapsed values above use the guest clock only.

## Full checkpoint and harness hardening

The subsequent full live checkpoint passed all 17 phases with successful job exit
and verified cleanup: `hids-m3-lab-e041ef38190c`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-e041ef38190c/run-20261111T184947Z-1aa2ab403b77/report.json`.
Elapsed 147.484 guest seconds, 144.025 summed phase seconds. This includes transport,
installed metadata/storage, runtime and native live Audit, 4096-event load,
resource pressure, installed allocation/API faults and health isolation/periodic/
lifecycle checks. It does not repeat the explicit rotations.

Subsequent lab-harness review strengthened cleanup to attempt every independent
restoration even if an earlier one fails, and made prefix verification reject
any permission bit added relative to the original file, including group execute.
Isolated regression tests exercise these negative paths; the focused Mac workflow
passed 79 M3 + 40 workflow tests. These changes do not alter product code or the
successful rotation path. The reports above identify the exact earlier snapshots;
they do not claim a second real two-rotation run of the hardened harness.

Final Ubuntu component validation of the hardened helpers passed all nine phases:
`hids-m3-lab-0a6a88da69cb`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-0a6a88da69cb/run-20261111T185338Z-a4aea2b34234/report.json`.
All 79 M3 Python and 40 workflow tests passed under the real root workflow,
including its unprivileged subprocess phases; fresh sanitizer/crash and installed
transport/metadata/storage checks passed. Elapsed 26.069 guest seconds, native
cache hit. No extra real rotations were attempted.

Final independent verification matched Audit configuration/plugins/rules against
`/root/hids-m3-reboot.xbahp1tb/manifest.json`, reverified all four final rotation
snapshot inode/byte prefixes after the full and component regressions, matched
29 installed application files, confirmed state 0700/ingest files 0600, configuration
root-owned 0640 with lab budget 512, Audit active and all M3/checker units inactive.
Fault/probe executables and temporary Audit plugin were absent. All 275 SQLite files
including control remain; none were deleted. The owner subsequently approved commit/push of this checkpoint to
`aidenjlee4321/HIDS_Project` on `main`; verify Git for publication status. No Mac system, software or credential changes were made.

## Limits and next gates

The same two-rotation test now deliberately refuses another run: highest suffix
three leaves insufficient room to rotate twice while preserving the extra spare
slot. Do not delete source files, shorten retention or weaken the guard merely to
repeat it. Use a separately provisioned source-test environment for broader
rotation variants. Existing source originals remain in the host's finite retention
pool: a later host-managed rotation can eventually remove them. HIDS cannot promise
indefinite retention or prevent external cleanup with the current plugin design.

File-generation replay, missing-file recovery, full-generation processing/retirement
and archival handoffs belong to the superseded file-tail design or separately
reviewed future work. They are not missing plugin implementation steps. Already
executed crash/reboot tests cover stream interruption independently; these two
rotations add live administrative-rotation evidence, including a short writer
stall. They do not prove indefinite lag preservation, hard device quotas,
physical power-loss behavior, all native forms/workloads, approved release resource
thresholds or reproducible packaging/distribution/license acceptance. M3 and the
product are not release-complete.
