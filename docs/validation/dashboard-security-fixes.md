# Dashboard review fixes — implemented scope and TLS blocker

The owner requested fixes to the confirmed UI race, TLS trust assumptions and
pre-load size guards. This work fixes/testing those boundaries with **synthetic
data only**. No real-data endpoint or collection/source change is authorized by
this record. D-12a/D-12b remain accepted; D-12c real history remains proposed.

## Implemented fixes

`frontend/src/session_client.ts` now owns volatile client state. Each authorization
has a generation; stale successes and failures cannot update another generation.
Logout clears credentials and all displayed content immediately, aborts prior
requests and uses its captured old credential only for best-effort server logout.
An old logout result cannot affect a new session. Successful current activity
renews the presentation idle timer; the absolute cap remains binding. Server-side
expiry/revocation remains independently authoritative. No persistent tokens or
background keepalive were added. The locked page never renders the data-message
field. The React page uses the tested controller rather than separate async setters.

Nine deterministic TypeScript tests cover late success after logout, old failure
and success during new authorization, overlapping redemptions, expiry during an
in-flight request, idle renewal, absolute cap, late logout and current denial.
The fake transport deliberately ignores abort, so generation checks are necessary.
These tests execute the actual controller, not a copy of its logic.

Actual Firefox additionally delays a fully buffered API response until after
logout, then releases a new Response independent of the original request's abort.
The record stays hidden and status remains Locked. Test interception is installed
before application startup through WebDriver BiDi, keeping the application's
captured transport intact. The first new browser attempt timed out because its
late-installed interception could not affect that captured transport; its failed
report `/var/tmp/hids-dashboard-acceptance.zs2yrc0_/report.json` is retained.

`api/history_bounds.py` is a resource-guard library, **not a complete authorized
history adapter or endpoint**. It opens no files. Its dedicated SQLite connection
uses fixed internal table/field policies, root-selected binding parameters, query-
only/trusted-schema-off settings, a short read transaction and cooperative deadline.
SQL projects field type/byte-length and bounded BLOB substrings before Python
receives values. Wrong types, invalid UTF-8, oversized cells, row overflow, missing
bindings, invalid plans and serialized aggregate overflow refuse the whole result.
It materializes no unselected event/evaluation/finding rows and selects rule rows
from the selected plans. Transactions/cursors close before return. Schema/hash/
provenance validation and safe public projection are still required before future
real-data integration; do not expose this library's internal dictionaries directly.

Twelve bounds tests pass, including a one-million-byte cell: the Python row
factory sees at most 16,385 bytes for that cell before rejection. UTF-8 limits are
bytes; a four-MiB serialized cap is not a Python heap/RSS promise. Existing service
MemoryMax=256M/TasksMax=32 are unchanged. No live history store was exercised by
these tests; fixtures use SQLite memory databases.

## Settled-source evidence

Snapshot `hids-src-20261113T050953Z-b9d91d33ea9a`, manifest
`7faa043ae2ecab52676eabe2604ba79d587a6599145d7a4714a1adf6a0df6203`.
The frontend was type-checked/built from identical sources in the private VM
workspace. UI production bundle remains synthetic-only.

Private checkpoint report:
`/home/ivy/hids-dashboard-build.zpoci9uz/security-fix-results/run-20261113T004408Z-7137aed884d8/report.json`.
All six phases passed: nine frontend race/timer tests (Node count in its phase log),
12 bounds tests, 39 API/session/client tests, 96 M4, 87 M3 and 41 workflow tests.
The verified source manifest was checked before/after the checkpoint. No skipped
phase. Node's test count is not parsed by the existing Python report counter;
its nine successes are visible in the retained Node output.

Full synthetic pilot report:
`/var/tmp/hids-dashboard-acceptance.ufbw6nw2/report.json`.
It passed all 21 integration checks, including the actual browser race, existing
refresh/reauthorization/revoke/restart paths, one-minute grant and five-minute idle
expiry, production preservation, credential-log checks and pilot cleanup. The
10 browser actions include `race_logout`. Neither this pass nor the original
pilot constitutes HTTPS acceptance or real-data access.

