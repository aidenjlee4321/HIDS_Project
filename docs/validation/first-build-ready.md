# First installable build: user-trial checkpoint

November 14, 2026. Owner requested the final loader/display review, end-to-end
acceptance and one prepared release checkpoint, followed by their own trial.
These steps are complete through packaging, Linux 2 preparation and documentation.
The owner subsequently approved committing/pushing this prepared checkpoint to
`aidenjlee4321/HIDS_Project` on `main`. Verify the resulting commit in Git rather
than inferring publication from this evidence record. Start the trial with [these instructions](../USER_TRIAL.md).

## Candidate and delivered files

Version: `0.1.0~dev20261114.15`, Ubuntu 26.04 AArch64/Python 3.14.
Size: 3,059,348 bytes. SHA-256:
`a57bfc91589b295b1b1ad6e606d3b1fe6bb70b5e33f830ab4bbcdbd3b3659a4a`.

- Linux 2 is now normally package-installed at this version, with all sources and
  viewer stopped. No pending process grant remains.
- User folder: `/home/ivy/Desktop/HIDS First Build`. It contains the installer,
  `SHA256SUMS` and `README.md`, all readable by ivy in that private directory.
- VM build artifact:
  `/home/ivy/hids-copilot-build.uwa242qg/development-packages/hids-development_0.1.0~dev20261114.15_arm64.deb`.
- Verified Mac temporary copy:
  `/private/tmp/hids-first-build/hids-development_0.1.0~dev20261114.15_arm64.deb`.
  Only the installer and synthetic instructions/checksum were retrieved/prepared
  there. Native evidence, private keys and credentials remain on Linux 2.

Artifact source: `hids-src-20261114T143957Z-cebd62f5ab93`, 435 source files.
Manifest: `95009c692a969bdc95474f08282f6d3d91518315d668a9e200770b6720e0c862`.
VM source:
`/home/ivy/hids-copilot-build.uwa242qg/verified/hids-src-20261114T143957Z-cebd62f5ab93`.
Installed `BUILD_INPUTS.json` records the exact package version, source/native
hashes and dependency provenance. No runtime product code was changed during this
review; the package refresh includes the current workflow and updated Stop guide.
Operator lab tools, browser diagnostics and handoff documentation were added after
this artifact snapshot; they are not silently claimed as its immutable inputs.

## Step 1: loader and display-boundary review

Inspected both frozen loaders, shared SQLite bounds, service family isolation,
HTTP projections and the React display. Existing limits validate types, canonical
payloads, schema, hashes and provenance; selected values are bounded before Python
materialization. Response/cursor budgets and family independence remain unchanged.
React renders untrusted strings as text, including technical JSON; no HTML injection
or executable field display was added.

Copilot initial job: `hids-copilot-review-c97d207b3e154b7499f50c050582a250`.
Packet: `74d761f0619db47cf1a7d00b263f2a9cff61dbcc78a3eef98f9d5fada519e7e3`.
It flagged a cleanly closed WAL database with absent sidecars. Independent launch
inspection showed that the existing owner-side preparation deliberately opens the
database before the read-only service, keeping the sidecars present through
startup. Weakening this guard or using immutable reads on potentially live stores
would be inappropriate.

Copilot reviewed the complete launcher context and withdrew the finding:
`hids-copilot-review-494d11723ee34aaa9bb34a644298044d`, packet
`78d3e4a495e4f05adc632acca4e29d648e3b72b88b5106f53b5e6ab24461dbee`.
Both jobs used one `gpt-6-luna` request each, no tools or model-applied changes.
Only inspected source was provided, with no runtime records, keys or credentials.

Four added Ubuntu regressions exercise actual launcher `PREP` against closed
process/M4 fixture databases: clean stores load after preparation, main bytes stay
unchanged, and malformed UTF-8 stores still refuse after preparation. Direct loader
calls without the required sidecars remain refused without creating them. These
checks are intentionally Linux-only; the final Ubuntu run had no skips. A local
Mac fixture attempt exposed a context-manager assumption in the test and different
SQLite sidecar behavior; neither was treated as a product failure.

Passed 13-phase report:
`/home/ivy/hids-copilot-build.uwa242qg/release-checks/run-20261114T132735Z-8f70a7b19612/report.json`.
198 Python checks, 24 client checks, all 13 actual synthetic HTTPS session
assertions, TypeScript and three frontend builds passed without skips.
No test count is a claim that all parser, resource or system variants are covered.

## Step 2: final installation and end-to-end checks

Independent copy-on-write Ubuntu acceptance passed `.14`→`.15` upgrade/downgrade
refusal at `/opt/hids-package-acceptance.lfw_j51i/report.json`, and fresh
install/reinstall at `/opt/hids-package-acceptance.cby590hr/report.json`.
Packaged dependencies/HTTPS, session revocation, frozen data, identity/choice/key
preservation, no-grant/legacy-gap refusal, boot metadata without authority and 24
actual configuration SIGKILL/retry cases passed across those two roots. These are
private PID/mount/network namespace roots, not newly provisioned full VM boots.

A fresh native build passed all 17 phases:
`/home/ivy/hids-copilot-build.uwa242qg/release-native-checks/run-20261114T133845Z-20f9ac737b53/report.json`.
This includes native regressions, cross-language checks, 10 receiver, 21 pipeline,
seven process-setup and 52 setup checks (some overlap the dashboard workflow;
counts are not added as if distinct). Its production collector hash exactly
matches the packaged binary:
`e5afaa5b01e38fa9d3768f96996ad5ca5c6fcdffae3073d331677147c7c11639`.
The verified owned-child acceptance binary is
`0bd5dd685eb616b8ce0d49e29e7f9b45563d82f7852d3ab43fdd6134cb50ec26`.
An initial native invocation used isolated import mode incorrectly, and a second
used the system Python without FastAPI; the existing complete test environment
resolved those tooling errors without installing dependencies.

