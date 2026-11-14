# M3 integration-build closeout and M4 entry decision

Status: bounded integration transition accepted by the owner alongside the M4
fixture contract after its walkthrough. This is not a v0.1 release declaration or a waiver of
existing decisions. Baseline: published `d921a2b`, production code from `f6c0259`.

## Accepted bounded stopping point

Freeze the supported Ubuntu 26.04 AArch64 M3 execution integration as the input
foundation for an isolated M4 fixture pilot. Do not keep adding unrelated failure
permutations before beginning detection. Preserve unsupported cases and reopen M3
when a supported-path defect or relevant code/source/dependency change warrants it.

M3 means existing Audit plugin → bounded C++ reconstruction/validation → protected
IPC → independent Python validation → durable SQLite, with authorization and
honest operational health. It does not mean every possible Linux execution form,
a complete product, an installer or a dashboard. Original local-file-generation
replay/retirement and archival gates are superseded/future, not missing plugin code.

## Finite entry checklist

| Gate | Evidence and disposition |
|---|---|
| Real end-to-end supported source | Eight real successful variants plus a rejected failed attempt; explicit current-tail authorization; EOE-backed acceptance; unchanged parser/privacy contract. [Native forms](../validation/m3-native-workload-validation.md). Satisfied within recorded profile. |
| Durable disposition and transport | Atomic event/metadata/progress, deduplication, lost ACK/recovery, interruption/late suppression; 58 SIGKILL boundaries and real reboot evidence. [M3 record](../../tests/integration/M3-README.md). Satisfied for executed cases. |
| Privilege and human access | Native reader and backend identities separated, root control, authenticated data peers, protected state/endpoints and separate approved checker. Installed acceptance passed. Satisfied; no new grants proposed. |
| Honest health and rejected data | Unknown/stale counters remain unknown, source readiness is not coverage, incomplete/unsupported groups do not become successful executions. Read-only metadata status remains available without fabricating unreadable history. [Read-only status](../validation/m3-readonly-status-validation.md). Satisfied within recorded limits. |
| Resource/storage behavior | Provisional assembly bounds, backpressure/deadlines, WAL admission, actual full/read-only filesystems, actual per-user quota with rollback/recovery. [Filesystem](../validation/m3-filesystem-validation.md), [quota](../validation/m3-quota-validation.md). Satisfied for selected cases, not final resource tuning. |
| Service response to actual quota | Last identified closeout test: actual reader/backend peer identities and protected control/data IPC; denied write gets no success ACK; root failure/lease denial stays latched after quota release; restart preserves B/interrupted A. Passed; detailed record below. |
| Rotation and preservation | Two administrative rotations retain reader/stream identity and original source byte prefixes. No HIDS deletion. External host finite retention is not an indefinite preservation guarantee. [Rotation](../validation/m3-rotation-validation.md). Scoped gate satisfied. |
| Repeatable lab verification | Verified source snapshots, dependency/build identity, fresh regressions, retained reports, explicit opt-in scopes and restoration. Latest production code passed all 17 live checkpoint phases; quota scopes add separate evidence. Satisfied for provisioned VM, not new-machine distribution. |
| Consumer boundary | M4 may consume only accepted, committed, independently validated events with source/activation/generation/native identity and profile. Rejected/timed-out/interrupted groups and unavailable status are not event substitutes. Must be enforced by the M4 pilot contract. |

No remaining observed supported-path implementation failure is recorded after the
last test. This is a statement about inspected evidence, not proof of every path.
M1/M2 acceptance and other adapters retain their own scopes; this review does not
upgrade their historical results or make Audit a replacement for cn_proc.

## What remains before release, without blocking a fixture-only M4 pilot

These are **preserved requirements**, not newly deferred owner approvals:

1. D-15 owner-reviewed resource acceptance: idle/representative host workloads,
   approved CPU/RAM/disk/backlog thresholds and tuning. Existing two-hour fixture
   measurements are valuable but apply to their exact earlier snapshot; no final
   release budget is invented. D-15 is explicitly a v0.1 resource-acceptance gate.
2. D-13 dependency/security/license/build/distribution review, reproducible package,
   install/upgrade/uninstall and target provisioning. Existing lab deployment is
   not a distributable package. No project/dependency license choice is implied.
3. Supported coverage expansion only when claimed: further native/source forms,
   other quota types and representative workloads need their own positive and
   failure cases. Rejecting unsupported forms is different from supporting them.
4. Broader VFS/device/power-loss and installed-systemd failure variants remain
   unproven. The private Service tests do not simulate every installed sandbox or
   storage failure. Do not translate test counts into reliability percentages.
5. External Audit retention/cleanup and dispatcher freshness remain host-administered
   limits. HIDS does not promise lossless history or change logging policy to hide gaps.
6. v0.1 still needs source-selection UX/consent, the other supported source paths,
   one-event rules, alert persistence, protected API/dashboard and their own gates.

## The last bounded closeout action

The old quota record verified direct storage methods. The added test now drives
actual version-3 Service IPC through a real `hids-audit` peer to `hids-ingest`,
with root-owned control descriptors and real root client checks. It commits B,
registers EOE-backed A, checkpoints committed pages, applies the private image's
UID quota, and sends A's accept request over the socket. It checks closed delivery
without a success ACK, root `storage_failure` despite normal sampled free space,
denied activation/leases, unchanged B and nonaccepted A. Quota release alone leaves
the failure latched. Explicit restart passes integrity, preserves B, durably
interrupts A and still requires new authorization.

This is actual protected Service/peer transport on private endpoints with synthetic
normalized data. Native parsing and installed-systemd/live-source evidence are
separate. No production module or global host policy changes for this test.

Final quota/Service run: `hids-m3-lab-5571cb8a78dc`, eight phases passed,
24.045 summed guest phase seconds, source snapshot
`fb193a787391ec2ce7dbe60016a88328c1d46e0e054d4137f541d974cc1cbd9d`.
Exact reports and independent preservation/cleanup checks are in the
[quota record](../validation/m3-quota-validation.md#service-ipc-extension-and-final-closeout-run).
All 355 original databases, four source prefixes and 29 installed artifacts were
verified; Audit remains active with all M3/checker units inactive. Production code
is unchanged, so the earlier full live checkpoint remains the regression baseline:
`hids-m3-lab-905e404c024d`, all 17 phases passed in 142.627 summed guest seconds;
report `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-905e404c024d/run-20261111T224552Z-4d5869ccdc35/report.json`.

## Accepted M4 fixture entry

The owner reviewed and accepted [the M4 pilot contract](m4-pilot-contract.md).
The first implementation is a synthetic,
opt-in one-event fixture path with bounded declarative predicates and a fresh
private prototype database. No live source hookup, M3 database migration,
user-facing threat classification, ATT&CK coverage or production rule defaults
are authorized by that fixture-pilot approval.

D-07 and D-08 reserve production persistence and supported rule/severity policy for
owner review. The owner accepted the concrete fixture semantics, with production
schema, live integration and real security rules outside that approval. The
[fixture pilot now passes its acceptance suite](../validation/m4-pilot-validation.md).
This preserves all release gates above; it does not declare v0.1 release-complete.
