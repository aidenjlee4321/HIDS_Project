# Dashboard interruption and cleanup safety — November 14, 2026

This records `.10`. The later `.12` atomic publication fix and updated installed
guide/provenance are recorded in [the publication follow-up](dashboard-publication-safety.md).

Continued owner-authorized review of the first installable development build.
No new source, rule, route, schema, collection or trust scope is added.

## Findings and changes

Restricted source-only Copilot review:
`hids-copilot-review-8e096446fde24de3bd3ce6ddc8bc2104`, normalized packet SHA-256
`c2427342c0501277afd455d3d411248b6d6423249656d14d41a4b34de85b948a`.
Auto-selected `gpt-6-luna` used one request, no tools or model-applied changes.
Only the launcher and ordinary-browser helper source were supplied. Independent
inspection confirmed three defects:

- Preparation caught `Exception`, so KeyboardInterrupt could skip viewer stop
  after units were started. It now catches interruption as well. Interrupted
  preparation-child reaping also stops the viewer; open's outer cleanup scope
  includes preparation and browser launch.
- Root cleanup sent SIGTERM to a Python browser helper whose default signal
  behavior skipped its `finally`. The helper now handles termination through
  cleanup. Chromium runs in a new owned process session; bounded termination,
  escalation and reaping target that launch's worker/group only. The transient
  HOME/NSS/profile is removed and signal handling restored. Unrelated browser
  processes and collection sources are not targeted.
- A timed-out AppArmor load could have already applied its profile while the
  old success flag remained false. Removal is now attempted after any load
  attempt, followed by a kernel-state absence check. If absence cannot be proved,
  cleanup refuses and retains its policy file for inspection rather than silently
  removing the evidence. Normal and interrupted VM acceptance left no profile.

These changes cover ordinary interruption/failure paths. SIGKILL of the root
launcher, a host crash and every possible repeated-signal/storage failure are not
claimed to run Python cleanup. No global kernel setting or browser sandbox bypass
was introduced.

## Component and actual VM evidence

Snapshot: `hids-src-20261114T112045Z-c09a4a3e60ab`, 422 source files.
Manifest: `fe5f9520c930053424c836e2f3879d52fd803fae37fbb42a3db5dddfef99f0bb`.
VM source:
`/home/ivy/hids-copilot-build.uwa242qg/verified/hids-src-20261114T112045Z-c09a4a3e60ab`.
Eleven-phase workflow:
`/home/ivy/hids-copilot-build.uwa242qg/dashboard-cleanup-checks/run-20261114T103402Z-6d018097f77f/report.json`.
173 Python tests, 24 client tests, TypeScript and three frontend builds passed,
without skips. Five added checks exercise interruption after start, interruption
while reaping preparation, cleanup after a timed-out policy load, retention on
unconfirmed policy removal, and real escalation/reaping of a stubborn owned child.

Explicit VM report: `/opt/hids-dashboard-cleanup.h48sziyf/report.json`.
`tests/integration/dashboard_cleanup_ubuntu.py` verified:

- Three isolated synthetic sleep services actually started under systemd. An
  injected KeyboardInterrupt after confirmed start caused the launcher's real
  stop function to stop its owned units. This is an exception-path test, not a
  physical terminal keystroke or real security-data viewer activation.
- The actual pinned ordinary-user Chromium and actual browser helper completed
  normal headless close and real SIGTERM interruption. The worker imported this
  verified source for the test; the VM's manual installation was not overwritten.
  A synthetic bootstrap and temporary test leaf were used, with no live viewer,
  valid production grant or security-data request. This tests process/trust
  lifecycle, not a new retained-data UI acceptance run.
- The owned browser process group was gone, adopted test descendants reaped,
  transient profiles removed and the exact prior AppArmor profile set restored.
  No production dashboard config was published. Original HIDS state and stopped
  source/viewer units were preserved. Only the test's own units/policy were removed.

The load-timeout failure is simulated in the component test; normal/terminated
real Chromium runs separately verify actual kernel policy removal. No claim of
an actual hung kernel-policy loader is implied.

## Final package

Version: `0.1.0~dev20261114.10`, Ubuntu 26.04 AArch64/Python 3.14 only.
Size: 3,057,464 bytes. SHA-256:
`292ed6168a132f5e4bbe487563db1c3a3f4e73c95b4438bd75c1768f4cf2aa04`.
VM artifact:
`/home/ivy/hids-copilot-build.uwa242qg/development-packages/hids-development_0.1.0~dev20261114.10_arm64.deb`.
Verified local installer:
`/private/tmp/hids-first-build/hids-development_0.1.0~dev20261114.10_arm64.deb`.
Native source/binary and dependencies were unchanged, reused after source/recipe/
hash verification. Previous artifacts remain unchanged.

Independent private PID/mount/network copy-on-write Ubuntu acceptance passed:

- `.9`→`.10` upgrade and downgrade refusal:
  `/opt/hids-package-acceptance.wrd17ne4/report.json`.
- Fresh `.10` install/reinstall:
  `/opt/hids-package-acceptance.iftvjqf3/report.json`.

Both passed packaged HTTPS/frozen fixtures, session revocation on restart,
preservation of history/IDs/keys/choices, no-grant/legacy-gap refusal and the six
installed configuration SIGKILL/retry regressions. They are installation-root
tests, not fresh full-VM boots. The running VM's manual HIDS install was not adopted
or replaced.

Independent final proof:
`/opt/hids-dashboard-cleanup-final.d1wxe31b/report.json`.
The 396-file baseline, installed hashes, Audit policy and source prefixes matched.
Seven source/viewer units remained inactive with no pending process grant. The
separate process DB retained its three events, clean-stopped/no-ACK interval,
quick_check `ok` and unchanged bytes after the metadata-only owner read. Inspection
passed all 649 regular package payloads: root ownership and no special privilege
bits, VM UUID/build-home path, private-key markers, runtime state or reviewer
installation. Only the installer was retrieved; reports and credentials remain
private on the VM. No source activation, historical reevaluation, Mac system
change, commit or push occurred. Post-build handoff documents are separate from
the immutable package source snapshot.
