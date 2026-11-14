# M4 v2 recovery and SQLite contention acceptance

Date: 2026-11-12. Scope: synthetic private fixtures and actual sandboxed Ubuntu
workers with synthetic source/destination mounts. No new real Audit executions,
production deployment, new dependencies, history deletion or automatic startup.
The approved one-event informational rule, v2 schema and frozen plans are unchanged.

## Executed evidence

Seven new implementation cases in
[test_m4_rules_v2.py](../../tests/unit/test_m4_rules_v2.py) extend that suite to 25:

- Four actual child SIGKILLs immediately before/after import commit and finding
  commit. Reopen/replay produces one event and one finding, retains the original
  16 rows unchanged/unevaluated and passes integrity/foreign-key checks.
- A separate SQLite connection holds BEGIN IMMEDIATE on the destination. Worker
  reports source_or_destination_unavailable without advancing import progress;
  M3 Runtime accepts another event independently while that lock remains held.
  Releasing the lock and reaching the bounded retry time imports/evaluates both
  events once. Only the synthetic test connection's busy timeout is shortened.
- Actual SQLITE_FULL from SQLite max_page_count equal to current page_count
  rolls back the whole new import/plan/progress. All 16 committed source records
  remain readable. Restoring only the fixture page cap lets the retry complete;
  old history stays unevaluated. This is a SQLite page-cap case, not physical
  ENOSPC, quota or a production budget change.
- A read-only source connection holds an old WAL snapshot. M3 accepts a new
  event; the old reader retains its original view while M4's fresh transaction
  sees both committed events and produces two findings.

Focused local 25-case suite passed. Verified Ubuntu workflow passed 93 M4 tests
(86 prior + seven new), 87 M3 regressions and demo:
`/home/ivy/hids-m4-fixture.etjurv8x/results/run-20261112T105355Z-2b59a75392c5/report.json`.
Its source manifest was
`e724ae13a30d9ff815acdadc9d20ef123da4912f9987e2a3b3ecec04805d6cb6`.

## Actual sandboxed worker recovery

The explicit integration command is:

```sh
sudo python3 -B tests/integration/m4_trial_ubuntu.py   --phase synthetic --rule --recovery --expected-manifest MANIFEST
```

`--recovery` refuses any phase other than synthetic with the approved rule. A
root-owned test wrapper runs the ordinary service/config/namespace path under
hids-ingest, empty capabilities, read-only M3 mount, hidden production sockets
and writable synthetic M4 destination. The wrapper kills itself at real
transaction boundaries; production modules gain no fault-injection interface.

| Boundary | Events after recovery inspection | Pending | Findings |
|---|---:|---:|---:|
| Before import commit | 16 | 0 | 0 |
| After import commit | 17 | 1 | 0 |
| Before finding commit | 17 | 1 | 0 |
| After finding commit | 17 | 0 | 1 |

Each inspection uses the actual owner identity and checks integrity/foreign keys.
Subsequent normal starts finish late A after B, ending with 18 events, two non-demo
informational findings and the original 16 events unevaluated. Repeated starts
produce no duplicates. Root-config mode/generation and old-plan backfill negative
controls remain exercised.

Final source `hids-src-20261112T105501Z-c7ccc5f42552`, manifest
`94ec2c1c2f9126ba8ee066d177ec734f78a862a67e5f017007a4b417c86e4f8f`.
Protected report `/var/tmp/hids-m4-handoff.7a4u4fl6/report.json` returned passed,
restoration verified and all four intended boundaries. The only change after the
full regression run was to the integration wrapper/assertion; production/unit
sources were unchanged and the final source manifest was checked by the harness.

The earlier run `/var/tmp/hids-m4-handoff.co_w53yx/report.json` reached all four
correct saved states but failed an assertion assuming A could only appear on
the second normal restart. Extra recovery sweeps can legitimately find A sooner.
The corrected assertion accepts either discovery round and still requires the
final complete count and repeat idempotency. The failed run truthfully remains
failed; restoration passed and all 357 real M3 databases remained.

## Independent preservation and limits

After final acceptance, independent inspection verified 357 real M3 database
files, all 29 installed hashes, all four original source inodes/byte prefixes,
exact Audit configuration/plugin/rules baseline and exact M3 configuration.
Real M4 remains 19 events/two bindings/one rule/three evaluations/one finding,
with integrity/foreign keys passing. Its main bytes were unchanged by the
read-only inspection. No M4 units or root trial config remain. No commits/pushes.

These cases establish selected ledger/store/worker recovery behavior. They do
not establish actual installed M3 IPC ACK latency under contention, physical
filesystem exhaustion/readonly coverage for M4, sustained WAL growth behavior,
CPU/memory acceptance thresholds, or unattended operation. Those remain separate
bounded measurement and release gates; no synthetic result is substituted for
live installed IPC or a production resource SLA.
