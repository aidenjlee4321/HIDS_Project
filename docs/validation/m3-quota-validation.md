# M3 real per-user hard-quota acceptance

## Scope and safety

The explicit `--tier component --experiment quota` workflow tests the installed
Python Runtime/progress/storage code under a real Linux UID hard-block quota on
a new private 64 MiB ext4 loop image. It changes no production module, global
account, host quota, source policy, installed service privilege or release budget.
It does not install software. Normal component/checkpoint scopes do not run it.

A small C++20 root-only lab helper uses the existing target sys/quota.h/Linux ABI.
Before any quota operation it requires a canonical root-owned 0600 single-link
64 MiB image in a private root 0700 lab directory, a matching private /run mount,
a loop block device matching the mount's device, and LOOP_GET_STATUS64 backing
inode/device identity matching that exact image. The UID is obtained from NSS
`hids-ingest`; root/unknown IDs and excessive limits are refused. The helper is
freshly compiled inside the protected run directory, executable only by root,
and is never installed into the product.

The mount namespace is private, with nodev/nosuid/noexec. The real writer drops
to the service UID/GID and opens its own probe descriptor after dropping privilege.
Root adjusts only that UID's block limit on this image, checks the kernel-reported
limit/usage, restores the original unlimited limit and removes its mount/loop.
Images and reports remain protected for inspection. No original history is deleted.

Five real negative helper cases refuse a non-loop device, non-private mount,
non-private image, excessive limit and a different backing inode. After each,
the actual quota is checked unchanged. The different-inode check uses a temporary
zero-filled invalid-image fixture, not original or collected security evidence.

## Actual quota result

The first complete run passed `hids-m3-lab-9aa8c6292ae4`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-9aa8c6292ae4/run-20261111T234814Z-075e7de170ea/report.json`,
protected `/root/hids-m3-quota.srbu11ps/report.json`, 22.156 guest seconds.
It predates the helper-negative-case assertions.

The next run including all five refusals passed `hids-m3-lab-6087ece5789a`:

- Workflow report:
  `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-6087ece5789a/run-20261111T235334Z-bc9849d6c3e0/report.json`.
- Protected image/report: `/root/hids-m3-quota.3dbv722z/report.json`.
- Source snapshot:
  `2fb55144142cabe2c59f8435525030788e2dec443ef16e46604794e135386b91`.
- Elapsed 22.569 guest seconds. Main native artifacts were a verified cache hit;
  one separate quota helper compile ran afresh. Eight phases passed, including
  87 M3 Python + 40 workflow tests, 26 sanitizer native groups, 128 linked native
  contract cases, 124 allocation cuts, 11 API faults and 58 actual SIGKILL boundaries.

The test commits normalized fixture B and registers EOE-backed A with acceptance
still pending. The actual storage admission check passes at 56,934,400 available
filesystem bytes and normal sampled storage. A lab hook then asks the independent
root parent to apply the hard quota **after** that check. The kernel reports UID
994 (NSS-resolved here), 229,376 bytes already charged and a 1-block hard limit,
with each quota block 1,024 bytes. Lowering this private-image limit removes no
existing data; it prevents new allocations.

The unprivileged probe receives real EDQUOT (122). A's SQLite write receives
`SQLITE_IOERR_WRITE` (778), not a fabricated SQLite trigger or an assumed FULL
code. The final test accepts only the observed write error or SQLite's FULL code;
unrelated I/O errors cannot satisfy the case. No transaction remains open, B is
the only accepted execution, A is still open and scanned/frontier remain 20/10.
Available filesystem bytes remain 56,934,400 and the capacity guard still samples
normal: global statvfs space is not a per-user quota guarantee.

Root restores this image's prior unlimited hard limit (0), retaining the same
charged bytes. Explicit Runtime restart passes integrity_check, keeps B accepted,
marks A interrupted, suppresses A's new late EOE and leaves source readiness false.
No automatic reauthorization, source deletion or evidence cleanup occurs.

## Helper and target evidence

The successful negative-case run retains its helper alongside the report:
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-6087ece5789a/run-20261111T235334Z-bc9849d6c3e0/quota-helper`.
SHA-256: `ed5409008202dc96cce690bca704dbdc31a2369364e00b010cc2f4c970474078`.
Existing target ABI headers, inspected before implementation:

- `/usr/include/linux/quota.h`:
  `ce5484b654f33927e42fcd1eaa59cdb0f33237032a845a2c85770b52b3dd212d`.
- `/usr/include/aarch64-linux-gnu/sys/quota.h`:
  `2699d27ae971449850a945f114257de6b4d46f765f479c3c5e717519782a770d`.

Compiler/dependency identity is in the normal workflow build evidence. The helper
has a fresh compile phase; it is not part of the cached product artifact set.
This is not a finalized distribution, bit-for-bit packaging or license approval.

## Limits

