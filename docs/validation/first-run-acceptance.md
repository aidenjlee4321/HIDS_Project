# D-14a first-run setup — bounded implementation acceptance

The owner accepted [D-14a](../implementation/first-run-control-review.md) in the
continuation following the explicit first-run policy question. Implementation,
synthetic gates and the approved real metadata/empty-selection trial passed.
This is a first-run consent/control slice, not release readiness or evidence that
all source adapters work live.

## Working behavior

- The protected setup page shows a frozen recognized-source assessment and saved
  choices. It labels preflight/runtime uncertainty and offers only eligible sources.
  Browser choices are volatile drafts, never collection permission.
- `setup:draft` is distinct from `pilot:read` and `history:read`. Only authenticated
  setup sessions can fetch `/v0/setup` or stage `/v0/setup/draft`. There is no HTTP
  configuration/start/stop/export or arbitrary path/command endpoint. Root/sudo
  issuance, one-use grants, memory-only credentials, Host/Origin/CSRF/CSP limits,
  verified HTTPS and the ordinary sandboxed browser remain in force.
- One draft/session, four/process, 60-second lifetime; replacement, logout, revoke
  and viewer restart invalidate it. References are opaque and one-use at root take.
  The UI clears expired references; late responses cannot restore them after logout
  or overwrite a newer authorization generation.
- The root terminal CLI independently reviews/rechecks a draft, compares current
  facts and confirmed revision, and requires explicit confirmation. References go
  through private terminal input, not argv. Only root executes the fixed
  confirmation/start/stop operations; the backend has zero effective capabilities.
- Confirmed choices are immutable root-owned revision files under `/etc/hids/setup`,
  root:backend 0440 in a 0750 directory, with bounded canonical content and a pinned
  registry. Atomic file/directory sync precedes initialization. Retain up to 16
  revisions and refuse further writes; no automatic deletion/migration. Safe private
  crash temporaries are not choices or activation authority.
- Saved choices do not start/resume sources. Root take/confirmation is fresh and
  single-use; empty choices call no adapter. Collection-runtime restart requires
  fresh activation. A viewer restart expires its browser grants/drafts and does
  not itself stop an independently confirmed collection interval.
- The root-owned transient ownership journal under `/run/hids-setup` tracks exact
  activation/source/generation. Known active unmanaged M3 **or legacy M2** services
  block confirmation, including an empty request. Stops affect only the owned
  Audit scope/units. Unknown cleanup remains unconfirmed; no blind takeover, signal
  to unrelated processes, OS logger stop or automatic retry. Editing held choices
  requires confirmed stop first.
- The fixed Audit adapter reuses existing M3 root control, admission, scopes and
  lease semantics. Initialization is reported as delivery unproven. Its cleanup
  checks only the intended HIDS reader identity/executable/activation after
  confirmation; no general process enrichment or argument retention is added.
  cn_proc/journal controls stay disabled pending their own identity/live gates.
- Root preflight reads recognized config/artifact/account/unit/build metadata and
  checks executable access under the intended existing reader identity. It does
  not open event payloads, instantiate sources/writer stores, connect activation
  sockets to probe usability, subscribe, change groups, install or repair logging.
  Source-prefix hashing belongs only to separate authorized lab preservation.

Modules: `api/setup_contract.py`, `setup_store.py`, `setup_preflight.py`,
`setup_sessions.py`, `setup_app.py`, `setup_service.py`, `setup_cli.py`,
`setup_manager.py`; React entry `frontend/src/setup.tsx`; manual setup systemd
service/socket templates. No new runtime framework/dependency closure or account.

## Executed checkpoint and build identity

Final verified source `hids-src-20261113T122635Z-ca8ce52de598`, manifest
`20f9df59347acef8ebcfd022e0f50faf08a38889e3211fdf85327fb5efbdbc50`.
Ubuntu passed **376 Python tests**, including 44 setup, 30 prior design-model,
12 rotation-guard, 44 history, 42 pilot/auth, 21 workflow, 87 M3 and 96 M4 cases;
all **19 TypeScript client tests** passed. No skips. Private report:
`/home/ivy/hids-browser-compare.9z_gnv_e/setup-checks/run-20261113T063732Z-01f927dd4c41/report.json`.

All three production UI entries built with the existing private pinned tools from
`hids-src-20261113T121340Z-0b9cc80f1498`, manifest
`fe80b44eb207da71725185fcecec7d37856ff350bf26341a7f994f6b71bbcc9f`.
The final checkpoint byte-compared every frontend input with that build copy;
all were identical. Private build: `/home/ivy/hids-browser-compare.9z_gnv_e/setup-build.bx8p6cer/frontend`.
The previous checkpoint/trials remain retained; final changes tightened the
recognized unmanaged-service guard without changing client/storage/auth behavior.

Final served assets: HTML SHA-256
`ea59962ebb9eaa5d74cc20cdb736f2cb919a23e5a8d0b70b9dfc5728010d8667`,
JS `1b1e31ee6cf3f04aef1d840ae442d93f0d2b1b23e0642fd44c867e8c89e3d63a`,
CSS `4148073b5f1e55b311684f205e8c2f11c081adff71ae6e635bc36ba293794462`.

