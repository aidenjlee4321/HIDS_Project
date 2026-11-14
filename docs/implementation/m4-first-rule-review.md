# First non-demo M4 rule: configured root-shell watchpoint

Status: owner accepted D-08/D-07 implementation and bounded acceptance. The
implementation and observed results, including the subsequent VM incident, are in
[first-rule evidence](../validation/m4-first-rule-acceptance.md). The remainder
records the approved review packet at decision time.

Original proposal: proposed for owner D-08 review, with a concrete D-07 schema/migration
extension. Production rules remain disabled. This document and the JSON proposal
are not an implemented/enabled security rule. Existing source/IPC/identity/storage
architecture and approved bounded trial budgets remain unchanged.

## Recommendation

Offer an **opt-in informational watchpoint** when one accepted execution reports:

1. The exact configured executable bytes `/usr/bin/dash` for this initial profile.
2. Effective UID (`euid`) equal to 0.
3. Successful execution.

Name: **Configured shell executed with effective UID 0**.
ID/revision: `linux.audit.configured-root-shell`, revision `1`.
Source: `linux.audit.aarch64.string/1` only. Default: **disabled**.
Definition: [proposed version-2 JSON](../../rules/proposals/configured-root-shell.json).

This reports a credential/executable condition, not maliciousness, interactive
access, a privilege escalation or a particular way privileges were obtained.
Authorized administration and scripts can match; one retained controlled script
execution demonstrably does. It creates no confidence score, ATT&CK claim,
correlation, remediation recommendation or automated response. Ordinary activity
stays in Activity by default; only explicit root opt-in makes this condition an
informational finding. It is not a default noisy threat alert.

## Source evidence and field meaning

The current native code independently parses `euid`, retains exact executable
bytes and success, and converts the recognized unset AUID/session sentinel to
null. Existing [native profile tests](../../tests/unit/m3_native_contract_test.cpp)
and [normalizer](../../collector/src/audit/execution.cpp) cover those semantics.
The closed Python event validator validates these fields again; `uid` must never
be substituted for `euid` and Boolean false is not numeric UID 0.