This verifies selected real ext4 UID quota denial, atomic storage-core behavior
and explicit recovery while global free space remains available. It does not add
quota discovery or quota-aware proactive admission to HIDS, configure production
quotas, prove every quota filesystem/project/inode/grace-time variation, or prove the installed native collector/systemd sandbox under this specific
quota fault. The later Service IPC extension below covers private normalized
peer transport, separately from native parsing and installed live-source tests. The storage exception remains
an exception; no successful durable acceptance is invented while writes fail.

Production code is unchanged from `f6c0259`; the prior 17-phase full live checkpoint
belongs to that published product code. This named quota test does not silently
claim all broader VFS/device, release threshold, workload, packaging or distribution
gates complete. Hard per-user quota evidence is now narrower and more concrete
than the previous generic open quota gate; other quota variants remain open.

## Final exact-error and restoration verification

The final strict write-error assertion passed `hids-m3-lab-11e7f46da4f4`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-11e7f46da4f4/run-20261112T000019Z-d1d18dadaa58/report.json`,
protected `/root/hids-m3-quota.snih37r0/report.json`, 21.824 guest seconds.
Source snapshot:
`214c51b1e66b010c87c368289ea8432cf7817617b03b7613d0568fad2c2ba27b`.
All eight phases, five helper safety refusals, actual EDQUOT/IOERR_WRITE (778),
rollback, integrity and suppression passed. Main native cache hit, one fresh
quota-helper build. Mac focused checks passed 87 M3 + 40 workflow tests.

Independent final inspection matched original Audit configuration/plugins/rules
against the protected earlier manifest, reverified all four original source
inode/byte prefixes, and matched all 29 installed artifacts. All 355 original
SQLite files remain; original root 0640 configuration/512 lab budget and ingest
0700 state/files 0600 match baseline. Audit is active and all M3/checker units are
inactive. The three quota images/reports remain root-protected; all associated
loop devices and temporary mounts are gone, and the private UID hard limit was
restored to its original unlimited value. No global quota or source policy,
production file, Mac setting/software/credential or original history changed.
The owner approved committing/pushing this checkpoint to `aidenjlee4321/HIDS_Project` on `main`; verify Git for publication status.

## Service IPC extension and final closeout run

The later extension `tests/integration/m3_quota_service_ubuntu.py` is invoked by
this same named quota scope after the direct-storage case. It uses the installed
Runtime/Service modules, an actual unprivileged `hids-ingest` backend and
`hids-audit` peer, protected real Unix sockets, root-owned control listener
inherited by the backend, and the normal root client ownership/peer/framing checks.
The synthetic normalized input is not a native collector execution test.

B is accepted and acknowledged; EOE-backed A is registered but not yet accepted.
After checkpointing committed pages, root applies the private image's UID quota.
A's acceptance request receives EOF rather than any success acknowledgement.
Root status reports `storage_failure`, a possible gap and disconnected/not-ready
collection despite normal sampled free space (56,774,656 bytes). Activation and
leases are denied. B remains the only accepted event. Releasing quota alone leaves
the failure latched and activation denied. Explicit backend restart passes
integrity_check, preserves B, marks A interrupted and denies an old lease without
new authorization. Coordination hooks exist only in the test child; no production
control operation was added. Root probe descriptors are closed before forking.

The initial complete Service run passed `hids-m3-lab-aea84c878a77`, private
`/root/hids-m3-quota.jcrrc_rp/report.json`. The final run after descriptor cleanup:

- Job: `hids-m3-lab-5571cb8a78dc`.
- Workflow report:
  `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-5571cb8a78dc/run-20261112T010147Z-52bd1c95b1c9/report.json`.
- Protected quota/Service report: `/root/hids-m3-quota.6g0gzlcs/report.json`.
- Source snapshot SHA-256:
  `fb193a787391ec2ce7dbe60016a88328c1d46e0e054d4137f541d974cc1cbd9d`.
- All eight phases passed, 24.045 summed guest phase seconds; verified native cache
  hit plus one fresh quota-helper compile. 87 M3 + 40 workflow tests, sanitizer
  reconstruction, linked native contract, parser/allocation/API faults and 58
  actual SIGKILL boundaries reran. Both direct-storage and Service quota cases passed.
- Independent post-run inspection matched the original policy/plugins/rules,
  all four original source inode/byte prefixes, 29 installed hashes, original
  configuration/512 budget and protected state permissions. All 355 original
  databases remain. Audit is active; all four M3/checker units are inactive.
  Quota test directories/images/reports remain root-private, no associated loop
  devices or temporary quota mounts/endpoints remain. No original evidence was removed.

These test/documentation changes remain uncommitted pending specific publication
approval. The earlier `d921a2b` direct-storage checkpoint is published. See the
[finite closeout](../implementation/m3-closeout.md) for bounded M4 entry versus
preserved release requirements. No production module changed for this extension;
the 17-phase full live checkpoint on `f6c0259` remains applicable to that code.
