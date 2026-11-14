# Dashboard session pilot — Ubuntu acceptance

**Scope:** owner-approved D-12a/D-12b, synthetic-only authorization pilot.
This is not real security-data API access, a completed dashboard/M4 milestone,
unattended operation or release acceptance. [Accepted mechanism](../implementation/dashboard-session-mechanism-review.md).

## Executed source and private evidence

Final accepted source snapshot: `hids-src-20261113T042014Z-ef40a1711175`.
Manifest SHA-256: `39d811653f7a3a3d2fce93bb7e50fce166adc4ea71d4e785669d43f9ddedf083`.
Report on Linux 2: `/var/tmp/hids-dashboard-acceptance.4e_4n__z/report.json`.
Guest UUID: `46330e53-4a53-4a94-b9d4-0adefd192ab7`.
Private build: `/home/ivy/hids-dashboard-build.zpoci9uz`.
No real event store is imported by the API; its namespace hides `/var/lib/hids`
and the M3 runtime socket path. Original M3/M4 units remain inactive.

The report records a passed bounded acceptance, 21 checks, successful ordinary-user
Firefox flows, production preservation, stopped pilot and no sampled credentials
in the pilot unit journal. Private screenshots/logs are retained under the build
and report directories. They contain synthetic data only. The final screenshot was
also visually checked: readable layout, separate access/logout controls and the
hostile example displayed literally.

## What passed

- 39 dashboard component tests on Ubuntu: 19 session, 13 ASGI/HTTP and seven
  client-boundary tests. Exact real credential/mode behavior is covered separately
  by the Ubuntu harness; mocked Mac client tests are not Linux peer-credential
  evidence. Session cases include simultaneous one-use redemption, combined
  four-entry capacity, random failure/collision, strict token/JSON parsing,
  logout/revoke/restart, scope, clock rollback and idle/absolute boundaries.
- Root terminal authorization; piped CLI output refuses. Root-owned socket
  directory 0700/socket 0600; ordinary UID 1000 cannot connect. A separate,
  deliberately permissive synthetic test listener rejects that actual non-root
  peer before accepting an operation, independently proving the server UID gate.
- Actual backend UID 994 with zero effective capabilities and no-new-privileges;
  production data paths hidden. The client accepts only root or the NSS-resolved
  designated backend at the root-protected pathname. Unknown operations, fields,
  versions, extra frames, oversized/control slow requests and slow HTTP bodies
  refuse. Occupied port refuses startup without selecting another port.
- Real loopback HTTP refuses absent bearers, cookies used as authority, foreign
  origins, duplicate security headers and proxy authority. Duplicate Host can
  receive h11's early 400; application authorization negatives receive 403.
  Real-data routes remain absent. Protected success returns only the fixed
  synthetic record.
- Fresh headless Firefox 154.0 as ordinary UID 1000: link redemption, fragment
  removal, empty cookies/localStorage/sessionStorage, clean observed resource
  URLs, literal hostile text/no injected image or script, refresh locking,
  same-tab root-link reauthorization, logout, root revoke plus access recheck,
  restart invalidation and fresh post-restart authorization.
- Actual 60-second grant expiry and 300-second idle expiry. The absolute
  1,800-second bound is verified using an injected monotonic clock in component
  tests, not a claimed 30-minute real wait. Browser-close server invalidation is
  not guaranteed; loss of client memory and server timeouts remain distinct.
- Runtime/backup/source-prefix/config/Audit and installed-artifact preservation.
  Pilot startup opens no SQLite store, starts no source and enables no rule.
  Temporary pilot units/config are removed; tested `/opt` runtime and earlier
  pilot asset bundles are retained inactive. No commit/push performed.

An additional post-run check is retained as adjacent `independent.json`: all
357 M3 databases passed quick_check; real M4 integrity/foreign keys passed with
19 events, one rule, three evaluations, one finding and two bindings. The v1
backup still has 16 events. Original installed hashes, Audit policy, source
prefixes and state hashes matched the run baseline again. Temporary config/unit
files and the loopback listener were absent. SQLite checks ran as the designated
backend identity rather than creating root-owned database sidecars.

## Build and regression evidence

Minimal service closure: 14 packages, separate from the automation environment.
FastAPI 0.162.5/Uvicorn 0.54.0, pinned in `api/requirements-pilot.txt`.
Publisher PyPI vulnerability metadata reported none for those pinned runtime
releases; available license metadata is retained privately. This is not a complete
security audit or ongoing vulnerability guarantee. Automation is separately pinned
in `api/requirements-pilot-test.txt`.

