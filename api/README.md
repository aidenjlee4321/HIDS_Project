# Dashboard APIs: pilot, protected history and source setup

The owner accepted D-12a/D-12b for the separate synthetic-only pilot below.
D-12c now also accepts the bounded protected history entry described at the end
of this guide; [implementation/acceptance](../docs/validation/m4-history-view-acceptance.md).
The pilot entry remains synthetic; neither entry is a production deployment. See the
[mechanism and threat limits](../docs/implementation/dashboard-session-mechanism-review.md)
and [executed acceptance](../docs/validation/dashboard-session-pilot.md).

## Synthetic entry

`pilot_sessions.py` owns volatile one-use grants and read-only sessions;
`pilot_app.py` exposes a closed FastAPI surface; `pilot_service.py` accepts the
root-created named HTTP/control listeners under the existing unprivileged
backend identity. `pilot_cli.py` is the root-only control client. None imports
M3/M4 storage or collector code. That entry exposes no HIDS records or source controls.

The React/TypeScript page under `frontend/` shows a fixed hostile-text example
and logout/access-check controls. A new link in the same tab intentionally reloads
the document, then consumes the one-use grant and removes its URL fragment.
Tokens stay in memory; a normal refresh cannot reauthorize. SSE remains later work.

## Reproducible private VM build

Use Ubuntu, private build directories and existing approved service identities.
`api/requirements-pilot.txt` pins the minimal 14-package runtime closure;
`requirements-pilot-test.txt` separately pins the automation/component-test
closure. `requirements-pilot.in` records the two direct runtime requirements.
The test packages are not copied into the service runtime. Pinning and the recorded
publisher checks do not establish that a dependency has no vulnerabilities.

```sh
python3 -m venv /your/private/build/runtime-venv
/your/private/build/runtime-venv/bin/pip install -r api/requirements-pilot.txt
python3 -m venv /your/private/build/venv
/your/private/build/venv/bin/pip install -r api/requirements-pilot-test.txt
/your/private/build/venv/bin/python -B -m unittest discover -s tests/unit -p 'test_dashboard*.py'
```

Build `frontend/` with the recorded private Node 26.13.1 toolchain, using `npm ci
--ignore-scripts` then `npm run build`. Exact dependency resolution/integrity is in
`frontend/package-lock.json`. Serve only the built assets through the protected
FastAPI pilot, never a development server as the product. Do not install Mac or
global VM tools as a side effect of these commands.

Source snapshots now include TypeScript, CSS, HTML, dependency inputs/locks and
the explicit access launcher, while excluding generated `dist`, environments and
`node_modules`. Verify the source manifest before and after acceptance. The
harness compares each frontend source file against its build input and records
asset hashes before copying into root-owned runtime paths.

## Explicit Linux 2 acceptance

The integration harness is lab-specific: it expects the existing workflow lock,
M3/M4 private state and historical artifact/source-prefix baseline reports. It
refuses before provisioning on a mismatched guest UUID/source manifest, active
M3 pipeline, existing M4 trial config or an unknown prior pilot installation.
It must run from an active ordinary-user login using sudo, because Ubuntu's Snap
Firefox/user bus needs that live session. Running the whole harness as a detached
root system service does not create that user session. No linger/account setting
change is needed. Browser automation uses a fresh ordinary-user headless Firefox
profile in that user's scope, never a root browser or their normal profile.

The build directory must contain separate pinned `runtime-venv`/`venv`, verified
private geckodriver, and `source/frontend/dist` built from the same verified
snapshot. Then, from that snapshot in the existing Linux 2 login:

```sh
sudo python3 -B tests/integration/dashboard_pilot_ubuntu.py \
  --build /your/private/build \
  --expected-manifest VERIFIED_SOURCE_MANIFEST_SHA256 \
  --expected-vm-uuid 46330e53-4a53-4a94-b9d4-0adefd192ab7
```

Do not use this harness as an installer on another host. It creates only its own
root-owned `/opt/hids-dashboard-pilot` runtime, temporary root config and transient
systemd unit files. No units are enabled. Root-only socket directory 0700/socket
0600 remain in force; Python does not manage that pathname. The client checks the
root-protected path and root/designated-backend server UID; the server requires
UID 0 for every control connection. Prior pilot asset bundles/reports are retained.
The harness stops its activation and removes its own temporary config/unit files.
The tested `/opt` runtime is retained inactive; it is not the production install.

The fixed manual socket templates use loopback port 18765, matching the example
root configuration. Changing the lab port requires the listener template and
root config to agree. No wildcard bind or fallback port. The root terminal-only
launcher is `packaging/hids-dashboard-access`, copied into that private runtime;
its two operations are `mint` and `revoke_all`. It refuses piped output. Never
copy generated URLs/tokens into tickets, logs, command arguments or Git.

Broader real-data routes, production origin/browser trust, complete dashboard features,
unattended enablement, installation packages and release acceptance remain
separate gates. The 30-minute absolute expiry is exercised with a controlled clock;
the live harness also waits for actual 60-second grant and 300-second idle expiry.

