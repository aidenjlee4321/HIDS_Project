# Copilot integration and development-build follow-up — November 14, 2026

This records `.7`. The latest `.9` installer and configuration interruption/retry
acceptance are in [the upgrade-safety follow-up](installer-upgrade-crash-safety.md).

The owner directed continued work and Copilot integration while student benefits
were pending. Scope remained review/fixes of the first installable development
checkpoint; no new source, detector, collection or product-value decision.
[Reviewer setup and actual review evidence](../implementation/copilot-collaboration.md).

## Independently verified installer finding

Copilot flagged account creation before `configure()`'s preflight. The package's
preinst already checks fresh installs, but `dpkg --configure` retries postinst
without rerunning preinst. On that path, unsupported Ubuntu, a conflicting unit
override or an unsafe existing role could be refused after account creation.
This is an unwanted privileged side effect of refusal, not evidence of remote
code execution or an observed damaged VM.

`configure()` now runs preflight before creating accounts and retains the later
preflight to validate resulting roles. Three targeted regressions exercise real
preflight failure conditions with account creation intercepted: Ubuntu 24.04,
a conflicting unit and a privileged existing role. The named combined-dashboard
workflow now includes `installer_regression`; the builder requires its evidence.
No schema, collection policy, source fields or authorization meaning changed.

## Verified snapshot and checks

Snapshot: `hids-src-20261114T095345Z-cf0efa8d93f1`, 418 source files,
manifest `38ddbbecc124c947c431fa0ea5f7f30b4922f89c0f307940b05abc1d419087df`.
VM source root:
`/home/ivy/hids-copilot-build.uwa242qg/verified/hids-src-20261114T095345Z-cf0efa8d93f1`.
Eleven-phase workflow report:
`/home/ivy/hids-copilot-build.uwa242qg/checks/run-20261114T090240Z-68cafea959ab/report.json`.
164 Python tests, 24 client tests, TypeScript and all three frontend builds passed,
without skips. Twelve additional reviewer/packet tests passed locally and on
Ubuntu. Native source and recipe were byte-compared against the existing passed
native checkpoint; the native binary was not changed or rebuilt.

Two rejected intermediate attempts are retained: the first transferred archive
contained Mac AppleDouble sidecars and failed exact manifest verification; a clean
Python-created archive resolved it without weakening inventory checks. The first
workflow used the browser-only venv and failed on missing FastAPI; the existing
complete test venv resolved it without installing dependencies. Test and VM clocks
differ; IDs/timestamps are recorded verbatim, not asserted as elapsed chronology.

## New artifact and actual package acceptance

Version: `0.1.0~dev20261114.7`, Ubuntu 26.04 AArch64/Python 3.14 only.
Size: 3,055,334 bytes. SHA-256:
`812df34d290a510c8c435672aa7cc609d0b33b56b128d0c413d563002c51edd9`.
VM artifact:
`/home/ivy/hids-copilot-build.uwa242qg/development-packages/hids-development_0.1.0~dev20261114.7_arm64.deb`.
Local installer copy:
`/private/tmp/hids-first-build/hids-development_0.1.0~dev20261114.7_arm64.deb`.
The previous `.6` artifact remains unchanged and retained.

Independent private PID/mount/network copy-on-write Ubuntu acceptance passed:

- `.6` fresh installation, actual upgrade to `.7`, restart/session revocation,
  preserved history/IDs/keys/choices and downgrade refusal:
  `/opt/hids-package-acceptance.zp4o6fwe/report.json`.
- `.7` fresh installation and reinstall, packaged HTTPS/frozen fixture display,
  missing-family authorization, no-grant refusal, new per-install identity and
  no automatic collection/grant after boot metadata recreation:
  `/opt/hids-package-acceptance.nq9e1hn8/report.json`.

Both reports returned passed and host-state-preserved. No package was installed
over Linux 2's manual HIDS runtime. This is not a newly provisioned full VM boot.
The retained-data ordinary-browser path is unchanged and retains its prior scoped
acceptance; it was not unnecessarily repeated for the configure-order change.

Independent payload inspection checked all 649 regular files: root ownership,
no special privilege bits, VM UUID, private-key markers, VM build-home paths,
runtime HIDS state or Copilot/Gemini install. Final host preservation matched the
396-file baseline including old HIDS stores, installed artifacts, Audit policy
and source prefixes. Separate final checks confirmed all seven process/viewer
units inactive, no pending process grant, process DB quick_check `ok`, three
original events and the same ACK=false/delivery=true/incomplete=false/stopped=true
interval. The cold DB's hash was unchanged after the metadata-only owner read.
No commits/pushes, Mac software,
Mac settings or Mac credentials changed. The owner separately approved the private
unencrypted Copilot credential file inside Linux 2. Native evidence and credentials
were not retrieved to the Mac or included in the model packet.

This remains the first development build with process Activity and protected
frozen display, not a complete v0.1 security release. Reassess before extras.