Private Node 26.13.1 AArch64 archive SHA-256:
`89e1853138db51e8b82d3e98ba9c0d3f2956a28e5e55ea1b7e12d25aae92d5dd`,
matched the publisher's SHASUMS file. Private geckodriver 0.37.1 SHA-256:
`8fd90b951422fbad5b56539fb344dff66eb3f986d615d8d6fde9f1f62dad610c`,
matched the release asset's publisher digest. Neither was installed globally.
Firefox was already installed. No Mac software/settings change was needed.

React/React DOM 19.3.1, TypeScript 7.0.2, Vite 8.3.8 and corresponding type packages
are pinned in `frontend/package.json`/`package-lock.json`. Clean `npm ci
--ignore-scripts`, type checking and production build passed; npm audit reported
zero known advisories for that resolved graph at execution. Hashes of the actual
bundled assets are in the final acceptance report. Rebuilding an unchanged
package graph does not imply a new vulnerability assessment.

The existing workflow also passed 96 M4 tests, 87 M3 regressions and the demo:
`/home/ivy/hids-dashboard-build.zpoci9uz/regression-results/run-20261112T232611Z-24f06ae43022/report.json`.
That run used the earlier snapshot
`hids-src-20261113T035903Z-bce5a7a3d92b`/manifest
`708024922199456284c2c9023b46864bd397ac17c46ff2af9437abc50b614cf5`;
subsequent fixes affected only the new pilot/UI/acceptance code. All 41 development
workflow tests passed on Ubuntu and Mac, including frontend snapshot completeness.
Guest clock timestamps differ from host timestamps; snapshot/report names are
identifiers, not measurements of product event-time accuracy. Expiry uses
monotonic time.

## Failures retained and corrected

These are intermediate failures, not passes or product readiness evidence:

- `/var/tmp/hids-dashboard-acceptance.m7nt66_t/report.json`: Python's default
  Unix-socket cleanup attempted to stat the root-only pathname. Set
  `cleanup_socket=False` for the inherited listener; systemd retains pathname
  ownership. [Python's cleanup contract](https://docs.python.org/3.14/library/asyncio-stream.html#asyncio.start_unix_server).
- `...51go2f9d/report.json`: a later root CLI connection saw the designated
  backend after asyncio relistened rather than the root listener creator.
  Client validation now permits exactly those two trusted server identities,
  together with protected-path checks; human eligibility/server client UID 0
  checks did not broaden. This early harness left its result as `running` after
  the terminal assertion even though it exited; later reports explicitly mark
  exceptions failed. Its original report is retained unchanged.
- `...b1_fx0lo/report.json`: acceptance helper shadowed the imported HTTP module;
  corrected the helper import. `...03t2epkt/report.json`: valid early duplicate-Host
  400 rejection was incorrectly expected to be 403; corrected only that assertion.
- `...__mx6lxp/report.json` and `...nclrqj1t/report.json`: Snap Firefox needs an
  ordinary-user scope and a live user-session bus. The final run keeps the SSH
  login alive and uses that user's scope; no linger/account change or root browser.
- `...30msilaf/report.json`: first authorization/refresh passed, but a second
  root link was only a fragment navigation and did not restart authorization.
  New explicit root links now reload the document. `...t8_jumpu/report.json`:
  Selenium retained a stale element during that intentional reload; use an atomic
  document/status/fragment predicate and show pending authorization truthfully.
- Initial TypeScript build required the Vite client declarations for the CSS
  import; fixed before acceptance. The mock-only CLI tests initially assumed a
  Linux socket constant existed on the Mac; their fake socket now supplies it,
  without adding a production fallback or claiming Mac runtime support.

All referenced acceptance attempts independently reported existing production
files/policy preserved. They are retained privately; no old event, backup or
failed report was deleted to obtain a pass.

## Remaining boundaries

An authorized browser/account and the backend remain trusted. XSS/extensions,
same-account malware, clipboard/terminal/memory access and stopped-port/origin
reuse remain relevant. Loopback HTTP is not authenticated TLS. This pilot uses a
clean test profile and grants synthetic read scope only; production origin trust
and the exact read-only M4 data/query/cursor/budget contract still require review
before real-data exposure. No background stream, download/export, source control,
permanent grant, wider human access, package installer or release claim follows.

See [API build/run guide](../../api/README.md). Future work should reuse the
verified snapshot/private-report workflow and preserve these scoped limits.
