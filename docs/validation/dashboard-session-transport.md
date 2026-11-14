# Dashboard session transport review — November 14, 2026

Owner-authorized continuation of first-build maintenance and Copilot review.
This checkpoint adds repeatable synthetic HTTPS acceptance. No concrete product
code defect was identified and no runtime behavior, timeout, scope, trust policy,
source meaning or stored-data contract was changed. The current `.14` installer
remains the verified artifact; rebuilding it solely for added tests is unnecessary.
[Artifact and prior ownership evidence](source-control-safety.md).

## Independent source review

Copilot reviewed inspected `pilot_sessions.py`, `pilot_app.py`, `dashboard_app.py`
and `dashboard_service.py` for authentication, revocation, expiry, framing and
isolation defects. Job: `hids-copilot-review-e39e4147a2af415aac56fda8d65f158b`.
Normalized packet SHA-256:
`c1b1230302e264b6ac410709de1c541979be4dd60a1fa63ce8ec68f90c6b7967`.
It reported no concrete defect. The auto-selected `gpt-6-luna` used one request,
zero tools and zero model-applied file changes. No runtime data, credentials,
private keys or session tokens were sent. This result does not prove absence of
all defects; the transport checks below supply independent executable evidence.

## Named HTTPS acceptance

`tests/integration/dashboard_session_https.py` now runs in the named
`session_https` phase of `scripts/combined_dashboard_workflow.py`.
Future development builds require that phase in their passed workflow report.
The workflow now has 13 phases. Both workflow and HTTPS test run as an ordinary
Linux user. The test creates a private certificate, key and fixed synthetic shell,
then runs the actual dashboard app under Uvicorn on an ephemeral loopback TLS
listener. Both frozen families are absent; no HIDS configuration or stores are
loaded. The client validates the private test certificate and checks its exact
peer fingerprint. No system/global/browser trust configuration is changed.

A test-only injected monotonic clock advances inside this process; no VM clock is
modified and no HTTP clock-control route exists. Revocation uses the injected
session object's existing method, not a new public control route. Test credentials
stay in memory; reports contain only assertion names/booleans. The test closes its
listener/server thread, revokes all remaining synthetic credentials and retains
new test files under its private 0700 VM directory.

All 13 assertions passed over actual TLS transport:

- Unauthenticated access is denied.
- A forged/duplicate Origin is denied without consuming the valid grant.
- Duplicate Authorization headers are denied.
- A used grant cannot be redeemed again.
- Logout makes the prior session unusable.
- Twenty redemption requests across eight workers produce exactly one success
  and nineteen denials.
- Revocation invalidates both pending grants and existing sessions.
- Grants are denied at the exact 60-second deadline.
- Sessions are denied at the exact 300-second idle deadline.
- Activity cannot extend the 1,800-second absolute deadline.
- A token issued by the separate setup-scope session authority is denied.
- Clock rollback denies the request and permanently revokes the old session.
- The test listener and server thread close.

Source snapshot: `hids-src-20261114T142713Z-9c8036621351`, 433 files.
Manifest: `1a777886d77ab17911f6de9d51e3658b302e9b1013685f9df9cf360d907b72ff`.
VM source:
`/home/ivy/hids-copilot-build.uwa242qg/verified/hids-src-20261114T142713Z-9c8036621351`.
Passed 13-phase report:
`/home/ivy/hids-copilot-build.uwa242qg/session-https-checks/run-20261114T131342Z-617cbbee6191/report.json`.
The same run passed 194 Python unit/regression tests, 24 client tests, TypeScript
and three frontend builds without skips. Detailed synthetic transport report:
`/home/ivy/hids-copilot-build.uwa242qg/session-https-checks/run-20261114T131342Z-617cbbee6191/session-transport/session-https.e22omoo0/report.json`.

## Preservation and limits

Independent root proof: `/opt/hids-session-final.qxqiylww/report.json`.
The original 396-file baseline, installed hashes, Audit policy and preserved source
prefixes still match. Seven source/viewer units are inactive, no process grant
remains, and saved choices are empty at revision 6. A cold immutable read under
the actual database owner still found three events, clean-stopped interval
`[0,1,0,1]`, quick_check `ok` and unchanged store bytes. The existing `.14` artifact's
checksum, 649 regular payload files and exact provenance still passed their audit.
The final proof's `source_manifest` identifies the `.14` artifact snapshot; it also
independently verifies the newer test/workflow snapshot identified above.

These are synthetic sessions, an empty frozen view, test TLS material and a
process-local clock. They do not establish every HTTP parser variant, sustained
load, browser behavior, retained-data rendering or the installed root control
socket path. Prior installed HTTPS/browser/root-control evidence remains separate;
no such broader acceptance is inferred from this test. No running installation,
source activation, Mac system settings/software, commit or push changed. No new
installer was produced. This handoff/evidence documentation follows the immutable
test snapshot and does not alter the existing artifact's source provenance.