## Review fixes and new helper boundaries

[Security-fix evidence](../docs/validation/dashboard-security-fixes.md) supersedes
the original UI race/timer behavior. Run controller tests with the private Node
toolchain: `node --test tests/frontend/test_session_client.ts` from the verified
snapshot root. `test_history_bounds.py` exercises the separate pre-load value
limits. `history_bounds.py` opens no file and performs no public API projection;
the separate history adapter now adds schema, hashes, provenance and authorization.
`tls_leaf.py` supplies explicit leaf/key validation, not a trust-store installer
or a trust policy. Synthetic TLS/native checks passed; Firefox leaf-peer
acceptance failed, while the subsequent
[Chromium no-CA/HTTPS flow passed](../docs/validation/no-ca-browser-comparison.md).
The API factory now accepts an explicit trusted http/https scheme and rejects
physical transport/Origin mismatches; request headers cannot select the scheme.
The existing operator pilot remains synthetic and defaults to HTTP. The actual
synthetic HTTPS proof was a bounded test harness. The separately approved
history service is described below and remains manually activated/stopped.


## Approved frozen-history entry

`history_view.py` loads only the fixed live-v2 M4 store through a private,
read-only mapping, validates a finite selection and closes SQLite before HTTP.
`history_app.py` exposes only the D-12c summary/event/finding list/detail contract.
`history_service.py` accepts the root-created HTTPS/control listeners and refuses
writable store mappings; `history_cli.py` reuses root-only peer/socket checks.
History credentials have `history:read`; the pilot default remains `pilot:read`.
Neither a request body nor query can choose the scope, database, binding or rule.
The view never starts collection, evaluates events or changes storage.

The manual templates under `packaging/systemd/hids-dashboard-history*` use fixed
HTTPS port 18765, root-only control permissions, a read-only store mount with other
HIDS state hidden, zero-capability backend, MemoryMax=256M/TasksMax=32 and a
ten-minute runtime ceiling. They are not installed/enabled by default. The fixed
root config is `/etc/hids/dashboard-history.json`: closed version 1, mode
`frozen-history`, port 18765, expected device/inode, one/two exact binding keys and
certificate SHA-256. The lab config is root:backend 0440 and is removed on cleanup.
TLS paths are fixed under `/etc/hids/dashboard-history-tls/`; seven-day CA=false
IP-127.0.0.1/server-auth leaf, pinned DER hash and root:backend 0440 key under 0750
parent. Startup and each grant validate it; no CA, renewal or trust fallback.

Reuse the pinned runtime/test dependencies and private VM Node tooling above.
Run `npm run build:history` in a private frontend build copy; its `dist-history`
is excluded from source snapshots alongside `dist`/node_modules. Run the existing
14 client tests and `python -B -m unittest discover -s tests/unit -p 'test_history*.py'` with the private test interpreter. Serve the compiled assets
through FastAPI; never a public development server.

`tests/integration/history_ubuntu.py` is an explicit Linux 2 lab harness, requiring
the pinned UUID, original preservation reports, inactive collection and existing
private browser/NSS/runtime fixtures. It takes `--expected-manifest`, `--assets`,
`--browser-build` and `--tools`. Omit `--real` for synthetic acceptance first;
`--real` is only for the owner-approved existing two-binding/19-event trial, after
those gates. It verifies build inputs and asset hashes, provisions fresh root TLS,
manual units/config and temporary exact-binary AppArmor permission, then stops and
removes that activation. It reuses the verified root-owned Chromium image instead
of duplicating it. It is not a general installer for another host.

The root terminal client may be invoked with isolated Python and the trusted
`/opt/hids-dashboard-history/code` import path, module `api.history_cli`, operation
`mint` or `revoke_all`. Main refuses piped output. Grant URLs go only to the
explicitly authorized browser via a private terminal/channel, never command args,
Git or routine logs. Browser HOME/NSS, XDG and user-data must all be new/private;
Chromium profile-only separation is insufficient. The trial browser has certificate
verification and its own sandbox enabled. The ordinary browser/account remains
entrusted. Existing/system trust, CA import, Mac settings and normal-browser setup
are outside this trial.

[Exact final evidence](../docs/validation/m4-history-view-acceptance.md) records
all synthetic/real/browser and independent preservation checks. Payload-bearing
reports/screenshots remain private in the VM. All current history units/listeners
are stopped and the config removed; root-owned runtime/TLS and private evidence
remain retained. A future activation still requires correct root selection and
new per-session authorization. Search, live updates/health, production lifecycle,
first-run source selection and release packaging remain open.


## Accepted first-run setup entry (D-14a)

