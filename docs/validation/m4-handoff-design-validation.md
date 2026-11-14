# M4 handoff ordering design evidence

Historical ordering-design checkpoint. The owner later accepted this direction;
[implementation and actual backend sandbox acceptance](m4-handoff-implementation-validation.md)
now supersede its pending-review/not-implemented status for synthetic input only.
The design-harness limitations and local failed report below remain preserved.

Status: synthetic design verification, not an implemented production handoff.
The [proposed contract](../implementation/m4-handoff-contract.md) is ready for
owner review. Existing fixture-pilot approval is preserved; no new scheduling,
live-data, migration or security-rule decision is treated as already accepted.

## What was exercised

Seven added tests in `tests/unit/test_m4_handoff_design.py` use the actual M3
Progress writer, isolated synthetic databases and a separate `mode=ro` SQLite
connection. The candidate sweep state is intentionally test-only and in-memory.
No live source database, runtime activation, installed service or rule is changed.

1. Demonstrate that maximum first_offset misses earlier A when B commits first.
2. Import B before A resolves, then find late A behind the page cursor on a later
   sweep; only the frontier captured at sweep START can become settled.
3. Paginate multiple B events while A is unresolved without starving later pages.
4. Destination failure leaves candidate progress unchanged and rereads the page.
5. Uncommitted/rolled-back execution rows remain invisible to the separate reader.
6. Recovery imports accepted B, not interrupted A, preserving format/profile/arch
   and observation/receipt/persistence-start metadata from the same row snapshot.
7. The source read-only connection cannot update M3.

These tests establish the ordering counterexample and selected candidate scan
behavior. They do not implement/prove a durable destination checkpoint, source
identity authorization, installed read-only sandbox, live scheduler, failure
isolation, resource thresholds or production schema. Those remain explicit
acceptance gates in the proposal. The existing 23 pilot tests retain their separate
scope, including actual process crashes in the private fixture destination.

## Results and retained evidence

The local run's M4 phase passed all 30 tests (23 pilot + 7 design), no skips:

`/private/tmp/hids-m4-workflow/run-20261112T052219Z-dcdf8530b0f7/report.json`

The subsequent local M3 regression phase ran 87 tests but failed with 33 setup
errors when M3's real storage admission guard refused the low-space Mac volume.
The observed available space was 405,651,456 bytes, below the existing 512 MiB
critical threshold. The report remains `failed`; it is not a full local pass.
No guard, production policy, Mac setting or unrelated file was changed or deleted
to bypass that result. The complete scope instead ran on the authorized Ubuntu VM.

Final Ubuntu run passed all three phases with no skips: 30 M4 tests, all 87 M3
Python regressions and the synthetic demo, 1.570 summed phase seconds. It ran as
ordinary user `ivy`, with no sudo/deployment/source-policy change:

- Snapshot: `hids-src-20261112T052539Z-53a5a5a24d8a`.
- Manifest SHA-256:
  `bdd5bbced388b8166c667000601fd4ecaff6a0a929bd1cfd9d8467f3d221a49b`.
- Source: `/home/ivy/hids-m4-fixture.etjurv8x/hids-src-20261112T052539Z-53a5a5a24d8a`.
- Report:
  `/home/ivy/hids-m4-fixture.etjurv8x/results/run-20261112T013421Z-8494c71003df/report.json`.
- Source inventory/hashes were verified before/after the run. Private logs and
  synthetic stores remain outside Git. Later documentation additions record this
  immutable snapshot's results; they do not claim the proposal is implemented.

Run the named scope with `python3 -B scripts/m4_workflow.py`; use an appropriate
canonical private output directory and `--expected-manifest` for a verified snapshot.
The current scope includes actual filesystem admission in its M3 unit regression
phase; insufficient host free space can fail that phase. Prefer the existing VM
for complete regression while the Mac remains below that guard.
