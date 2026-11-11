# M3 development and isolated-VM workflow

This is development automation for the already provisioned Linux 2 test VM, not
product packaging or an installer. Start with [current state](current-state.md).
The existing [development workflow](development-workflow.md) retains its M1/M2
snapshot/offline scope. This runner reuses its verified snapshots/private reports
and adds explicit M3 lab deployment/acceptance. Python standard library, existing
SSH, compiler and VM dependencies suffice; nothing is downloaded or installed on
the Mac. No Git command, SSH configuration/key setup or automatic reboot is included.

## Test tiers

| Tier | Local/offline work | Installed Ubuntu work |
|---|---|---|
| focused | M3 Python and workflow regression tests | None |
| component | Above, native ASan/UBSan reconstruction/profile/parser-failure suites and actual SIGKILL matrix | Matched build/deployment, producer transport, event metadata/rejections and storage acceptance |
| checkpoint | All component work | Runtime/capacity, 4096-event load, resource ceilings, installed parser faults, actual health isolation and lifecycle |

`--live-audit` explicitly enables the previously authorized lab-only live Audit
rule/plugin test and periodic dispatcher-report test within checkpoint scope.
Without it, checkpoint does not claim live-policy acceptance. Neither option runs
actual reboot, quiet-source/rotation experiments, five-minute/multi-hour workloads,
M1/M2 acceptance, distribution approval or release benchmarks. Those are separate
named gates; automation must not silently label them complete. `plan` shows scope
without running tests, creating snapshots or deploying.

```sh
python3 -B scripts/m3_workflow.py plan --tier checkpoint
python3 -B scripts/m3_workflow.py local --tier focused --output /private/tmp/hids-m3-local
python3 -B scripts/m3_workflow.py local --tier component --output /private/tmp/hids-m3-local
```

On macOS use real `/private/tmp/...` paths, not the `/tmp` symlink spelling, for
explicit output paths. Existing private-state checks reject symlink ancestors;
this protection is not weakened for convenience. Local component checks are
unlinked structural/parser tests; Ubuntu uses actual pinned headers/runtime.

## One-command VM run

From the Mac repository, pass an existing pinned known-hosts file and the existing
guest header directory. Use the actual current VM address. These are runtime
parameters, not credentials or permanent machine configuration:

```sh
python3 -B scripts/m3_workflow.py vm \
  --host ivy@192.168.64.7 \
  --known-hosts /absolute/path/to/existing/known_hosts \
  --state-dir /private/tmp/hids-m3-host-workflow \
  --headers /home/ivy/hids-m3-runtime.6MmspJ2L/headers \
  --tier checkpoint --live-audit --lab-activation-budget 256
```

SSH/sudo may prompt interactively using the existing authorized credentials. They
are never persisted in source, host reports, test logs or command options. This
command creates a verified local snapshot, transfers an archive through SSH without
a pseudo-terminal, then uses a terminal only for the guest sudo invocation. It
retains host/guest evidence and returns the actual guest exit status. It requires
no shared mount, credential helper, guest agent or Mac settings change.

The guest validates the exact transferred snapshot against its expected digest
before running any phase. A separate root lock serializes shared VM state. Preflight
requires Ubuntu 26.04 AArch64, existing accounts/services/Audit headers/library,
Audit active, M3/checker units inactive, at least 2 GiB available and sufficient
remaining activation budget. Component/checkpoint reserve 6/30 intervals. Missing
prerequisites fail with a report; no packages, permissions or host source policy
are automatically repaired. Dependency evidence includes compiler identity/bytes,
header/library hashes, Python/SQLite versions, platform and flags.

An explicit lab activation budget can temporarily increase the HIDS budget; the
original configuration is restored afterward. All event/activation history remains.
If tests produce more intervals than the restored lower budget, further collection
will correctly refuse activation until an administrator deliberately raises it.
For repeated lab runs, set an adequate persistent **VM-only** budget first and
record that setting. This is never evidence-deletion permission.

## Build, deployment and cleanup

The native cache key covers native source/header/test inputs, build recipe/artifact inventory,
compiler/dependency identity and flags. It fingerprints compiler-reported
transitive source/system headers and the VM package inventory as well as the
explicit Audit headers/library. Unique snapshot directory names are normalized
out of input identities. Every cached executable must retain its
recorded digest and executable mode. Missing/changed outputs force a fresh build;
invalid/partial outputs are retained privately. Only binaries are cached, never
passing tests. Documentation/Python changes do not independently force native
relinking; build-recipe/dependency changes do. Unrelated CLI/reporting edits do not. Native sanitizer runners currently
build their own fresh private artifacts for every applicable acceptance run.

The matched deployment covers Python engine modules, collector, health checker,
launcher, M3 unit files and tmpfiles configuration. Root-owned previous files and
metadata are backed up privately before replacements. Units must be stopped;
application files are replaced atomically one at a time, hashes checked, then
systemd/tmpfiles reloaded. A failed deployment stays failed with collection stopped.
This is not an atomic whole-installation upgrade or a database rollback tool.
Never restore a database or older binary blindly across schema changes.

Builds and model/transport tests run as the invoking ordinary VM user, with
empty supplementary groups; root is reserved for deployment and installed
acceptance. Private unprivileged scratch artifacts remain outside the source.
Test-induced systemd failed/start-limit counters are cleared between owned lab
phases. The health harness clears its counter before intentionally rapid manual
samples; installed production rate limits are unchanged. A nonzero phase still
fails the run and is never silently retried or relabeled as a pass.

