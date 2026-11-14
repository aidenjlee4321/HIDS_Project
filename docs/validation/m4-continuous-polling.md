# M4 continuous idle/burst and held-reader WAL measurement

Date: 2026-11-12. Result: passed. Scope: one bounded synthetic activation, 16
synthetic IPC events, three ten-second observation windows, and a repeat start.
This is a short measurement, not a production soak or release acceptance.

## What ran

The [installed-IPC harness](../../tests/integration/m4_ipc_contention_ubuntu.py)
now has an explicit `--polling` scope. It retains its exact guest-UUID, immutable
snapshot, inactive-original-units, Audit-active and serialized workflow preflight.
Installed M3 Service/real reader/backend accounts accept the synthetic protocol-3
messages. Its source, M4 destination and selected configuration remain private
fixtures. Production collection/configuration/history are not fault targets.

Unlike the earlier one-step observations, this scope runs the actual
`m4_service.run()` configuration validation, admission, source isolation and
one-second polling loop continuously. Root-owned version-2 config selects the
approved informational rule, exact scope, normal 512-page/storage policy,
max_events=16 and max_seconds=60. The configuration directory is bind-mounted
read-only over `/etc/hids` inside the test worker only; no host `/etc/hids/m4.json`
is created. The source is read-only, destination writable and original sockets
hidden in the existing unprivileged worker sandbox. Added systemd CPU/memory/I/O
accounting measures usage; it does not install a production unit or change budgets.

Sequence:

1. Start with zero events and observe ten seconds of idle polling.
2. Send four synthetic IPC events and wait for their durable M4 import.
3. Pin an external read-only SQLite snapshot at four source events. Send four
   more events, observe ten seconds, then four more and observe ten seconds.
   The held reader still sees its original four; M4's short fresh reads see new work.
4. A PASSIVE checkpoint while held reports 178 log frames and only 74 checkpointed.
   Release the holder, request TRUNCATE on that private fixture through the
   backend's test coordinator, and verify result (0,0,0) and zero WAL bytes.
5. Send the final four events. M4 reaches its 16-event cap, completes all 16
   evaluations/findings with zero pending work and exits. Repeat start retains
   exactly 16 findings and exits at the cap without duplicates. Source/destination
   integrity and destination foreign keys pass; M3 remains ready/connected.

The external long-lived reader is deliberately a test fault. Normal M4 source
transactions remain short; this does not approve long-lived reads in production.
The explicit checkpoint applies only to this newly created synthetic database;
no historical evidence or source file is removed or rewritten by the experiment.

## Measured observations

| Observation | Recorded value |
|---|---:|
| Main bounded service loop elapsed | 32.410 seconds |
| Main loop process CPU delta, excluding import/startup | 0.230655 seconds |
| Main process peak RSS | 27,344 KiB |
| Largest sampled cgroup MemoryPeak | 15,167,488 bytes |
| Initial idle observation interval | 10.009 seconds |
| Cgroup CPU delta during that idle interval | 0.056034 seconds |
| Cgroup IOWriteBytes delta during that idle interval | 0 bytes |
| Logical source/destination file-size growth during initial idle | 0 bytes |
| Accept-ACK samples | 16 |
| Accept-ACK median / maximum | 2.234 / 7.071 ms |
| Largest sampled synthetic source WAL | 733,392 bytes |
| WAL immediately after holder release and TRUNCATE | 0 bytes |

Cgroup memory and process RSS measure different accounting views; they must not
be treated as the same quantity. CPU deltas are CPU time, not elapsed time or a
release CPU percentage. Zero accounted idle I/O growth does not establish absence
of reads/system calls; cache effects and filesystem accounting apply. The bursts
use one tiny repeated synthetic payload and one informational rule. There is no
representative workload, statistically justified latency comparison, throughput
SLA, long-duration growth guarantee or accepted release threshold here.

## Reproduction and retained evidence

```sh
sudo python3 -B tests/integration/m4_ipc_contention_ubuntu.py --polling --expected-manifest MANIFEST --expected-vm-uuid 46330e53-4a53-4a94-b9d4-0adefd192ab7
```

Source snapshot `hids-src-20261112T112250Z-36a3e5d4e637`, manifest
`748b3f24e1709ef4527114eb528d93f6207089f62ba53619613023e2f3f3076a`.
Protected report `/var/tmp/hids-m4-ipc.e9d5arcz/report.json`, parent log
`/root/hids-m4-polling-job.v4gdtede/run.log`. The root job has a 150-second wall
limit; continuous worker has a 70-second unit bound in addition to its 60-second
application bound. All synthetic state/reports remain retained.

The original four-phase contention scope was re-run from this same snapshot after
modifying the shared harness. It passed at
`/var/tmp/hids-m4-ipc.7lvo13wi/report.json`, including overlap barrier, source
snapshot, completed recovery and production preservation. The most recent full
component scope remains 93 M4 tests, 87 M3 regressions and demo; no production
module changed in this step. Syntax, diff and document-link checks passed.

## Preservation and next gates

Both runs returned production-preserved and original-units-inactive. Their
before/after inventory hashes cover real M3/M4 main databases (including backup),
M3 config and Audit config/plugins/rules. Independent post-run inspection checked
all 29 installed hashes, all 357 real M3 database files, all four original Audit
inodes/byte prefixes, and real M4 counts 19 events/two bindings/one rule/three
evaluations/one finding with integrity/foreign keys passing. No M4 units or host
trial config remain. No commits or pushes were made.

This extends finite scheduler, idle/burst, snapshot/checkpoint and duplicate-free
restart evidence. It does not exercise M4 physical ENOSPC/readonly mounts or cross
WAL/state admission limits; broader native/typical workloads, longer observation,
release thresholds and unattended-operation approval remain open. Preserve the
existing real state and v1 backup. The next bounded failure scope should use a
separate fenced filesystem image with normal guards and a tested cleanup path,
never fill or remount the guest's real root/data filesystem.