## Actual Ubuntu boundary evidence

| Private report | Executed scope |
|---|---|
| `/opt/hids-setup-final-faults.bkp79s2l/report.json` | Final source: four actual config-writer SIGKILL cuts; private read-only/ENOSPC; actual M3 root-control IPC; foreign scope refusal; actual UID peer checks; production preserved |
| `/opt/hids-setup-lab.gnb2bfw7/private/report.json` | Full synthetic setup trial: 20 outer checks, 14 browser checks, actual 60-second draft expiry/display clearing and root-terminal confirmation |
| `/opt/hids-setup-lab.vkwj5_46/private/report.json` | Final real metadata/empty-selection trial: 16 outer and 13 browser checks passed |
| `/opt/hids-setup-lab.vkwj5_46/private/independent.json` | All 11 independent preservation/cleanup checks passed; empty saved revision 2, no active ownership, all three HIDS service-account process counts zero |

The four process deaths were at before file sync, before publication, after
publication and after directory sync in the **actual configuration writer**.
Before publication the old configuration remains; after publication the complete
new preference is readable, with no persisted activation authority. Unit faults
also verify the manager never initializes after an unconfirmed persistence result.
These cuts are not every power-loss/filesystem boundary in the entire controller.

Read-only and real ENOSPC used private mount namespaces; FULL used a 64 KiB tmpfs,
not host disk exhaustion. Source/M3 storage stayed untouched. Actual production M3
`Service`/`Runtime` in an isolated synthetic directory accepted activate/deactivate
through the real root control client; a different activation was refused. **Unit
start/stop and native reader presence were stubs in that IPC test**. No actual
native Audit reader/source event was exercised or claimed by it. A deliberately
public *synthetic* Unix socket independently proved UID-1000 denial/UID-0 admission;
production control directory/socket stayed root 0700/0600.

Ordinary-account Chromium used the previously verified root-owned test image and
new private HOME/NSS/XDG/user-data; direct peer trust, certificate verification and
sandbox enabled, no CA or bypass. The setup trials verified authenticated metadata,
blocked/unvalidated choices, empty private browser storage, replacement/replay,
root CLI private-PTY confirmation, saved choices across viewer restart, refresh
requiring a new link, missing HTTP collection-control routes and a buffered completed
draft response delivered after logout. Synthetic acceptance additionally waited the
actual draft TTL and verified server refusal and client clearing. Existing
[certificate negative tests](no-ca-browser-comparison.md) retain their separate
executed scope; no new full TLS negative matrix is claimed here.

The ten-minute service ceiling, MemoryMax=256 MiB and TasksMax=32 were present.
Sampled cgroup MemoryPeak values were 42,999,808/42,983,424 bytes around the synthetic
service/restart and 40,800,256/41,992,192 bytes around the final real service/restart.
Peaks reset with instances; these samples are not a maximum workload, RSS guarantee
or release threshold. Root CLI/fault processes are separate from that backend cgroup.

## Real result and retained state

The real metadata assessment correctly kept Audit blocked under unchanged existing
configuration and cn_proc/journal unverified/disabled. The actual browser staged
**empty choices**, root-terminal confirmation saved them, and a restarted viewer
showed the saved revision. Two bounded real confirmations left immutable empty
selection revisions 1 and 2, root:backend 0440. No source authority is persisted;
`owned.json` contains an empty instance map. No collector was initialized.

The original 357 M3 databases, M4 19 events/three evaluations/one informational
finding/16 unevaluated old events, v1 backup, 29 installed artifacts, original
Audit prefixes/rules and unit state remain preserved. No fresh full integrity sweep
is claimed: baseline hashes retain the earlier verified inventory. No logging/PAM/
Audit rule change, package install, normal-profile/system trust or Mac system change.

All setup service/socket units, viewer/listener and test workers are stopped;
temporary AppArmor permission and activation config/runtime units removed. Normal
NSS/global namespace policy are unchanged. New empty preferences, transient empty
ownership metadata, inactive root-owned runtime/snapshots and private evidence are
retained intentionally. No actual log copying, source deletion, baseline rewrite,
commit or push occurred.

## Rotation guard resolution and remaining gates

`tests/integration/source_preservation.py` is lab-only. It resolves rotated names
only in the original directory and requires the original inode number, trusted
regular linked file, sufficient original byte length and exact original prefix
SHA-256. It uses bounded scans/reads and rejects missing, mutated, shortened,
symlinked, hardlinked or unsafe inputs. It does not accept a replacement with the
same bytes but a new inode, copy logs or revise the baseline. Twelve cases and
all privileged trial preservation guards passed on the already-rotated real files.
The earlier pathname assertion failure remains in the historical review evidence;
the next run can use the corrected guard without dropping preservation checks.

The first-run trial is complete within this scope. Actual native-source startup/
shutdown under this new controller when Audit is already configured, intended-account
live process-connector validation, journal deployment, hot edits, live health/SSE,
normal-browser/certificate lifecycle, packaging, broader security rules, resource
thresholds and release acceptance remain open. The native Audit pipeline's prior
M3 acceptance is preserved; it is not a substitute for untested controller/source
combinations. Never enable OS logging or a disabled source merely to turn this
setup assessment into a green result.
