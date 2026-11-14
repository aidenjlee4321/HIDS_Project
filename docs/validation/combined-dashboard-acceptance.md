# Combined frozen dashboard acceptance

P-01–P-04 reached the first local installable **development** checkpoint. The
chronological sections distinguish the retained-data trial from later launch and
package acceptance. Full v0.1/release criteria remain open.

## Synthetic workflow

Named scope: `scripts/combined_dashboard_workflow.py`. Snapshot
`hids-src-20261113T225702Z-dc7488c7cb44`, 393 files, manifest SHA-256
`942e9f9381d916cbcf6fead74e9663c8d69c8b06aba39ad45755d921f1db12e5`.
Private Linux 2 report:
`/home/ivy/hids-browser-compare.9z_gnv_e/combined-dashboard-checks/run-20261113T224436Z-d5250e5cce4c/report.json`.
All ten phases passed: 146 Python tests (process projection 7, combined HTTP 8,
history 44, session/pilot 42, setup 45), client regressions, TypeScript and the
combined/history/setup frontend builds. No skipped tests were accepted.

Coverage includes exact process provenance and canonical digest validation,
explicit missing activity wall time, receipt/observation separation, lossless
64-bit values, read-only WAL loading, closed SQLite schema/length bounds, explicit
latest-128 truncation, session/view/family cursor binding, per-route dashboard
scope, legacy scope denial, independent unavailable families, request boundaries,
expiry/logout and stale responses. Existing scopes retain their previous meanings.

The first archive attempt contained Mac metadata sidecars and was rejected before
tests by the exact manifest check. Portable Python-created archives avoid these
extra entries; rejected evidence was retained. A workflow output-directory bug
was fixed before the final ten-phase run.

## Installed retained-data trial

Final harness snapshot `hids-src-20261113T230008Z-caa92cd0cf8c`, manifest
`84e130816c67dd8003425358a9186ec016ccf8ff636da5e011614efc6f4dacbd`.
Only harness permission/startup checks changed from the tested runtime snapshot;
the reused frontend's source inputs were independently byte-compared equal.
Private root report: `/opt/hids-combined-trial.l9hsxmqa/report.json`.

All checks passed. Three retained real process events matched every approved
stored envelope/receipt/arrival field. The same 19 M4 events, one informational
finding and 16 unevaluated old events remained. No source was opened, subscribed
or evaluated by this trial. The API ran as hids-ingest with all five capability
sets zero. Both databases closed before HTTP serving; the view survived closing
the separate read-only WAL-preparation process. Its namespace hid M3 state and
unrelated configuration and mapped the selected stores read-only.

Ordinary isolated Chromium verified direct-leaf HTTPS with one peer trust entry,
no CA, no certificate bypass and its actual namespace/seccomp sandbox. It showed
all expected event/finding counts, process timestamp precision and historical
interval flags, and the original finding-to-event link. Fragment/cookie/storage
checks passed. A delayed completed process response could not restore data after
logout; replaying the consumed grant stayed locked. Only this launch's new browser
HOME/NSS/user-data profile was removed after browser exit. Screenshots and all
native details remain private on the VM. The temporary exact-browser userns policy
was removed; no global trust/profile or Mac system setting changed.

Initial installed attempts safely refused due to umask-restricted newly created
TLS/config modes, then a wrong test-tool path. Explicit modes and early startup
checks corrected the harness. A separate root-only leaf regression passed strict
umask, reuse, wrong-pin refusal, unsafe-key refusal and unchanged existing material.
The failed trial reports remain retained. No permission boundary was weakened.

After cleanup the original Audit/M3/M4 preservation baseline matched, process/M4
main and existing WAL bytes matched, all process collectors remained stopped,
root config and temporary unit files were removed. New application trial code and
root-managed leaf material remain inactive for subsequent packaging work.

## Boundary at the retained-data checkpoint

At that checkpoint the explicit-root lifecycle, development artifact and independent
installation acceptance were still outstanding. The later evidence below closes
those bounded development tasks. This view remains frozen, with no new process
security rule, unrestricted search/export or live-health guarantee.


## Explicit launch and external-browser reproduction

`/opt/hids-launch-acceptance.tfq4tbq7/report.json` passed root selection,
private-pipe ordinary-browser startup, valid-leaf reuse, prior-bootstrap revocation,
new-profile cleanup, old-leaf privacy and temporary policy restoration. Original
state and process bytes matched; sources stayed stopped.

The browser prerequisite is external vendor software, not redistributed inside the
HIDS package. Its exact 301-file manifest is
`packaging/browser-inputs.json`, SHA-256
`4cf7930957249f1561eb9f4bf55b68d4c791d7a59e675454728249e6abe1147a`.
It records the already tested Chrome/158.0.8127.18 input obtained with Playwright
1.65.1; the vendor ABOUT file identifies Google Chrome. Do not generalize these
results to other Chromium builds, Snap packages, platforms or browser versions.
`hids-browser-prepare` verifies all inputs and libraries, copies them to a fresh
root-owned `/opt/hids-browser`, reuses only an exact matching installation and
refuses unknown input. No download, root browser, global trust change or unrelated
browser replacement. `/opt/hids-browser-prepare.v5subktw/report.json` passed real
copy/reuse and bad-input-no-publication, with old-state preservation.

Only Ubuntu `libnss3-tools` 2:3.120-1ubuntu2.2 was added to Linux 2 using its signed
Ubuntu package source. The simulation and actual install had one new package,
zero upgrades/removals. Normal browser trust/profile data and logging policy stayed
unchanged. `/opt/hids-final-launch.gwfise22/report.json` then passed the recreated
browser plus `/usr/bin/certutil` through the production pipe/HTTPS launch path,
actual root status CLI, saved choices and preservation checks. All sources stopped.