### Explicit Linux 2 operator transition

The earlier Linux 2 application directories had manual trial installations, which
normal package preflight correctly refuses. The pinned lab-only
`development_trial_prepare_ubuntu.py` archived the stopped manual application
directories/local units at `/opt/hids-prepackage.4rl2pqv2`, and retained a private
archive of config/keys/process history. It then ran the normal package preflight
and `dpkg --install`; no marker forgery or product conflict bypass was used.
All original data, six source-choice revisions and source configuration remained
byte-identical through installation. No source or viewer was started by install.
Transition receipt: `/opt/hids-prepackage.4rl2pqv2/transition.json`.
This is an explicit, reversible lab transition, not general migration support or
permission for the product to silently adopt unmanaged installations. Do not
restore the archive over a running or package-managed installation.

Operator snapshot: `hids-src-20261114T145104Z-e6c453cd11bb`, manifest
`bb35b10a1e55b58e36ad77ba5e33727c07349032c707c6975ba2a74e4e9cc6be`.

### Actual installed source and protected dashboard

`development_live_ubuntu.py` confirmed a fresh root-authorized process selection,
started the real packaged coordinator/backend/systemd restrictions, and used only
the verified acceptance collector override to retain one owned child's native
fork/exec/exit. The production collector binary was never replaced. Three new
records were added to the existing private store; the original three were retained.
The interval completed cleanly before root scoped Stop confirmed it. The override
was removed. A subsequent no-grant runtime start refused before collection.
Active invocation-bound signaling has separate actual systemd synthetic-coordinator
acceptance in [the source-control record](source-control-safety.md); the owned-child
fixture naturally completes, so this run is not a new active-stop race test.

Installed HTTPS then displayed six process records and the unchanged 19 Audit
history records/one informational finding, including 16 unevaluated records.
Viewer restart rejected the old session; explicit reopen created a new frozen
view; root revocation invalidated the current session.
Native and HTTP receipt: `/opt/hids-release-live.3i3stmnj/report.json`. Its native
and HTTP assertions passed, but its overall result is failed because the selected
test Python lacked Playwright. It is not represented as a completely passed run.

The existing browser environment was selected and the remaining viewer tests ran
without collecting another interval. One attempt returned a generic browser error
after record/detail/finding checks; no cause was established. Private diagnostics
were added, then two consecutive full repeats passed:

- `/opt/hids-release-live.jl7kfzmk/report.json`
- `/opt/hids-release-live.425sxuyd/report.json`

These verify direct-leaf trust, no sandbox/TLS bypass, an ordinary sandboxed browser,
unauthenticated denial, actual counts, lossless process fields, historical interval
labels, finding→event linkage, logout clearing late responses, grant replay refusal
and transient-profile cleanup. The initial generic failure remains a recorded
possible test flake, not silently reclassified as a passed attempt. Temporary
exact-browser policy was removed and original policy state restored after each run.
Screenshots/private browser evidence were restricted to root after completion.
No global trust or CA was added. The headed user-desktop experience remains part
of the owner's trial; automated acceptance used headless Chromium.

Final browser/operator snapshot: `hids-src-20261114T150155Z-bff4492bd482`, manifest
`0b1e62633089c1db63f2720706241887c83d883bde16020262d03ea0399754b4`.
The viewer-only mode is explicit and does not claim to rerun native collection.

## Independent final proof and Step 3 handoff

Final proof: `/opt/hids-first-build-final.x_6wiaag/report.json`. All 21 assertions
passed. Actual terminal-only `hids-sources status`, confirmed `hids-sources stop`
and `hids-dashboard stop` ran in a PTY. `dpkg --verify hids-development` found no
installed payload changes. All 649 regular payload files passed root ownership,
privilege-bit, private-key, VM identity/path and runtime-state exclusion checks;
exact source/version provenance matched. An initial archive-check helper could
not deserialize a WAL-format database into memory; a private immutable archived
copy completed the comparison without altering current or archived evidence.

The original 396-file M3/M4/installed baseline, Audit rules/config and original
source prefixes still match. The current cold process store has six records/two
clean-stopped intervals `[0,1,0,1]`, quick_check `ok`, unchanged bytes across the
owner-identity immutable check, and all three original event hashes matching the
prepackage archive. Old choice revisions 1–6 and process source configuration are
byte-identical. New choices ended empty at revision 8. Seven source/viewer units
are inactive; no pending grant or acceptance collector override remains.

The installer, checksum, [trial instructions](../USER_TRIAL.md), installed operator
guide and this evidence record form the ready checkpoint. Source commit/push is
approved by the owner for GitHub `aidenjlee4321/HIDS_Project`, branch
`main`. Remote main was read-only verified as
`d921a2bb4e74f245a60723011b36d9f614cde2ef`; no Git state has been changed here.
The pending source includes the already accumulated approved implementation and
maintenance work; this is not represented as a tiny isolated change over main.

This is a first installable development build. It does not complete full v0.1,
prove fresh full-VM boot behavior, supported process threat detection, enrichment,
broad rules, release performance thresholds or unattended monitoring. Reassess
additional features after the owner's trial. No Mac system changes, security-data
deletion, CA or Git mutation occurred during the implementation/acceptance run described
above. The later separately approved commit/push is recorded by Git history.
