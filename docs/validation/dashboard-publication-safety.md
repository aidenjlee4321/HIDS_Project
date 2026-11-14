# Dashboard configuration publication — November 14, 2026

This records `.12`. The later `.13` root-private TLS staging hardening and package
acceptance are in [the TLS follow-up](tls-staging-safety.md).

Owner requested continued work with ongoing Copilot review. Scope remains fixes
to the first installable development build, with no new source/rule/HTTP authority.

## Review and correction

The old publisher moved the active dashboard config into history before publishing
its replacement. Rename failure or interruption between operations could leave the
active frozen selection and certificate binding missing. Independent inspection
and restricted Copilot review confirmed the window:
`hids-copilot-review-f1bfbd945ea74bfd8d5843a59e4f59fa`, normalized packet
`b8c630637a5a9f2a3b78d096a056b05dc73c0181005df49040a470aae7df39be`.

Publication now checks the root-controlled destination, syncs a complete pending
file, preserves a byte-exact root-private backup and atomically replaces the active
pathname. History and active directories are synced at their relevant boundaries.
It retains a complete old or new selection/TLS binding through process interruption;
no collection or automatic restart is added. Prior data/backups are not deleted.

Copilot then reviewed the applied correction and reported no further concrete
defect in the two publication functions:
`hids-copilot-review-18a144e3026745379e8d64fb14948a21`, packet
`891c018bbfd8e97462b6a4d5e542632b32f41fd916e95d2d11d82a84ce211c6c`.
Each review used one auto-selected `gpt-6-luna` request, with zero tools or file
changes. Only inspected development source was supplied. The follow-up is a scoped
review result, not proof of complete program correctness; executable checks below
independently verify the behavior.

## Final source and checks

Snapshot: `hids-src-20261114T114740Z-c4521447b7ec`, 424 source files.
Manifest: `713184d6bc9a3d93cd836e2bc538b1e9e00059886f4c37259744d4f4168d34e0`.
VM source:
`/home/ivy/hids-copilot-build.uwa242qg/verified/hids-src-20261114T114740Z-c4521447b7ec`.
Eleven-phase report:
`/home/ivy/hids-copilot-build.uwa242qg/dashboard-publication-checks/run-20261114T110257Z-dda4db149f79/report.json`.
177 Python tests, 24 client tests, TypeScript and three frontend builds passed
without skips. Four added publication tests cover failed replacement, interruption
after replacement, symlink refusal and initial creation. Mac temporary-directory
aliases were resolved in the tests to preserve the production canonical-path guard.

The packaged guide previously named the prior artifact as "latest" and linked to
unshipped validation documents. It is now version-independent, points explicitly
to records in the source checkout and explains installed version/provenance lookup.
`BUILD_INPUTS.json` includes `package_version`; actual payload inspection confirmed
it matches dpkg metadata. This avoids embedding a moving latest-version pointer.

## Actual installed acceptance

Private copy-on-write Ubuntu roots with PID/mount/network isolation passed:

- `.10`→`.12` upgrade/downgrade refusal:
  `/opt/hids-package-acceptance.1o1ddmg2/report.json`.
- Fresh `.12` install/reinstall:
  `/opt/hids-package-acceptance.pi6fyuo3/report.json`.

The actual installed dashboard publisher received SIGKILL at six boundaries in
each root: pending-file sync, backup-directory sync, before/after replacement and
before/after active-directory sync. Every case retained complete old/new metadata,
the exact prior bytes after backup/retry, unchanged TLS generation/fingerprint and
a valid retry to the intended selection. Active files remained root-owned 0440,
backend-group readable and single-link. The real main dashboard config stayed
unchanged while separate fixtures exercised the kills.

Each root also passed the six existing source-config crash/retry cases: 24 actual
process kills across the two final roots, 12 specifically for dashboard publication.
Packaged HTTPS/frozen fixtures, restart revocation, unavailable-family auth,
history/IDs/keys/choices, no-grant and legacy-gap refusal, and boot-without-authority
checks passed. These are process-kill tests, not physical power-cut or newly
provisioned full-VM boot tests. Native code/dependencies were unchanged and reused
after source/recipe/hash checks. Earlier `.11` acceptance passed but that candidate
retains the stale guide; it remains private as superseded evidence.

## Delivered artifact and preservation

Version `0.1.0~dev20261114.12`, Ubuntu 26.04 AArch64/Python 3.14 only.
Size: 3,057,800 bytes. SHA-256:
`b363e1260fb87a73e4f5d0b68ace173ac4dc3f35fab12aa86ec92925e7e73194`.
VM artifact:
`/home/ivy/hids-copilot-build.uwa242qg/development-packages/hids-development_0.1.0~dev20261114.12_arm64.deb`.
Verified local copy:
`/private/tmp/hids-first-build/hids-development_0.1.0~dev20261114.12_arm64.deb`.

Independent proof: `/opt/hids-dashboard-publication-final.hmzyue1j/report.json`.
The 396-file original baseline, installed hashes, Audit policy and source prefixes
matched. Seven source/viewer units remained inactive with no pending process grant.
Process history stayed three events with its clean-stopped/no-ACK interval,
quick_check `ok` and unchanged cold DB bytes. All 649 regular payloads passed
root ownership, privilege-bit, private-key, VM identity/path and runtime-state
exclusion checks; package version and installed guide checks passed. The manual VM
installation was not replaced, no source activated, no history re-evaluated and no
Mac system setting/software/credential, commit or push changed. Only the installer
was retrieved; native reports and credentials remain private on the VM.
