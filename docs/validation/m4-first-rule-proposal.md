# First M4 rule and migration proposal: design evidence

Status: review-ready D-08/D-07 proposal; no production rule or migration is enabled.
[Decision packet](../implementation/m4-first-rule-review.md) contains the exact
condition, meaning, default-off policy, JSON version, migration SQL and activation
semantics. This extends the review work after the passing bounded real import;
it does not reinterpret that approval as permission for new alert meanings.

## Real evidence inspected without collection

The root-private aggregate record is
`/root/hids-m4-rule-evidence.rhzg1_ck/report.json`.

Read-only queries under the actual data-owner identity inspected two retained M3
activations. Original database main bytes were hashed before/after each query and
remained unchanged. No raw event payload was copied into the repository.

- Native workload `151d0e53-27ab-4baa-a76a-4cb5ae8bd720`: 8 accepted events, one
  configured `/usr/bin/dash` effective-UID-0/success match and seven nonmatches.
  The match is the known authorized script case; it demonstrates a benign match,
  not an attack. Its metadata names the supported current profile.
- First bounded real import `c850bb51-d518-42b9-81d7-8556c28ffcc0`: 16 accepted
  events, all nonmatches for that configured shell condition.
- All 24 events have unset audit login identity. No human initiator is inferred.

The record independently confirms the retained real destination is still schema
version 1, with 16 events / zero rules / zero evaluations / zero alerts. Its main
bytes also remain unchanged. M3 database count remains 356; original units remain
inactive, Audit active, rules empty and root trial config absent. No new source
activation, Audit configuration change, live rule evaluation or database upgrade
was performed for this review.

## Test-only checks

`tests/unit/test_m4_rule_proposal.py` has nine semantic cases: exact JSON/current-v1
rejection, optional unset auid, euid/uid distinction, executable-versus-comm,
non-root shell, unsuccessful outcome, missing/unsupported profile and invalid/
missing/Boolean/null euid. The fixed evaluator exists only inside that test module.
It is not a version-2 production parser or supported detection implementation.

`tests/unit/test_m4_rule_migration_proposal.py` has six checks on private synthetic
version-1 databases, using the proposed SQL directly from the decision packet:

- Preserve all 16 complete synthetic event rows and an alternate schema-valid demo
  alert/rule/evaluation through the upgrade, with new binding plans empty. The
  real production store has no such demo rows; this checks lossless SQL copying.
- SQLite API backup includes committed WAL data and remains readable as v1.
- Existing backup refuses before schema writes rather than being overwritten.
- Failure after creating the new table rolls back the entire schema.
- Actual child SIGKILL after old-table removal but before commit reopens intact v1.
- Actual child SIGKILL after commit reopens complete v2.

Both crash cases retain all 16 synthetic event rows, application identity,
integrity and foreign keys. Current v1 code refuses the upgraded fixture. These
checks are a proposed-migration prototype, not a production migrator with proven
root authorization/admission/precondition/backup-path controls. Those controls and
all first-real-finding acceptance remain work after owner approval.

An initial local backup-inspection case found that the new WAL-mode backup could
not be reopened read-only without sidecars on the local SQLite version. The design
was corrected to finalize ONLY the new backup copy as a standalone DELETE-journal
snapshot, then verify it. The original/source remains WAL and untouched; no
immutable mode or ordinary copy of a live database is used. All final cases include
this correction. No real backup or schema migration occurred.

## Final verification

The 15 proposal checks pass locally. The complete verified Ubuntu scope passed
68 M4 tests (53 existing M4 checks + 15 proposal-only checks), all 87
M3 Python regressions and the demo, no skips, 2.916 summed phase seconds:

- Source snapshot: `hids-src-20261112T065216Z-8ee22a546fb0`.
- Manifest SHA-256:
  `7e761148acd484ac97ee73e778eccfd623fe754b1a901c4837cb58be6e5807a2`.
- Report:
  `/home/ivy/hids-m4-fixture.etjurv8x/results/run-20261112T030808Z-d0ebde19553b/report.json`.
- Ordinary invoking user, standard library only; source inventory/hash verified
  before/after. No deployed code or original M3 state is modified by this scope.

Earlier semantic-only Ubuntu report (before adding migration design checks):
`/home/ivy/hids-m4-fixture.etjurv8x/results/run-20261112T030131Z-5c80950cbeae/report.json`,
62 M4 + 87 M3 tests and demo passed. It does not contain the later migration checks.

Primary Linux Audit field documentation was checked along with local C++/Python
contract code; links and exact interpretation limits are in the decision packet.
No rule-frequency benchmark, threat/ATT&CK coverage, full migration implementation,
current real-data alert support or unattended-monitoring claim follows from these
counts. No application code was changed or Git progress published in this step.