Fault/probe executables are temporary and restored/removed in `finally`. Harnesses
retain their established restoration rules. The outer runner stops M3/checker
units, restores the HIDS configuration, compares Audit configuration/plugin/rule
baseline, checks Audit active, state permissions, installed hashes and source
snapshot integrity. A restoration mismatch is `needs_attention`, never a pass;
protected baselines/backups remain available. It does not overwrite an unknown
changed Audit policy just to make the check green. SIGKILL/power-loss of the runner
cannot execute `finally`; inspect the protected baseline and VM before retrying.

## Reports and test selection

Each phase records exit status, elapsed seconds, detected skips/test counts and
stdout/stderr hashes. Full logs/report are private, outside source/shared snapshots.
Only short phase summaries and bounded failure tails reach the chat. Nonzero exits,
timeouts, detected unittest skips or an empty required Python/workflow suite fail
the run. Timed-out test process groups are killed before cleanup to prevent late
writes. No failed/skipped phase is reused as a cached pass.

```sh
python3 -B scripts/m3_workflow.py summary /path/to/private/run/report.json
```

The generated summary includes source identity, scope, result, wall/phase seconds,
cached-artifact compile-command count, retained log bytes, phase-summary
console bytes, cleanup and failure. Sanitizer compiler invocations are not part
of the cached-artifact command count. Compare uncached
and cached runs under the same scope, remembering that time, filesystem load and
retained history vary. Log volume is not a token count; exact model/token savings
need actual usage telemetry and must not be guessed.

During editing, run the focused suite plus the tests exercising the changed boundary.
Protocol, privilege, deployment, dependency or native changes warrant component
checks; final checkpoints use the applicable checkpoint scope. Broaden/repeat tests
when changes or failures justify it. Different suites sharing installed state must
remain serial. Do not skip a required gate merely to save time/tokens.

## Efficiency implementation roadmap

1. Compact current-state/authority handoff.
2. Complete verified snapshot, including timer, launcher and the explicitly sanitized fixture.
3. VM preflight, transfer, matched build/deploy and cleanup orchestration.
4. Test tiers, dependency-aware binary cache and private machine-readable reports.
5. Current documentation index/backlog reconciliation with historical evidence intact.
6. Local regression, actual VM safe-failure/retry and uncached/cached pilot measurements.

The first five describe implemented tooling; executed acceptance is recorded in
[workflow validation](validation/m3-workflow-validation.md). No efficiency gain,
release gate or complete native coverage is inferred from implementation alone.

## Supervised performance and soak experiments

Use `--detach` for long VM runs. It dispatches a uniquely named transient VM
systemd job, not an enabled boot service or a Mac configuration change. The job
retains ordinary-user build/test execution, its private output directory and the
existing VM lock; terminal/SSH closure cannot terminate acceptance. Per-job reports
are separate from the explicitly shared native cache root, so new jobs can reuse
verified artifacts without mixing their test results. Its resource
runtime limit includes the requested workload plus setup/cleanup allowance. Dispatch
returns `dispatched`, never `passed`. Check the final job report and cleanup result.

```sh
# Append to the same vm host/known-hosts/state/header options shown above:
# Controlled feature-bundle comparison against an existing local commit:
# --tier component --experiment performance --baseline-ref cde78d9 --detach
# Storage-only comparison with the optimized working tree:
# --tier component --experiment performance --baseline-ref ff90498 --history-files 200 --detach
# Two-hour installed varied fixture workload:
# --tier component --experiment soak --events 4096 --duration-seconds 7200 --detach

python3 -B scripts/m3_workflow.py vm-status \
  --host ivy@192.168.64.7 --known-hosts /absolute/path/to/existing/known_hosts \
  --job hids-m3-lab-012345abcdef --compact --watch-seconds 9000
```

Replace the example job name with the actual dispatched identifier. The watcher
reads only the job's unit/report/private progress metadata over one authenticated
connection. `running` or a successful status-query exit code is not test acceptance.
A missing final report from an inactive job is `incomplete`; inspect its private
baseline/logs before retrying. A failed run remains failed even if cleanup succeeded.
Do not overlap installed-state jobs or start another deployment over the soak.

Performance exports an existing Git commit read-only into private temporary state,
creates a second verified snapshot and builds both native variants with the same
recorded environment. No Git checkout, branch, commit or push occurs. The benchmark
copies code into root-owned VM test directories, uses separate fresh private state
on the installed database filesystem, and never lets old code open current HIDS
history. Six alternating trials and a separate profiled trial preserve full private
measurements. `--history-files` models metadata-accounting cost using equal synthetic
files in both variants; it is not a real-host archival workload.

The native cache now keys on the build recipe and artifact inventory, native inputs,
flags and dependency fingerprints. Changing an unrelated CLI/reporting function no
longer forces native relinking. Cached artifact hashes and ownership are still
checked, tests are never cached, and partial/invalid builds remain retained evidence.

Soak adds varied burst sizes and quiet periods, bounded writer delays, CPU/RSS and
storage observations, and private atomic minute-level progress. Final exact identity,
position, frontier and observation checks remain mandatory. Its JSON report is
retained beside the protected temporary-config backup; console output is bounded.
The two-hour profile uses larger temporary lab budgets and restores the exact prior
configuration afterward. It does not establish release sizing or continuous native
coverage. See [performance/long-workload evidence](validation/m3-performance-validation.md).

The restrictive job umask exposed two negative-permission tests whose fixtures had
implicitly depended on umask 022. Those tests now explicitly set the deliberately
unsafe modes in their synthetic temporary directories. The actual privacy checks
and job umask 0077 remain unchanged.
