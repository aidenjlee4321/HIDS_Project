# HIDS current state and session handoff

Start here for ongoing work. Read the linked authority for the area being changed;
use chronological chat/evidence only when a decision or result needs tracing.
This summary does not override the owner, AGENTS.md or accepted decisions.

## Current checkpoint

- Latest pushed checkpoint: `19e2bb10cc0d1e6359dd637c07a3e5d98ce2d166`
  on `main`, GitHub `aidenjlee4321/HIDS_Project`: plugin-stream rotation and
  source preservation. Publication was owner-approved and remote main verified.
  Earlier `fc77ca5` includes storage accounting/performance and the two-hour load.
- Owner-approved checkpoint for commit/push: real-native execution acceptance and two parser
  corrections: quoted native PROCTITLE and separate non-execution Audit-family
  framing. Eight successful native variants and one failed attempt passed with
  explicit USER/health background traffic; execution semantic checks and EOE-only
  completion remain strict. Full live checkpoint passed all 17 phases. Current
  counts: 79 M3 + 40 workflow tests, 26 native groups, 128 native contract cases,
  124 allocation cuts, 11 API faults and 58 actual SIGKILL boundaries. Exact cleanup,
  source prefix integrity and 29 installed hashes independently verified. See
  [native form evidence](validation/m3-native-workload-validation.md) for retained
  failures/fixes, final reports and remaining limits. The owner approved committing/pushing this checkpoint to `main`; verify Git
  for publication status.
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
  After native-form/full-checkpoint acceptance, 305 SQLite files including control
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
