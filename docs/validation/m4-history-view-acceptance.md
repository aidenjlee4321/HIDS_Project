# Protected stored-history view — D-12c acceptance

The owner accepted the exact [D-12c contract](../implementation/m4-history-view-review.md)
in the continuation following the explicit bounded-history-trial question on
November 13, 2026. That approval covers selected retained records, the documented
fields/budgets, and the isolated direct-leaf HTTPS path. It does not enable
collection, unattended deployment, broader rules, CA trust or Git publication.

The implementation and bounded Linux 2 trials passed. The ordinary-account browser
viewed all 19 retained events and one informational finding; every exposed event
and finding matched protected database ground truth. The original 16 events remain
unevaluated. Collection and the M4 worker stayed stopped. All trial activations
are now stopped and their temporary config/unit/policy removed.

## Implemented boundary

- `api/history_view.py` validates the fixed live v2 store, expected inode/device,
  private paths/sidecars, exact schema/application ID, canonical envelopes/content
  hashes, binding plans, pinned rule and stored evaluation/finding relationships.
  Its dedicated URI read-only connection uses query-only/trusted-schema-off,
  50 ms busy timeout and a cooperative two-second overall loader budget. No writer
  constructor, writer lock, immutable read, migration, checkpoint or repair runs.
- `history_bounds.py` bounds SQLite types/bytes before full Python values are
  fetched. Cap-plus-one refuses an oversized view: 128 events/evaluations, 32
  findings, one rule, two bindings, four MiB canonical serialized view. That is
  not a four-MiB heap guarantee. Exact schema validation now runs inside the same
  bounded read transaction. The transaction and connection close before serving.
- `history_app.py` serves frozen memory only: summary, fixed-size pages and selected
  event/finding details. Every route requires `history:read`; `pilot:read` cannot
  authorize it. Per-start HMAC cursors bind view/route/position/session digest;
  only the optional bounded cursor query is accepted. Responses are capped at
  64 KiB, details at 32 KiB. No export, SQL, file, source, settings or live route.
- `history_service.py`, `history_cli.py` and manual systemd templates retain
  UID-0/sudo grant issuance, root-only control directory/socket, a non-root backend,
  60-second one-use grants, 300-second idle/1,800-second absolute session limits,
  four combined credentials, explicit logout/revoke and per-mint TLS validation.
  Port is fixed at HTTPS `127.0.0.1:18765`. Root selection config is root:backend
  0440; the leaf key is root:backend 0440 under a root-owned 0750 directory.
- The service maps only the selected store read-only under a temporary HIDS state
  filesystem; M3/runtime and backups are hidden. MemoryMax is 256 MiB, TasksMax
  32, RuntimeMaxSec ten minutes. The existing service account is resolved via NSS.
  Sharing a UID with other HIDS services is not protection from same-UID compromise.
- `frontend/src/history.tsx` supplies Overview, Activity, informational findings
  and linked progressive technical detail. It labels preparation/import clocks
  and stored outcomes; monitoring status is **not assessed**. All offsets/results/
  non-null nanosecond values are decimal strings, including zero. Missing values
  remain null. Native previews escape controls/bidi/invalid bytes and truncate
  explicitly; exact Base64 remains in detail. React text rendering is used.
  Authorization generations gate every sensitive result/display, including a
  completed response delivered after logout. No cookies or persistent tokens.

The original synthetic HTTP pilot remains the default in its separate entry point.
It has no history routes and cannot select history scope from an HTTP body.

## Executed evidence and source identity

The settled component/build snapshot was
`hids-src-20261113T100259Z-7061aff0ec06`, manifest
`07ffeddf49a967204098b35c3947e31cf0ec43e14b6fdc262eada64feb2d2e07`.
Ubuntu passed 44 history/value/HTTP tests, 42 pilot/auth/CLI tests, 96 M4 tests,
87 M3 tests and 21 source-workflow tests: 290 Python tests, no skips. All 14
TypeScript session/race tests passed, and both pilot/history production builds
completed with the existing private pinned toolchain/dependency closure.

Private checkpoint:
`/home/ivy/hids-browser-compare.9z_gnv_e/history-checks/run-20261113T040037Z-2ea6feeeb1d9/report.json`.
Build inputs/assets:
`/home/ivy/hids-browser-compare.9z_gnv_e/history-build.9861whfm/frontend`.

Final acceptance snapshot:
`hids-src-20261113T101534Z-5bd84212d173`, manifest
`4f5e3fdb8caf79146f7f9be2a69ba727bc2d8cf6d1d6e5e445f92613e5334889`.
Byte comparison against the component snapshot found only the two integration
harness files changed. API/backend, client and build inputs were identical.
The final harness independently checks each frontend build input, records built
asset hashes, verifies the original preservation baseline before setup and checks
source identity afterward. Historical report identifiers/host and guest clocks
are not a single synchronized activity timeline.

