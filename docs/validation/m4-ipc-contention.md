# M4 contention beside installed M3 IPC: bounded observations

Date: 2026-11-12. Result: passed. This is a 16-event synthetic IPC experiment,
not native Audit capture, a long soak or release performance acceptance.

## Scope and exact path

[Harness](../../tests/integration/m4_ipc_contention_ubuntu.py) runs installed
`/usr/lib/hids` M3 Runtime/Service under the real hids-ingest account, receives
protocol-3 messages from the real hids-audit identity and uses the existing
root-client control protocol. Native records are not collected: payloads and
source/state directories are private synthetic fixtures. Parent root selects the
new synthetic activation and coordinates the test; no production activation or
root M4 config is created.

M4 runs from a verified root-owned source snapshot in actual transient systemd
sandboxes. It uses the implemented LiveSource/RuleStore/Worker classes and exact
approved non-demo rule, not a mock database. Its synthetic source is bind-mounted
read-only over `/var/lib/hids/m3`, synthetic destination over `/var/lib/hids/m4`,
and original M3 sockets are hidden. Empty capabilities, NNP and worker hardening
remain in place. UID is 994; the observed sole group is its NSS primary GID 971,
with no IPC group. These values are resolved through NSS rather than hardcoded.

Four phases send four events each, staying at 16 total:

1. Baseline imports/evaluates the first four accepted IPC events.
2. A separate owner connection holds BEGIN IMMEDIATE on M4's destination. A
   test-only SQLite trace barrier confirms M4 attempts its write before the next
   M3 batch. M3 ACKs those events durably; M4 reports unavailable and retains four
   imported events/findings without partial progress. No retry/busy timeout is
   shortened in the production connections.
3. A read-only SQLite connection pins the synthetic source's eight-event WAL
   snapshot. M3 ACKs four more events; that old reader still sees eight while M4's
   fresh transaction imports the missing events, reaching 12 findings.
4. After releasing the holders, four more IPC events complete 16 accepted events
   and 16 unique findings. Source health remains ready/connected without failure
   throughout the measured phases; SQLite integrity/foreign keys pass.

The test verifies that the accepted count is visible in committed SQLite reads
before treating each batch as durable. ACK latency covers the accept request,
Service processing/SQLite transaction and socket reply; registration latency,
native parsing and capture lag are not included.

## Final recorded measurements

Each ACK median/max below has only four samples. M4 wall/CPU measurements cover
one Worker.step, excluding process startup. RSS is whole-process peak KiB,
not incremental allocation or a release budget.

| Phase | ACK median / max ms | M4 wall seconds | M4 CPU seconds | M4 peak RSS KiB | M4 events/findings |
|---|---:|---:|---:|---:|---:|
| Baseline | 2.179 / 3.125 | 0.0120 | 0.0040 | 26348 | 4 / 4 |
| Destination locked | 2.020 / 2.766 | 1.0218 | 0.0032 | 27120 | 4 / 4 |
| Source snapshot held | 1.972 / 2.299 | 0.0179 | 0.0035 | 26404 | 12 / 12 |
| Recovered | 1.789 / 3.219 | 0.0112 | 0.0025 | 26292 | 16 / 16 |

Source WAL grew from 90,672 bytes before the first batch to 959,992 bytes after
16 events; the held-reader phase grew 519,152 → 733,392 bytes. This establishes
finite observed growth/visibility under this workload, not eventual checkpoint
reclamation, bounded sustained growth or an accepted CPU/memory/disk threshold.
These tiny samples cannot establish that contention improves latency or has no
host-resource impact; no statistical significance or throughput SLA is claimed.

## Reproduction and protected evidence

Run only on the authorized VM from an immutable snapshot:

```sh
sudo python3 -B tests/integration/m4_ipc_contention_ubuntu.py --expected-manifest MANIFEST --expected-vm-uuid 46330e53-4a53-4a94-b9d4-0adefd192ab7
```

The exact guest UUID is checked before setup; IP address/DHCP mapping alone is
not identity. A wrong-UUID negative run refused before creating any experiment
directory. Normal preflight also requires original M3 units inactive, Audit active,
the serialized workflow lock and verified source manifest. No Mac system changes,
software installation, new account, logging-policy change or data cleanup occurs.

Final snapshot `hids-src-20261112T110915Z-8af8fc4dbf24`, manifest
`ac4180061c45754bf20bfb33fb6acca97ea86fa95f5e1b45ef1872d10a44c46f`.
Private report `/var/tmp/hids-m4-ipc.lxfyoawv/report.json` returned passed.
Supervised parent log `/root/hids-m4-ipc-job.u4n2eoea/run.log`; adjacent
`identity-negative.json` records fail-before-setup evidence. The root job was
bounded by RuntimeMaxSec=150, with finite protocol/page/event counts and waits.
All experiment databases and private reports are retained.

The first attempt `/var/tmp/hids-m4-ipc.jgv7b90y/report.json` stopped at a harness
identity assertion before its first event batch. A no-data probe confirmed systemd
includes the primary group in getgroups(). The corrected assertion permits only
that primary group and still rejects the IPC group or any additional group; no
service privilege changed. Production preservation passed even for that failed run.
An initial four-phase pass at `/var/tmp/hids-m4-ipc.37l1iudh/report.json` was
followed by the explicit write-attempt overlap barrier and another pass at
`/var/tmp/hids-m4-ipc.zlw6opn9/report.json`. The final UUID-guarded run above is the
reported measurement. Intermediate results are not silently relabeled.

## Preservation and remaining work

Harness before/after hashes match all production M3/M4 main SQLite files
(including the migration backup), M3 configuration, Audit config/plugin inventory
and exact Audit rules. Original M3 units remain inactive. Independent inspection
of the overlap run confirmed all 29 installed artifact hashes, 357 real M3
SQLite files, exact guest UUID, no M4 units and no root M4 trial config. Production
code and real data were not used as fault targets or changed by this experiment.

The most recent full component scope remains 93 M4 tests, 87 M3 regressions and
demo; this turn added only this integration harness and documentation, with actual
Ubuntu execution, syntax and diff checks. No product module was changed, so that
scope was not repeated without cause. No commit or push was performed.

Remaining gates include continuous idle/typical/burst measurements, longer source
snapshot/WAL pressure and reclamation, M4 real-filesystem full/readonly failures,
representative native-input workloads and owner-reviewed release thresholds.
This test closes only selected installed-Service/peer IPC correctness and small
contention observations, not unattended monitoring or broad performance acceptance.