The [accepted contract](../docs/implementation/first-run-control-review.md) and
[executed acceptance](../docs/validation/first-run-acceptance.md) cover a separate
manual setup entry. `setup_preflight.py` runs only as a trusted root one-shot:
recognized metadata/configuration and intended-reader executable access, no event
sampling, source/DB-writer initialization, activation-socket probing or logging repair.
It never calls the lab's source-prefix preservation helper.

`setup_contract.py` validates the fixed registry, closed snapshot and preferences.
`setup_sessions.py` adds one volatile 60-second draft/session (four/process), bound
to the exact assessment and confirmed revision. `setup_app.py` exposes only
`GET /v0/setup` and `POST /v0/setup/draft`, plus existing authentication routes.
Its `setup:draft` bearer cannot read history or control collection. No HTTP
start/stop/save endpoint. `setup_service.py` is unprivileged, hides original HIDS
state and uses existing manual HTTPS/root-control boundaries and limits.

`setup_cli.py` provides terminal-only `mint`, `revoke_all`, `review`, `confirm/start`
and `stop`. Invoke it through isolated Python with the trusted root-owned
`/opt/hids-dashboard-setup/code` import path. Draft references are entered at a
private prompt, never arguments or logs. Confirmation independently checks current
facts/revision, persists complete choices and only then invokes eligible fixed
adapters. There is no arbitrary unit/path/command or privilege escalation from a
browser bearer. `setup_manager.py` records exact owned Audit activation scope under
root-only `/run/hids-setup` and refuses unowned/uncertain takeover or edits.

`setup_store.py` keeps immutable `selection-NNNN.json` files under `/etc/hids/setup`:
root:backend directory 0750, records 0440, max 16 revisions/4 KiB each, no automatic
deletion. Pending crash temporaries do not authorize collection. Preferences do not
automatically resume sources; source-runtime restart needs a fresh root action.
Viewer restart/logout expires browser grants/drafts, not an independently confirmed
source. cn_proc/journal controls stay disabled pending their own live/identity gates.

Build with `npm run build:setup` in a private VM frontend copy. `dist-setup` is
excluded from snapshots. Reuse existing pinned runtime/test closures; run
`python -B -m unittest discover -s tests/unit -p 'test_setup*.py'`, the scoped
rotation-guard tests and all 19 client tests. The settled checkpoint additionally
runs history/auth/M3/M4/workflow regressions. No new runtime framework is introduced.

`tests/integration/setup_ubuntu.py` is Linux-2-specific, not an installer for another
host. It requires verified manifest/build inputs, original private preservation
reports/lock, inactive collection and the existing isolated browser/NSS fixtures.
Arguments: `--expected-manifest`, `--assets` (private frontend `dist-setup`),
`--browser-build`, `--tools`; omit `--real` for synthetic gates first. Synthetic
acceptance includes the actual M3 control service against private storage with
unit/native-presence stubs, actual UID checks, crash/VFS faults, HTTPS browser/root
PTY confirmation and real draft expiry. `--real` is deliberately restricted to the
approved empty/blocked-source trial; it must not configure OS logging or make a
blocked source eligible. Record unavailable gates honestly.

Actual empty preferences remain at revision 2 with no active source. The setup
viewer/units/listener are stopped and temporary activation removed. Root-owned
runtime/snapshot, preferences and private evidence remain. The existing history
entry remains separate and unchanged; no CA, normal-profile trust or default
service enablement follows. Current implementation is a bounded setup slice;
usable source deployment, live health, hot edits and packaging remain later work.

## Process source integration boundary

The approved process pipeline has an actual installed owned-child acceptance
record, root-confirmed activation and separate zero-capability services.
[Evidence](../docs/validation/process-pipeline-acceptance.md). The setup metadata
registry recognizes the implemented adapter only when its installed code, units,
identities and inactive state verify. Previous immutable selection catalog hashes
remain readable; no previous choice starts collection automatically.

There is currently **no process event HTTP route**. Existing history:read is
limited to its accepted M4 projection; it must not silently acquire process data.
Use `scripts/process_workflow.py` from a verified source snapshot with the existing
Ubuntu test venv for this source's offline scope. It opens no native subscription.


## First installable development workflow

P-01–P-04 now has bounded acceptance evidence and a local Ubuntu arm64 artifact.
Start with [the operator guide](../packaging/DEVELOPMENT.md) and
[immutable source/report details](../docs/validation/combined-dashboard-acceptance.md).
`combined_dashboard_workflow.py` is the named source-verified synthetic scope.
It includes the ordinary-user `session_https` phase: private test-only TLS,
synthetic sessions and empty frozen views, with no store/config reads or global
trust changes. See [transport evidence](../docs/validation/dashboard-session-transport.md).
`build_development_deb.py` requires its passed report, explicit native SHA/source/
report, pinned runtime site-packages and frontend inputs. Both run as an ordinary
Linux build user and neither collects nor installs. Root-only acceptance harnesses
remain explicit lab tools, not installers for other hosts. The development package
keeps scopes separate, sources manual, data local and old state preserved. A fresh
installation-root pass does not establish a whole new VM boot or full release.