| Private VM evidence | Result |
|---|---|
| `/var/tmp/hids-history-trial.tto_m4qm/report.json` | Synthetic 25-event trial: 25 outer checks and 18 browser checks passed |
| `/var/tmp/hids-history-trial.fu6ob2br/report.json` | Real 19-event trial: 23 outer checks and 16 browser checks passed |
| `/var/tmp/hids-history-trial.fu6ob2br/independent-v2.json` | All eight independent preservation/cleanup checks passed; 357 M3 databases retained |
| `/home/ivy/hids-browser-compare.9z_gnv_e/history-browser.x37mfc69/report.json` | Synthetic browser report; screenshots/trust inventory private in the same directory |
| `/home/ivy/hids-browser-compare.9z_gnv_e/history-browser.m7vv1ntj/report.json` | Real browser report; screenshots/trust inventory private in the same directory |

The final browser was the same privately obtained Chromium test build as the
[no-CA comparison](no-ca-browser-comparison.md), reporting
`Chrome/158.0.8127.18`, executable SHA-256
`40c121f803bd7f2c3dc394a12f064d14af1faea4baf7938dd2a8edd5175086f6`.
The existing root-owned image was reused, avoiding duplicate browser copies.
Ubuntu NSS tooling and the pinned private Playwright closure were reused; no new
runtime framework, Mac software or global trust installation was needed.

Both browser trials verified direct-peer trust without CA entries or certificate/
sandbox bypass; namespace/seccomp sandbox status; foreign, wrong-name and expired
certificate rejection; plaintext rejection; unauthenticated denial on all five
history routes; root-authorized access; empty fragment/cookie/WebStorage;
lossless detail and finding-to-event linkage; logout with a buffered old response;
grant replay denial; and foreign-certificate rejection at the same port after
stopping the genuine service. Synthetic input additionally proved literal hostile
text and 20/5 pagination. Controlled-clock component cases cover expiry, scope,
revocation/restart and stale failures/new authorization. Earlier actual grant/
idle-expiry evidence remains in the [pilot record](dashboard-session-pilot.md);
this history trial does not claim another wall-clock 30-minute expiry test.

Both actual service processes had zero effective capabilities, no retained
`handoff.sqlite` descriptors, hidden unrelated state and a tested EROFS write
refusal. Missing/invalid selected history refused new grants while static locked
UI and root revocation remained available in the synthetic namespace. Cgroup
MemoryPeak was 46,088,192 bytes synthetic and 45,658,112 bytes real; sampled
TasksCurrent was one. These bounded workloads do not establish maximum-load or
release resource thresholds.

Built assets (same in both final trials): HTML SHA-256
`0cbd4b68a6f1a7c5a57cedda036f82dcd008d7f528d18f8c6adec087d3351719`,
JS `85ca0eaff07c3b344cc7174959741479496fb76f1ac8bb026c8b1396d27f442a`,
CSS `4148073b5f1e55b311684f205e8c2f11c081adff71ae6e635bc36ba293794462`.

## Corrections and preservation

Failed attempts are retained as intermediate results. The initial root CLI import
pulled in FastAPI under system Python; service-only imports were made lazy so the
root client remains standard-library-only. Node's strip-only runner rejected a
parameter property; it was replaced with an ordinary typed field. Browser probes
were corrected to avoid CSP-forbidden string evaluation, install the response
wrapper before the app captured fetch, and wait for `finding_id` rather than a
field also present in old event detail. These were test synchronization failures,
not proof that the browser authorization boundary failed.

A repeat-trial port probe mistook TCP TIME_WAIT for a listener. It now uses normal
address reuse and still refuses an active listener. The first independent process
probe matched its own command text; its failed `independent.json` is retained.
`independent-v2.json` checks executable argv[0] and passes. No failed attempt
changed the production preservation baseline or required an architecture reversal.

The final independent check matched the original baseline: database/main/WAL and
backup hashes, installed artifacts, source prefixes/Audit policy and unit state.
SHM bookkeeping bytes are not claimed immutable; sidecar identity/permissions are
validated. No fresh full database integrity sweep is claimed: unchanged hashes
preserve the previously recorded 357-database healthy inventory. All history units,
listeners and browser processes are stopped; temporary AppArmor permission,
activation config and runtime unit files are removed. Normal HOME/NSS and the
global namespace restriction are unchanged. Private evidence, trial leaf/key,
isolated browser environments and inactive root-owned runtime builds are retained.
No real payload/screenshot was copied to Git, chat or the Mac. No commit or push.

## Remaining scope

This proves the first protected **stored snapshot** only. It does not establish
unattended monitoring, source confirmation/first-run UX, ongoing health/refresh,
search, retention, broad rule coverage, normal-browser setup, certificate renewal/
production lifecycle, packaging, supported Chromium distribution or release
readiness. No CA amendment is approved. Preserve the owner-approved root-only
access, no automatic collection and no logging-policy changes in subsequent work.
