# Installer configuration upgrade safety — November 14, 2026

This records the `.9` checkpoint. The later `.10` dashboard cleanup fixes and
package acceptance are in [the cleanup follow-up](dashboard-cleanup-safety.md).

The owner directed continued work on the first installable build. This checkpoint
fixes installer behavior; no source, rule, schema, trust or collection-authority
changes are introduced.

## Verified defect and correction

The old collector-hash update moved `/etc/hids/process.json` into history before
renaming its replacement into place. Interruption between those operations left
the active path absent. A retry could create a fresh source UUID and default
limits, violating preservation requirements.

Independent inspection identified this path. A restricted Copilot review confirmed
it in job `hids-copilot-review-8325a4ca2388431f95b122da1fd1c035`, normalized packet
SHA-256 `37a3324a01d8e6c19849ab694224143c0afd72874fad383a73376d45a7d21409`.
It used auto-selected `gpt-6-luna`, one request, no tools and no model-applied
changes. Only installer source and its operator guide were sent. Copilot suggested
a hard link as one option; an independent byte-exact backup instead preserves
existing single-link requirements.

`update_process_config()` writes/syncs a root-private backup and its directory,
then writes/syncs the replacement and atomically replaces the active pathname.
The active file remains complete, with its containing directory synced afterward.
Source ID and limits remain unchanged. Pending files/backups are retained rather
than automatically deleted. A missing active config with history, a broken history
symlink or pending metadata is refused before generating a new identity. Ambiguous
older interruptions require deliberate administrator recovery, not guessed IDs.

## Final source and component checks

Snapshot: `hids-src-20261114T101130Z-8eee6c4d3b43`, 419 source files.
Manifest: `025a392804e4daf6f20422ae7719ecc604dc55e8a7a3784acd4a932b106c7356`.
VM source:
`/home/ivy/hids-copilot-build.uwa242qg/verified/hids-src-20261114T101130Z-8eee6c4d3b43`.
Eleven-phase report:
`/home/ivy/hids-copilot-build.uwa242qg/upgrade-safety-checks/run-20261114T091849Z-8e2430a5a567/report.json`.

168 Python checks, 24 client checks, TypeScript and three frontend builds passed,
without skips. Seven installer checks cover the earlier preflight refusals,
before/after-publication failure/retry using real temporary files, fresh
initialization and refusal of retained ambiguous metadata. Native code/binary and
runtime dependencies were unchanged, reused after source/recipe/hash checks.

## Actual installed crash and package acceptance

Private copy-on-write Ubuntu roots had separate PID/mount/network namespaces.
The actual packaged helper was killed with SIGKILL at six boundaries: after backup
directory sync, after pending-file sync, before/after replacement and before/after
active-directory sync. Every case retained a complete old/new config, byte-exact
backup, source ID and limits. Retry produced a root-owned 0440 single-link active
file. Six cases passed in each of two final roots: 12 actual process kills.

Upgrade report: `/opt/hids-package-acceptance.b73f_v_w/report.json`.
An actual `.7`→`.9` upgrade passed. Synthetic stale recorded hash metadata forced
the installed postinst update branch without changing the executable. Identity,
limits, data, keys and choices survived; stale metadata remained in history and
the current binary hash was restored. Downgrade refusal, packaged HTTPS/frozen
display and restart/session revocation also passed.

Fresh-install/reinstall report:
`/opt/hids-package-acceptance.wsp6vcfh/report.json`.
Fresh `.9` install/reinstall, role identities, missing-family authorization,
no-grant refusal and boot metadata without collection authority passed. Both final
roots also reproduced an older missing-active-config interruption: actual
`configure()` refused, retained the saved config and created no new identity.
Test metadata was restored only within the isolated root.

The earlier `.8` candidate passed initial crash/upgrade/fresh-install checks but
lacks the subsequent legacy-interruption guard. It remains on the VM as superseded
evidence; `.9` is the delivered build. These are process-kill and orderly failure
checks, not physical power-cut testing or proof for every filesystem. A newly
provisioned full-VM boot also remains untested.

## Artifact and preservation

Latest version: `0.1.0~dev20261114.9`, Ubuntu 26.04 AArch64/Python 3.14 only.
Size: 3,056,866 bytes. SHA-256:
`1c41c852528f08e1046f324d11502e1566027d0032d1b1fed903afeaa9fd2dbf`.
VM artifact:
`/home/ivy/hids-copilot-build.uwa242qg/development-packages/hids-development_0.1.0~dev20261114.9_arm64.deb`.
Verified local installer:
`/private/tmp/hids-first-build/hids-development_0.1.0~dev20261114.9_arm64.deb`.
Earlier artifacts remain unchanged.

Independent proof: `/opt/hids-upgrade-final._245eoks/report.json`.
The original 396-file baseline, installed hashes, Audit policy and source prefixes
matched. Seven process/viewer units remained inactive, with no pending start grant.
The process DB passed quick_check with its original three events and unchanged
clean-stopped/no-ACK interval; its hash stayed unchanged after the owner-only cold
metadata read. Inspection passed 649 regular payload files: root ownership and no
special privilege bits, VM UUID/build-home path, private-key markers, runtime state
or external reviewer installation.

No source was enabled or history re-evaluated. No logging/trust policy, Mac
software/settings/credentials, commit or push changed. Only the installer was
retrieved; native reports and credentials remain private on the VM. Post-snapshot
documentation is a later handoff update, separate from immutable package inputs.
