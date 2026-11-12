# HIDS current state and session handoff

Start here for ongoing work. Read the linked authority for the area being changed;
use chronological chat/evidence only when a decision or result needs tracing.
This summary does not override the owner, AGENTS.md or accepted decisions.

## Current checkpoint

- Latest pushed checkpoint: `bfb4592eaa48763a8fde87504a1c70266e450030`
  on `main`, GitHub `aidenjlee4321/HIDS_Project`: real filesystem capacity,
  SQLite FULL and read-only recovery tests. Publication was approved and verified.
  Prior native checkpoint `2c76070`, rotation `19e2bb1`, performance/soak `fc77ca5`.
- Owner-approved checkpoint for commit/push: read-only startup root status. Existing private state keeps its
  exclusive writer lock; collection/writes remain blocked. Readable SQLite history
  uses mode=ro and honours WAL. If read-only WAL auxiliaries are unavailable,
  root gets known metadata with interval/history explicitly unavailable, never
  immutable journal bypass. Real private Service/root-client IPC passed read-only
  status, activation/lease rejection, writable latching and explicit restart.
  Focused: 87 M3 + 40 workflow tests. Full live regression passed all 17 phases.
  [Read-only evidence](validation/m3-readonly-status-validation.md) records limits
  and exact jobs. Owner approved commit/push to `main`; verify Git for publication status.
- Published native checkpoint: eight successful variants and a rejected failed
  attempt with explicit USER/health background traffic; strict execution validation
  and EOE-only completion. Full live checkpoint passed all 17 phases, 79 M3 + 40
  workflow tests, 26 native groups, 128 native contract cases, 124 allocation cuts,
  11 API faults and 58 actual SIGKILL boundaries. [Native form evidence](validation/m3-native-workload-validation.md).
- Rotation acceptance already passed both real signals, source inode/byte
  preservation, unchanged reader/generation and three known EOE-backed executions,
  including a writer stall. Full live checkpoint passed 17 phases; final component
  checks passed 79 M3 + 40 workflow tests. [Rotation evidence](validation/m3-rotation-validation.md).
- The current plugin source decision supersedes file-tail generations/replay and
  associated retirement mechanics. Do not implement older unchecked backlog items
  as missing plugin behavior. Original Audit logs remain host-administered;
  indefinite preservation under external finite rotation is not guaranteed.
- Next work: reconcile remaining native forms/representative workload evidence,
  release resource thresholds and packaging/distribution/license gates. Do not
  claim M3 release readiness or start M4 solely from these passing tests.
- Use the verified workflow whenever applicable. Mac work remains limited to
  authorized project edits/private temporary outputs; ask before system/settings,
  software/credential changes and specific Git publication.
- Canonical repository: `/Users/aidenlee/Downloads/hids`; the chat workspace is a
  different directory. Verify branch, working tree and remote before Git mutations.
- M3 implements root-authorized current-tail Audit execution, separate native
  reader/backend identities, bounded reconstruction, independent validation,
  atomic SQLite/progress, interruption suppression, resource handling, health,
  proactive storage admission, separate event clocks and root rejection diagnostics.
- Previous product acceptance: 70 M3 Python tests, 25 native groups, 124 native
  boundaries, 124 allocation cuts, 11 API faults and 58 actual SIGKILL cases;
  installed live/runtime, load, storage, resource and health tests passed.
  Exact conditions and limits: [M3 evidence](../tests/integration/M3-README.md).
- Dashboard, detection rules, full packaging, broader workloads/native coverage,
  release thresholds and distribution/license approval remain unfinished. Passing
  this tooling workflow does not close those product gates or begin M4 by itself.

## Authority and workflow rules

1. Prioritize safety, then progress, then avoiding unnecessary interruptions.
2. Reversible implementation/testing and Linux 2 VM work are authorized.
3. Ask for specific commits/pushes, fundamental architecture/product decisions,
   breakage needing owner action or blockers unresolved with available access.
4. For this efficiency task, the owner approved Mac project edits in the canonical
   repository and private temporary build/snapshot/test outputs. Ask before Mac
   settings changes, software installation, credential configuration or other
   modifications outside that scope. VM authorization is broader.
5. Preserve C++ native collection/normalization, Python validation/SQLite ownership,
   protocol boundaries, least privileges, root-only human security-data access,
   local-first behavior, no automatic remediation and no evidence deletion.
6. Product installation/runtime must not change Audit/journald/PAM policy. Explicit
   lab live-policy tests are separate, opt-in and must restore their exact baseline.
7. Keep secrets, raw security data and private test logs outside Git. Do not paste
   credentials into documentation, reports, SSH options or command strings.

Full constraints: [AGENTS.md](../AGENTS.md). Scope: [ADR-007](decisions/007-initial-release-scope.md).
M3 authority: [specification/register](implementation/m3-linux-audit-spec.md).

## VM and next-run prerequisites

- UTM guest name Linux 2; Ubuntu 26.04 AArch64; SSH user `ivy`.
  Previously observed address `192.168.64.7` may change. Verify reachability and
  the existing pinned host key; do not disable host-key checks to get past failure.
- Password/other authentication stays in the existing authorized access channel,
  never in this file. The runner accepts interactive SSH/sudo authentication and
  neither installs keys nor changes Mac SSH configuration.
- Previous staging: `/home/ivy/hids-m3-runtime.6MmspJ2L`; matching pre-existing Audit
  headers are in its `headers/` directory. The runner verifies dependencies and
  creates a new complete source snapshot/staging directory for each VM invocation.
- Installed application `/usr/lib/hids`, state `/var/lib/hids/m3`, configuration
  `/etc/hids/m3.json`; resolve service accounts through NSS, not hardcoded IDs.
- The persistent VM-only lab activation budget was deliberately raised from
  256 to 512 for continuing acceptance, preserving all prior history. Exact old
  configuration: `/root/hids-workflow-budget.9sdud64k/config.json` (root-only).
  After read-only/full-checkpoint acceptance, 355 SQLite files including control
  remain. The workflow restores the 512 baseline after each run. Check remaining capacity
  before further runs; never delete history to make room.
- Two source rotations left four Audit log files, highest suffix `.3`, under the
  original five-file ROTATE policy. Repeating the two-rotation experiment now
  correctly fails safe preflight. Do not weaken that guard or remove old logs.
- VM workflow requires M3/checker units already inactive and Audit already active.
  It never takes over an active collection session or reboots automatically.

## Normal work cycle

Use [the M3 workflow guide](m3-workflow.md). Run focused tests during iteration;
component tests for affected boundaries; one applicable checkpoint suite once code
settles. Re-run checks after fixes according to the affected scope. Native or
privilege-boundary changes require Ubuntu evidence; Mac passes cannot substitute.

Every run keeps a private report/log directory. Link results and limitations from
this summary; append detailed evidence only for meaningful new behavior or results.
Record the current task and next action before a handoff. Source/build hashes,
exit codes and cleanup checks establish reproducibility; a test count alone does not.

## Next product work after tooling acceptance

Review the remaining M3 gates against the specification and measured evidence:
broader representative workloads/native forms, controlled performance comparison,
remaining source-retention/rotation cases, release thresholds and reproducible
packaging/distribution. Preserve owner approvals; do not reopen settled decisions
because an older backlog checkbox is still empty.
