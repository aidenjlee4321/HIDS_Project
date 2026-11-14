# First Ubuntu development build

This guide ships with each development package. Check the installed version with
`dpkg-query -W hids-development`; exact build version, source/native hashes and
dependency provenance are in `/usr/share/doc/hids-development/BUILD_INPUTS.json`.
For the latest artifact and scoped acceptance results, consult
`docs/current-state.md` and `docs/validation/` in the source checkout. Those lab
records are deliberately not included in the installed runtime package.

This build supports Ubuntu 26.04 AArch64 with Python 3.14 and systemd. It provides
explicit process lifecycle collection → independently validated private SQLite →
a root-authorized frozen HTTPS dashboard. It is a development checkpoint, not the
complete v0.1 security product or a claim of continuous monitoring reliability.

The package contains application/runtime code, the tested native collector,
prebuilt frontend and license/input provenance. It contains no VM databases,
source/installation UUIDs, private keys, passwords, grants or vendor browser binary.
IDs are generated during installation; local leaf/key material is generated only
when root explicitly prepares/opens the dashboard. No collection is enabled or
started by installation or reboot. Existing Ubuntu Audit/journal/PAM policy is not
changed. Existing history and source choices are never automatically removed.

## Install and prepare the browser on Ubuntu

Use the locally verified artifact named in the acceptance record:

```sh
sudo apt install ./hids-development_VERSION_arm64.deb
sudo hids-browser-prepare --from /path/to/extracted/tested-browser
```

`apt` supplies the declared Ubuntu certificate-tool prerequisite (`libnss3-tools`)
and normal OS runtime dependencies. The external browser is the exact previously
tested `Chrome/158.0.8127.18` input from the pinned Playwright 1.65.1 toolchain.
Obtain/extract that upstream browser separately under its own terms; it is not
redistributed in the HIDS artifact. This does not establish compatibility with
other Chrome/Chromium versions or Ubuntu Snap wrappers.

The browser preparation command checks all 301 input file hashes against
`BROWSER_INPUTS.json`, rejects extra/symlink/changed files, verifies library
availability and creates a root-owned copy at `/opt/hids-browser`. It never
downloads, executes a root browser, changes trust or replaces an existing browser.
A matching prior copy can be reused. Missing input or libraries fail closed.
The exact pinned input can be reused on another supported system; the source
folder's location is not saved and no VM identity is required.

## Select collection explicitly

Run from a local terminal with sudo:

```sh
sudo hids-sources status
sudo hids-sources start-process
```

The second command explains retained fields and asks for `START`. It saves the
process-only choice and initializes only the eligible process adapter through the
existing setup manager. The collector and backend remain separate unprivileged,
zero-capability services; root controls the one-use start grant and activation
lease. Status is metadata only, not payload sampling or proof of complete delivery.
After a restart, remembered choices are not permission to resume collection.

The process source supplies fork/exec/exit, process/thread IDs, available parent
IDs, native CPU/sequence/raw monotonic values and observation/receipt metadata.
It supplies no executable/user/arguments/environment enrichment or reliable wall
activity timestamp. A thread exit must not be interpreted as whole-process exit.
There is no supported process security rule in this build. Fresh installation
therefore provides process Activity, not a new process detector or alert feed.

## Open the protected snapshot

```sh
sudo hids-dashboard open --recent-process --temporary-browser-userns
```

Root explicitly selects up to two recent stored process activations. An ordinary
isolated browser opens `https://127.0.0.1:18765`; a fresh HOME/NSS/profile trusts
only this local server leaf. The temporary exact-browser userns permission keeps
Chromium's namespace/seccomp sandbox and is removed after exit. No CA, global
trust-store/profile edit, certificate-warning bypass or root browser is used.
The bootstrap travels through a private pipe, not browser command arguments.

Every route requires the new `dashboard:read` scope. Existing tokens retain their
previous scopes. Bootstrap: one use/60 seconds; sessions: five-minute idle,
30-minute absolute, at most four grants/sessions. Logout/reopening/restart revoke
old authority. Closing the browser removes only its new transient profile and
stops the viewer. It does not stop a separately authorized collector.

Ordinary Ctrl-C/failure cleanup stops the viewer and terminates only that launch's
browser worker/process group. A temporary policy load failure also triggers
removal and a kernel-state check. If removal cannot be confirmed, the launcher
refuses and retains its policy file for administrator inspection. Forced SIGKILL
or a host crash cannot be assumed to run this cleanup.

This is a frozen bounded view: latest 128 process events/128 intervals, 20/page,
explicit capture time/truncation and historical diagnostics. Observation time and
storage arrival are not activity chronology. Reopen explicitly to capture newer
records. Current monitoring is not assessed by the frozen dashboard.

Frozen-view configuration updates preserve a synced byte-exact prior copy and
atomically publish the complete new config. An interrupted update leaves the old
or new selection/certificate binding in place; retry requires explicit root launch.

An existing approved M4 store can be included with `--retained-audit`. This only
shows the existing bounded Audit history/informational finding projection; it
creates no M4 history, imports/evaluations, Audit plugin/rules or new detector.
The old 16 unevaluated events stay unevaluated. A missing/failed family leaves the
other family and authorization usable. Fresh installations have no M4 history.

Explicit source stop:

```sh
sudo hids-sources stop
```

Type `STOP` to stop only setup-owned HIDS activations. `hids-dashboard stop` stops
only the viewer. No automatic deletion: source retention stops at its bounded
capacity rather than erasing older evidence. Saved selection history is finite
and never silently recycled.

Stop also revokes a matching unused start authorization after an interrupted
start. Active termination requires the recorded runtime to match the live service
invocation. If Stop reports `stop_unconfirmed`, inspect status before retrying;
unknown active components are left untouched. A failed or unknown component does
not become a confirmed stop just because an unused authorization was revoked.

## Upgrade, evidence and limits

Stop the viewer and owned collection before installing a new package. Active or
unmanaged/conflicting installations are refused. The installer preserves source
IDs, installation IDs, histories, private keys, saved choices and prior config
revisions. Downgrades are refused. Removal must not erase data/keys/accounts;
there is no broad purge helper. Existing manual Linux 2 installations are not
silently converted by this package.

Collector-hash updates retain a durable byte-exact configuration backup and
atomically replace the active file, preserving source identity and limits on
retry. If an older interruption left the active config missing with retained
history or pending metadata, configuration is refused. Preserve those files for
explicit administrator recovery; do not erase them or generate a new identity
to get past the refusal.

The first acceptance uses an independent copy-on-write Ubuntu root with private
PID/mount/network namespaces, shared read-only Ubuntu base and fresh HIDS state
and roles. That tests packaged dependencies/metadata/HTTPS/restart/upgrade paths;
it is not a full newly provisioned VM boot. Exact production systemd restrictions
and ordinary-browser behavior have separate Linux 2 acceptance. Wider hardware,
other distributions/architectures, browser builds, source coverage, detections,
resource release thresholds and unattended/release operation remain open.

Build/test commands and immutable report hashes belong in the source checkout's
`docs/validation/` records, including `combined-dashboard-acceptance.md` and its
linked follow-ups.
No commit, push, deployment to another real host or Mac system change follows
from building these artifacts.
