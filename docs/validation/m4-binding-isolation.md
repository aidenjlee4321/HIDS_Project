# M4 synthetic binding isolation, backoff and pagination acceptance

Date: 2026-11-12. Result: passed. Scope: two explicitly selected synthetic bindings
in an actual unprivileged systemd sandbox. The production bounded entry remains
single-binding; this test does not expand live collection or root configuration.

## Executed boundary

[Harness](../../tests/integration/m4_binding_isolation_ubuntu.py) verifies the exact
Linux 2 guest UUID, source snapshot, inactive original M3 units, active Audit and
serialized workflow lock. Root creates protected fresh source/destination fixtures
and copies verified code into a root-owned readable code tree. Source is bound
read-only over the canonical M3 path, destination over M4's parent, and original
M3 sockets hidden. Existing capability/NNP/filesystem hardening stays enabled.

One source has two new registered intervals, A and B, selected explicitly by the
test. Producer retains A's connection/sidecars. A's ledger mode is temporarily 000,
which fails the required private-file policy; its rows and schema are untouched.
B remains healthy. Restoring A's original 0600 mode verifies identical main bytes
and original metadata before retry. No actual source or historical record is
rewritten or deleted to create this failure, and the product gains no repair path.

The actual Worker uses one-event pages. Its existing injected clock is controlled
at 0 then 3 seconds to test retry ordering deterministically; this is not a wall-
time/backoff performance measurement. The normal scheduler timing was separately
measured in the continuous polling scope.

| Step | Binding A | Binding B | Total events/findings |
|---|---|---|---:|
| First scan | source_invalid, no manufactured event | First event imported | 1 / 1 |
| B receives two more events, clock still before retry | Not re-read; prior blocked status retained | One-event page imports next event | 2 / 2 |
| A restored, clock advanced past retry | Its event imported | Remaining backlog page imported | 4 / 4 |
| Repeated paginated sweeps | Eventually idle | Eventually idle | 4 / 4, no duplicates |

Both intervals include the same native identity `1.001:1`. Their separate scoped
event identities remain distinct. The final store has four completed evaluations
and four informational findings, no pending work; integrity/foreign keys pass.
A failing binding does not prevent healthy binding progress or permanently disable
itself after access is restored. Root selection and source consent remain explicit.

## Reproduction and retained evidence

```sh
sudo python3 -B tests/integration/m4_binding_isolation_ubuntu.py --expected-manifest MANIFEST --expected-vm-uuid 46330e53-4a53-4a94-b9d4-0adefd192ab7
```

Source `hids-src-20261112T121345Z-f1853d582c98`, manifest
`733d85e39b2da387f56d89c7b07b255ca93e8afe60ba462a78a0382165e85239`.
Private report `/var/tmp/hids-m4-bindings.7_jvymhk/report.json` returned passed,
production preserved and original units inactive. Parent log
`/root/hids-m4-bindings-job.dxye88_1/run.log`. The worker has a 60-second unit
limit and the supervised parent 100 seconds, with bounded coordination waits.
All fixture state and reports remain retained.

Earlier `/var/tmp/hids-m4-bindings.p09qzx80/report.json` correctly isolated failure,
advanced B and recovered A, but a harness assertion incorrectly required B to say
imported when it had no further work and correctly said idle. That run remains
failed with production-preserved true. The final assertion accepts honest idle
and adds a two-event backlog with one-event pages plus complete repeat sweeps.
No production module changed for this scope.

## Independent preservation and limits

Independent checks verified four synthetic events/evaluations/findings and full
integrity/foreign keys. The real store remains 19 events/three evaluations/one
finding with integrity/foreign keys passing. All 357 real M3 database files,
29 installed hashes, exact guest identity, no M4 units and no host trial config
were checked. Harness before/after hashes also matched real databases/backup,
M3 config and Audit config/plugin/rules inventory.

This establishes selected per-binding isolation/backoff/recovery and bounded-page
semantics under the actual sandbox. It does not enable multiple production
bindings, unattended operation, arbitrary source repair, a representative load or
release resource thresholds. The latest complete component regression remains
96 M4 tests, 87 M3 regressions and demo; this turn changed only a new integration
harness and documentation. Syntax/embedded-script/diff checks passed. No commits
or pushes occurred.