## TLS checks implemented and exercised

`api/tls_leaf.py` validates canonical root-controlled paths/ancestors, restrictive
leaf-key permissions and backend group, bounded independent regular files,
certificate fingerprint, CA=false, exact loopback SAN, server-auth usage, current
validity/remaining trial lifetime and seven-day maximum certificate lifetime.
OpenSSL verifies the leaf's signature/purpose/IP; Python's server context requires
TLS 1.2 minimum and matching key/certificate. Loading a key is not treated as
sufficient certificate validation. This helper changes no trust store and is not
connected to a history service.

Synthetic root/backend trial report:
`/opt/hids-tls-synthetic.8m5rf1fp/report.json`, using snapshot
`hids-src-20261113T050518Z-83f6950acf5d`/manifest
`b3513c3672058095a6c1bc517a8d4cc149f6e4fc8afd61a3c279464a552b9076`.
Ten checks passed: valid context, wrong fingerprint/key mismatch/expired leaf/
unsafe key refusal, ordinary-user key denial, verified Python TLS, foreign-leaf
and wrong-name rejection and plaintext not serving data. The listener actually
ran as UID 994/GID 971, loading a root-owned 0440 leaf key. Private fixture certs
and keys remain under `/opt`; no key or real payload is copied to Mac/Git.

The full TLS trial correctly **failed at Firefox acceptance**. In fresh Firefox
154.0, peer-only `P,,` trust did not accept the valid CA=false leaf with
`acceptInsecureCerts=false`. Follow-up report:
`/home/ivy/hids-dashboard-build.zpoci9uz/tls-diagnostic.xky1jj5f/report.json`.
It confirms the certificate's peer trust entry in the **actual running browser
profile**, verification enabled, and a certificate-error document instead of the
synthetic page. This rules out merely importing into the wrong pre-copy profile.
Browser positive acceptance and subsequent browser negatives are not claimed passed.

Mozilla's [verifier source uses CA trust for trust anchors](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/security/certverifier/NSSCertDBTrustDomain.cpp);
[NSS defines peer/CA flags separately](https://nss-crypto.org/reference/security/nss/legacy/tools/nss_tools_certutil/index.html).
This corroborates the observed behavior; current upstream source is not claimed
to match the exact installed Firefox binary. Native Python/OpenSSL success was
not substituted for browser success. Certificate-error overrides, insecure flags,
CA trust and plaintext fallback were not used.

The matching Ubuntu NSS utility package `2:3.120-1ubuntu2.2` was downloaded and
extracted privately at
`/home/ivy/hids-dashboard-build.zpoci9uz/fix-tools.r3m524_g`.
No package was installed; no existing profile, OS trust store or Mac setting was
changed. Newly created synthetic-only Firefox profiles have the test peer entry
and are retained. Synthetic TLS servers were stopped, including the diagnostic.

## Remaining owner decision

A successful Firefox HTTPS path requires replacing the proposed leaf-only trust
choice. The [concrete profile-local CA amendment](../implementation/dashboard-ca-trust-amendment.md)
keeps its signing key root-only, gives the backend only a separate leaf key and
adds CA trust only to a new dedicated ordinary-user profile. It explicitly admits
the broader signing authority inside that profile. This is a fundamental trust
change, so it has not been performed under general VM maintenance permission.

Existing history remains closed. Future implementation must still provide the
complete read-only validator/projection/cursor contract and HTTPS integration,
then pass synthetic gates before any separately approved real-data trial. No
commits/pushes or default enablement were performed.


## Subsequent no-CA result

The owner asked why Firefox was required, then authorized comparing alternatives.
The [Chromium comparison and synthetic HTTPS integration](no-ca-browser-comparison.md)
passed with direct leaf trust and sandboxing. The earlier Firefox failure remains
valid for that browser/method, but no longer blocks the no-CA direction. The CA
amendment is optional/unapproved; real history remains closed pending D-12c.