The root-only isolated leaf regression also passed strict umask, reuse, wrong pin,
unsafe key, real near-expiry renewal and expired-leaf renewal with old material
unchanged. Only a local test-process clock mock was used for the near-expiry edge;
the VM clock and system trust stores were not changed.

## Final verified development artifact

This section records the original `.6` checkpoint. The later verified `.7`
installer-preflight fix and fresh-install/upgrade acceptance are recorded in
[the Copilot build follow-up](copilot-build-followup.md); `.6` is retained unchanged.

Version `0.1.0~dev20261113.6`, Ubuntu 26.04 AArch64/Python 3.14 only.
Size **3,055,096 bytes**. SHA-256:
`79f55d29fa022a3f8450ca51509abff67af6b148636de2e35ac119602be9db95`.
Private VM artifact:
`/home/ivy/hids-browser-compare.9z_gnv_e/development-packages/hids-development_0.1.0~dev20261113.6_arm64.deb`.
Verified Mac temporary copy:
`/private/tmp/hids-first-build/hids-development_0.1.0~dev20261113.6_arm64.deb`.
Only the installer, not native security data/reports/keys, was retrieved.

Source snapshot `hids-src-20261114T002100Z-93d3e5b7f8a9`, 411 files; manifest
`0aa1dbe13098a08557cc385d5e38ec89898140fb6599dcc715b64910f6cc08f7`.
Final ten-phase report:
`/home/ivy/hids-browser-compare.9z_gnv_e/combined-dashboard-checks/run-20261114T001623Z-622c4ef43234/report.json`.
**161 Python tests**, **24 client tests**, zero skips/failures, TypeScript and all
three frontend builds passed. Counts are scoped, not a claim of complete project
coverage. The native binary is the independently verified C-01–04 production
artifact `e5afaa5b01e38fa9d3768f96996ad5ca5c6fcdffae3073d331677147c7c11639`;
collector inputs/recipe were byte-compared to its passed native/offline checkpoint.

The offline builder checks exact source/report/native hashes and pinned runtime
versions plus wheel RECORD hashes, includes runtime/frontend/nlohmann license
notices and build-input provenance, and ships prebuilt assets. The main artifact
contains no vendor browser binary. A stage gate rejects runtime state, lab manuals
in code, private-key markers and unexpected external links. Final independent
archive inspection passed all 649 regular payload files: no actual VM hardware or
source UUID, private key, runtime data, VM build-home path, special privilege bits
or unexpected symlinks. All archive owners are root; the only symlink is the
explicit system Python interpreter reference.

An earlier candidate inadvertently included an API lab README containing the VM
identifier. Inspection caught it before retrieval/delivery. Runtime packaging now
excludes those manuals, with regression tests and the stage gate. Earlier internal
candidates are retained as superseded test evidence, not the delivered artifact.

## Independent installation, restart and upgrade

Final report: `/opt/hids-package-acceptance.ob9ij9_4/report.json`.
A fresh copy-on-write Ubuntu root used private PID, mount **and network** namespaces,
empty HIDS directories, fresh nonlogin roles and locked test credentials. The base
Ubuntu system packages were shared read-only; all package writes went to isolated
layers. The running Linux 2 installation was never overwritten by this package.

Fresh installation configured successfully, enabled/started no units and created
no event DB or activation grant. Per-install UUIDs were generated and differed
from Linux 2's actual source identity. Starting the coordinator without a grant and
the collector without its root configuration was refused before collection.

Three **sanitized synthetic** lifecycle fixtures exercised the installed store and
packaged HTTPS/API closure. These are separate from the three real retained events
in the earlier VM trial. The API displayed the frozen fixtures while missing M4
history left authorization usable. Stop/restart revoked the old session, retained
history and allowed fresh authorization. A real package version upgrade from
`0.1.0~dev20261113.5` to `.6` preserved DB bytes, IDs, keys, confirmed choices and
prior configuration. Downgrade refusal preserved the same bytes. Recreating boot
metadata did not restore authority. Original host preservation passed afterward.

This is an independent installation-root test, **not** a fresh complete VM boot.
Production systemd isolation and the real ordinary-browser path have their separate
Linux 2 evidence above. Initial harness issues (identity import path, incomplete
masking of old HIDS state, root-directory traversal mode and normal Uvicorn SIGTERM
status) were fixed; failed attempts remain private. No production restriction was
weakened to obtain a pass.

## Product stopping point and remaining scope

The first local installable development checkpoint is ready; reassess before
adding features. [Operator/install guide](../../packaging/DEVELOPMENT.md).
Fresh installation supports process Activity and protected frozen display; it does
not add a process security detector, executable/user enrichment, authentication
source or general Audit installation. Existing M4 informational findings can be
viewed only where that approved history already exists. No automatic OS logging
changes, remediation, source restart, history deletion, wider human access or CA.
Wider release thresholds, distributions/architectures, browser versions and full
v0.1 requirements remain open. No commits/pushes or Mac system changes were made.


Final independent post-work proof:
`/opt/hids-first-build-final.0spvozzn/report.json` passed original preservation,
all six selection revisions with empty revision 6, no owned activation/grant,
inactive process/viewer units, removed temporary browser policy and DB-owner
integrity checks. The real stores remain three process events with the same clean
stopped interval, and M4 19 events/one finding/16 unevaluated events. Post-build
changes are handoff documentation only; all other snapshot inputs were rehashed
unchanged against the delivered artifact's source manifest. Git remains on main
at `d921a2bb4e74f245a60723011b36d9f614cde2ef`, with no staged changes or publication.
