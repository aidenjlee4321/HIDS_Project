# M3 real filesystem capacity and read-only acceptance

The later [read-only root-status implementation](m3-readonly-status-validation.md)
supersedes this checkpoint's cold-start status limitation. The observations below
remain the exact historical test results for `bfb4592`.

## Scope and isolation

The explicit VM workflow `--tier component --experiment filesystem` exercises the
installed Python Runtime/progress/storage implementation as `hids-ingest` on a
64 MiB ext4 image. No production modules, source policy, release thresholds or
service architecture change. This is storage-core acceptance, not an installed
collector-to-service failure run or a hard per-user/project-quota implementation.

The image/report stay in a root-owned 0700 lab directory; the image is 0600.
Mounting/remounting occurs only in a new private mount namespace, with
nodev/nosuid/noexec. The writer has the actual unprivileged identity and state
0700/files 0600. A root parent fills only its own filler file, checking a distinct
filesystem device and a 64 MiB allocation bound before allocation. It truncates
only that filler to release capacity, never a database, original log or history.
Parent mount namespace identity is checked, mounts are removed, and any remaining
loop device is detached only by association with this exact new image. Root-only
images/reports remain for inspection. The VM's main filesystem is never filled or
remounted. Existing HIDS state and logging policy remain separate.

Lab-only free-space floors (warning 4 MiB, critical 2 MiB, minimum 1 MiB) permit
meaningful pressure within the bounded image. They do not replace production
values or approve release thresholds. Maximum WAL/state budgets remain explicit.
No raw security events are used: B is a synthetic normalized execution, A is a
separately registered EOE-backed group whose acceptance is still uncommitted.

## Completed real failure/recovery sequence

Final passed job `hids-m3-lab-04ba50f04114`:

- Workflow report:
  `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-04ba50f04114/run-20261111T205331Z-b422f8136ca3/report.json`.
- Protected filesystem report/image directory: `/root/hids-m3-filesystem.rst9vn8j/`.
- Verified source snapshot:
  `e59f2c432b791e54b95b236d6f891ea9a06a90b08dd9b5a952f585949f1915c0`.
- Elapsed 20.625 guest seconds. Native cache hit, zero cached-artifact build
  commands; native sanitizer/parser/crash tests still reran. Cache key unchanged:
  `6ad7a4499604db6efcbfe7014dcde0e1829556220e24ab16801b4e5057bf27d4`.

| Stage | Actual observation and required outcome |
|---|---|
| Baseline | 56,856,576 available bytes; normal admission; B accepted; A pending; scanned/frontier 20/10. |
| Reserve pressure | Own filler leaves 1,572,864 bytes; actual statvfs reports critical/filesystem_reserve; A's transaction is blocked before writes; B and 20/10 remain. |
| External-writer race | After releasing the filler, normal admission sees 56,950,784 available bytes. A lab hook then asks the independent root parent to fill the image **after the real admission check**. |
| Actual full filesystem | Zero available bytes; SQLite returns real `SQLITE_FULL` (13). No transaction remains, B is the only accepted execution, A remains open and frontier is still 10. Exhaustion is not a synthetic SQLite trigger or invented successful write. |
| Restart recovery | Only the filler is released. Explicit Runtime restart durably interrupts A, advances frontier to 20, preserves B and passes integrity_check. A's new late EOE is suppressed; no resurrection or automatic source readiness. |
| Read-only mount | After closing all writers, the parent remounts only the private image read-only. New Runtime startup fails closed with `EROFS` (30); immutable read inspection of this quiescent read-only image confirms B and interrupted A. |
| Writable recovery | Private image returns writable; explicit Runtime restart passes integrity_check and remains not source-ready. No automatic reauthorization. |

The immutable inspection is confined to a closed, quiescent, kernel-read-only
private test image; it is not a production shortcut for ignoring WAL/recovery.
Cold startup on a read-only filesystem fails before establishing control status.
This does **not** establish historical root-status availability under every VFS
failure; restoring writability/restarting is still required in that case.

All seven workflow phases passed: 82 M3 Python tests, 40 workflow tests,
26 sanitizer reconstruction groups, 128 linked native contract cases, 124 allocation
cuts, 11 API faults, 58 actual SIGKILL boundaries and the real filesystem experiment.
Three new isolated safety tests verify refusal to fill the host filesystem or
exceed the image allocation bound before any allocation, and fail on peer exit.
Mac focused tests also passed 82 + 40. Native builds/privileged work stayed on the VM;
no Mac settings, packages, credentials or disk cleanup changed.

## Retained intermediate results

The original capacity/SQLITE_FULL/recovery sequence passed before adding the
read-only case: `hids-m3-lab-fa209a838d19`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-fa209a838d19/run-20261111T204835Z-3d7d741d8646/report.json`,
protected `/root/hids-m3-filesystem.b7sjyq06/report.json`, 20.114 guest seconds.
It does not establish read-only acceptance or the later safety-test count.

The first read-only attempt failed because the harness still held its own filler
open for writing, preventing remount: `hids-m3-lab-f338da293c65`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-f338da293c65/run-20261111T205154Z-7beb4e8ef4a2/report.json`.
This is a failed intermediate result, not a product pass. The harness now closes
that descriptor before remount, and explicitly closes its immutable connection.
The protected intermediate image remains `/root/hids-m3-filesystem.1avxfbso/filesystem.ext4`.
Cleanup restored policy/state; final inspection found no mountpoints or loop
devices associated with any of the three test images.

## Remaining scope

This proves selected real storage-core capacity, rollback and recovery behavior
under controlled ext4 conditions. It does not prove root control availability on a
read-only mount, installed transport behavior under every VFS failure, hard project/
user quotas, device power loss, arbitrary I/O corruption, all filesystems or
release resource acceptance. Existing full live checkpoint evidence belongs to
the previous product checkpoint; it is not silently relabeled as this experiment.
Production code is unchanged. Broader native/workload, release threshold and
packaging/distribution/license gates remain open.

Final independent verification matched original Audit configuration/plugins/rules
to `/root/hids-m3-reboot.xbahp1tb/manifest.json`, reverified all four earlier native
source inode/byte prefixes, and matched all 29 installed application artifacts.
All 305 original SQLite files remain, state is ingest 0700/files 0600, original
root 0640 configuration and 512 lab budget match baseline, Audit is active and
all M3/checker units are inactive. All three retained lab images are root 0600
inside root 0700 directories; no associated loop devices or temporary mountpoints
remain. No product files, original security evidence or host mount settings were
changed by the experiment. The owner approved committing/pushing this checkpoint to `aidenjlee4321/HIDS_Project` on `main`; verify Git for publication status.