Upstream [Linux Audit auditctl documentation](https://raw.githubusercontent.com/linux-audit/audit-userspace/master/docs/auditctl.8)
defines euid as effective identity and auid as login identity. The
[Audit rules documentation](https://raw.githubusercontent.com/linux-audit/audit-userspace/master/docs/audit.rules.7)
explains the unset loginuid representation. These primary references were checked
alongside the local implementation and real records; this is not an ECS mapping
or a change to Ubuntu Audit policy. No rule writes kernel Audit rules at runtime.

Read-only inspection of retained real M3 data found:

| Existing input | Observed result for the proposed condition |
|---|---|
| Native workload activation `151d0e53-27ab-4baa-a76a-4cb5ae8bd720`, protected report `/root/hids-m3-native-workload.m6s9o0ye/report.json` | 8 accepted executions: 1 configured root shell (`/usr/bin/dash`, known supported profile), 6 other root executables and 1 non-root execution. The shell is the known authorized script case. |
| First bounded real M4 activation `c850bb51-d518-42b9-81d7-8556c28ffcc0` | 16 other root executable events, zero shell matches. All remain unevaluated in the real M4 store. |

All 24 inspected events have unset login identity. Requiring a known non-root
login identity would therefore be unable on these samples; treating unset as
non-root would be wrong. This is why the proposed first condition uses euid and
makes auid important context rather than a matching requirement. The database
main bytes were SHA-256 checked before/after each owner-identity read and remained
unchanged. Only aggregate results/system executable identity are documented;
no private event payload is copied into Git. These are tiny controlled samples,
not a representative frequency/false-positive benchmark or threat coverage claim.

## Required evidence, unknowns and explanation

| Evidence | Role / behavior |
|---|---|
| Verified source binding, committed acceptance, metadata/profile | Required admission/provenance. Unsupported or unknown profile cannot produce a match. |
| exe_base64, euid, success | Required predicates; exact typed equality only. No command-name/path guessing, symlink lookup or argument matching. |
| auid, uid and parent/process identifiers | Important interpretation/context; preserve existing values and missing/unset meaning. They do not establish a human identity or parent chain. |
| Session identity | Optional context. Null does not become a guessed login. |
| Capabilities, intent, interactivity and arguments | Not established by this event/retention contract; never infer them. |

Malformed/incomplete mandatory M3 fields reject at receipt; the isolated evaluator
reports error if handed invalid data. A valid event with unavailable profile is
unable, not no_match. Explicitly unset optional login identity does not suppress
this credential condition; the finding must disclose that attribution is unavailable.

Fixed explanation: “The configured shell executable was recorded with effective
UID 0 and a successful execution result. Authorized administration and scripts
can match.” The finding links its one event, exact rule revision/hash and matched
exe/euid/success values. The event supplies retained optional context. Impact label
is proposed **informational**, not a final severity taxonomy or an attack-confidence
label. Effective UID 0 alone does not describe capabilities or containment.

Exact byte-path matching covers only the configured executable. Bash, another
shell, a renamed/deleted executable, alternate namespace/path or an unsupported
profile does not become covered merely because the process name looks similar.
Generalizing the executable list or rule meaning requires a new reviewed revision.

## Minimal evaluator and storage extension

Proposed rule definition format 2 adds only `euid` as a strict uint32 equality
field and permits this approved non-demo informational definition. Keep bounded
`all_of`, at most four predicates, closed keys and immutable id/revision/hash.
No new operator, regex, code plugin, SQL or history access is required. Keep the
version-1 fixture validator unchanged; it currently rejects this proposal.

The real version-1 alert table currently requires `demo=1`, so enabling a real
finding needs an explicit schema version 2, with the same application id/five-table
architecture. Proposed changes only:

- Add `rule_plan TEXT NOT NULL DEFAULT '[]'` to `m4h_bindings`. Existing imported
  bindings get an empty plan: the 16 historical events remain unevaluated.
- Rebuild `m4h_alerts` with identical columns/keys/foreign keys, changing the demo
  check to `CHECK(demo IN (0,1))`; keep informational as the only accepted severity
  for this first scope. Copy every existing alert row unchanged before replacing
  the old table. No original event/rule/finding is deleted or reinterpreted.
- Set user_version 2 in the same atomic migration transaction. Preserve the real
  application id. Older code must refuse the upgraded live store.

The concrete SQL change is:

```sql
ALTER TABLE m4h_bindings ADD COLUMN rule_plan TEXT NOT NULL DEFAULT '[]';
CREATE TABLE m4h_alerts_v2(
 alert_id TEXT PRIMARY KEY,event_key TEXT NOT NULL,rule_id TEXT NOT NULL,revision TEXT NOT NULL,
 explanation TEXT NOT NULL,matched_values TEXT NOT NULL,demo INTEGER NOT NULL CHECK(demo IN (0,1)),
 severity TEXT NOT NULL CHECK(severity='informational'),created_at TEXT NOT NULL,
 UNIQUE(event_key,rule_id,revision),FOREIGN KEY(event_key,rule_id,revision) REFERENCES m4h_evaluations);
INSERT INTO m4h_alerts_v2 SELECT * FROM m4h_alerts;
DROP TABLE m4h_alerts;
ALTER TABLE m4h_alerts_v2 RENAME TO m4h_alerts;
PRAGMA user_version=2;
```

Execute this only through an explicit owner-authorized migration, under the
existing destination writer lock and normal admission settings. Require the exact
known version-1 schema/application, integrity/foreign-key checks and an exclusive
mode-0600 SQLite backup in a new 0700 directory before modification. Backup uses
the SQLite API/WAL view, not file copying of a live database. Finalize only the
new backup copy as a standalone DELETE-journal snapshot and verify it read-only;
source journaling remains WAL. This avoids needing missing source-style sidecars
when inspecting the backup. Check row counts and immutable event hashes before/after. Include the backup in admission under the
already approved aggregate M4 state/free-space budgets; do not hide backup growth
outside the store accounting. Unsupported schema/capacity/backup failure
must refuse without schema writes; interrupted migration must reopen as intact
v1 or complete v2, never a partial version.

Rollback before commit is SQLite rollback. After v2 findings exist, stop the new
worker and preserve both live v2 data and v1 backup; do not overwrite v2 with an old
backup or silently downgrade and lose findings. This is not automatic retention,
expiry, permission repair or evidence cleanup.

## Explicit activation/version policy for the first scope

Root must opt into the exact rule id/revision/definition hash for a **new selected
M3 activation** in a bounded trial. Keep the 16-event/120-second approved budget;
root configuration remains fixed-path, owner-checked and closed/versioned.

Freeze the rule plan on first import for that source/activation/generation.
Changing the plan/revision in the same binding refuses; choose a new explicit
activation for changed semantics. Duplicate source delivery only retries that
binding's original plan. Never apply a newly enabled rule to old events merely
because a sweep revisits their offsets. Existing history is not backfilled.

Disabled configuration performs no import/evaluation. Stopping/disabling a bounded
operation retains pending work and all findings; it does not mark pending as clean
or delete old alerts. Resuming an explicitly authorized scope uses its frozen plan.
No hot reload, unattended detection, all-source enablement or UI enable/disable
workflow is approved by this first rule. The collection consent boundary is unchanged.

## Evidence and finite implementation acceptance

Nine rule-semantic test-only proposal cases cover its exact JSON/v1 rejection, a matching root
shell with optional unset auid, euid/uid distinction, another executable/comm spoof,
non-root shell, unsuccessful outcome, unknown/unsupported profile and malformed/
missing/Boolean/null euid. The prototype is confined to a test module, never loaded
by a worker. Six additional test-only cases exercise this exact proposed migration
SQL, preserving 16 synthetic events and an existing schema-valid demo finding,
WAL-aware backup, backup refusal, mid-migration rollback and two actual SIGKILL
boundaries (after old-table removal before commit, and after commit). These are
private design fixtures, not a production migrator or rule implementation.

After approval: implement the versioned validator/evaluator, migration, frozen
plan/root opt-in and non-demo alert persistence; then prove migration backup and
crash boundaries, unchanged old 16 events, disabled/no-backfill behavior,
positive/nonmatch/unable/error cases, immutable revision conflicts and one-alert
idempotency. Finally run bounded Ubuntu acceptance with controlled root shell,
non-root shell and other-executable cases, exact source preservation and policy
restoration. Retain all prior/new history. No arbitrary arguments, PAM/journald
configuration, dependencies, privileges or Mac system change is introduced.

Final [design evidence](../validation/m4-first-rule-proposal.md) records the
root-private aggregate report and passing local/Ubuntu checks. The complete Ubuntu
scope passed 68 M4 tests (53 existing + 15 proposal-only), 87 M3 regressions and
demo. The real store remains v1 with the original 16 unevaluated events and no
rules/evaluations/alerts; no migration or live collection occurred.

## Owner decision requested

Accept this opt-in informational condition, its narrowly scoped version-2 rule
format, history-preserving migration and frozen-plan/no-backfill behavior for
implementation and bounded acceptance. This is the D-08 rule/value and D-07 schema
decision reserved for owner review. It does not enable any current live rule,
authorize default alerts, complete a release or permit commits/pushes.
