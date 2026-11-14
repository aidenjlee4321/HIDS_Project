# M4 real filesystem pressure, full-write and read-only acceptance

Date: 2026-11-12. Result: passed. Scope: synthetic M3/M4 state in a fenced private
mount namespace with a separate 1.5 GiB ext4 image. No production filesystem was
filled or remounted. Existing real history, logging policy and installed code
remain unchanged.

## Implemented experiment and safety boundaries

[Harness](../../tests/integration/m4_filesystem_ubuntu.py) requires the verified
Linux 2 guest UUID, immutable source manifest, original M3 units already inactive,
Audit already active and the serialized workflow lock. Before creating an image,
it requires more than image size plus 2 GiB of free guest filesystem space.
Observed preflight free space was 45,582,262,272 bytes; no dependency was installed.

The image has a fixed logical size of 1,610,612,736 bytes, is root-owned/mode 0600,
and is formatted with zero reserved-user blocks. It is mounted nodev/nosuid/noexec
inside an unshared private mount namespace. Before any mount action the inner
helper refuses its parent's or PID-1's namespace, noncanonical/unexpected
workspace paths, or an incorrect image owner/mode/type/link count/size. It then
verifies the mounted source is the loop device associated with that exact image.
The filler can allocate only on that distinct image device and has byte/time
bounds. Neither the real guest root/data filesystem nor an arbitrary device is
an accepted filler/remount target.

A separate data-owner producer creates three committed synthetic M3 executions
on the guest filesystem outside the image and keeps its WAL/SHM available.
That private source is bind-mounted read-only over the canonical M3 path; the
private image is bound over the canonical M4 parent. Original M3 sockets are
hidden. The M4 child uses actual LiveSource and RuleStore fixed-path constructors,
the exact approved root-owned rule, normal 512-page/M4 storage budgets, and the
real isolation probe. No production guard is weakened or mocked.

Children permanently drop to the data owner with no supplementary groups and
verify zero effective/permitted/inheritable capabilities. Parent-death termination
is armed after dropping credentials. This is a forked private-namespace storage
experiment, not a claim that every systemd restriction was exercised again;
actual systemd worker isolation is covered by the earlier accepted scopes.

## Executed boundaries and saved state

| Boundary | Imported events | Pending evaluations | Findings | Observed result |
|---|---:|---:|---:|---|
| Initial event | 1 | 0 | 1 | Durable baseline |
| Real free space reduced to about 400 MiB | 1 | 0 | 1 | Normal policy reports critical and refuses before a write |
| Import admitted normally, then image filled | 2 | 0 | 2 | 0 available bytes; real SQLITE_FULL (13); complete import/progress rollback |
| Finding write admitted normally, then image filled | 3 | 1 | 2 | 0 available bytes; real SQLITE_FULL (13); evaluation and finding roll back together |
| Space restored and pending work retried | 3 | 0 | 3 | Complete, one finding per event; repeated retry has no duplicates |
| Destination closed and remounted read-only | 3 | 0 | 3 | Writer startup refuses with EROFS (30); main bytes and file inventory unchanged |
| Writable mount restored and store reopened | 3 | 0 | 3 | Integrity/foreign keys pass; counts unchanged |

The pressure case retains default warning/critical/minimum free-space thresholds
(1024/512/256 MiB). In each race case, a test-only wrapper first runs the actual
admission check in normal state, then coordinates the external image fill before
SQLite writes. The storage failure is genuine filesystem exhaustion, not SQLite
max_page_count, a mocked write exception or a production fault-injection switch.
The failed import leaves all three committed source events readable. The failed
finding retains the already imported third event and its pending evaluation for
retry from M4's stored snapshot. Complete logical rows, rule plans and scan state
are compared around each failure; no partial progress/completion is accepted.

The read-only case closes writable handles before remounting, then tests startup
refusal and byte/file preservation. It does not establish arbitrary mid-syscall
remount behavior, continued UI/history service while unavailable, quota variants
or every VFS/SQLite failure mode.

## Reproduction and protected evidence

```sh
sudo python3 -B tests/integration/m4_filesystem_ubuntu.py --expected-manifest MANIFEST --expected-vm-uuid 46330e53-4a53-4a94-b9d4-0adefd192ab7
```

Final source `hids-src-20261112T114001Z-9c472280ee97`, manifest
`9d192f0e8377ffafa8293eb447fb8b27e71cb39e63af13b9c2d50749bdaecb5c`.
Private report `/var/tmp/hids-m4-filesystem.2g42naej/report.json` returned passed,
cleanup verified, production preserved, normal M4 budgets and three final events/
findings. Parent log `/root/hids-m4-fs-job.0rgvsiua/run.log`; adjacent
`namespace-negative.json` records same-namespace refusal before mounting and an
unchanged previous report. The root job has a 150-second bound and the inner
namespace command 120 seconds; individual waits/fill actions are also bounded.

An initial import/full/readonly pass is retained at
`/var/tmp/hids-m4-filesystem.mij9pg86/report.json`. The subsequent added evaluation
boundary passed at `/var/tmp/hids-m4-filesystem.wpw5__vn/report.json`. The final
run adds namespace/image/device fencing and passes both transaction boundaries.
All three images, synthetic histories and reports remain retained; their logical
image sizes are not equivalent to allocated host storage. No cleanup of evidence
or unrelated files was performed.

## Independent cleanup/preservation and limits

The namespace helper released every test bind mount and image mount. The parent
verified its original mount namespace/device view and detached only devices
associated with its exact private image. Independent post-run inspection found no
loop association for any of the three retained images.

Before/after hashes matched all real M3/M4 main databases (including the v1 backup),
M3 config and Audit configuration/plugin/rules inventory. Independent inspection
also verified all 29 installed hashes, 357 real M3 database files, all four original
Audit inodes/byte prefixes, real M4 counts 19 events/two bindings/one rule/three
evaluations/one finding, full M4 integrity and foreign keys, no active M4 unit and
no host `/etc/hids/m4.json`. Original M3 units remained inactive. No native Audit
collection, deployment, migration, commit or push occurred.

This closes selected real-filesystem guard/refusal, import/finding atomicity,
pending retry and read-only startup boundaries for the current M4 implementation.
It does not close M4 WAL/state-limit behavior under sustained growth, additional
quota/VFS variants, representative native workloads, release thresholds,
unattended operation, root-only API/authentication or dashboard/packaging work.
The most recent full component regression remains 93 M4 tests, 87 M3 regressions
and demo; production modules were unchanged here. The new integration harness was
syntax/diff checked and exercised on Ubuntu at its actual filesystem boundaries.
