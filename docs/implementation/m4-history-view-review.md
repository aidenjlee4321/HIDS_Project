# First protected M4 history view — owner review D-12c

**Status: owner accepted D-12c in the continuation following the explicit
bounded-trial permission question (November 13, 2026).** Implementation and
acceptance evidence must be recorded separately; approval is not a test result.
The historical review below records the proposal and its earlier findings.

Previously, real-data scope remained proposed. The owner subsequently authorized
fixing the review issues with synthetic data. UI/size guards are implemented and
tested; Firefox rejected peer-only leaf trust. See [fix evidence](../validation/dashboard-security-fixes.md)
and the [no-CA browser/HTTPS integration](../validation/no-ca-browser-comparison.md).
The latter passed with Chromium; the [CA amendment](dashboard-ca-trust-amendment.md)
is optional and unapproved, not the required path forward.

 D-12a/D-12b remain accepted; the
[synthetic session pilot passed](../validation/dashboard-session-pilot.md).
This packet proposes a bounded first view of existing M4 data. No real-data
endpoint, certificate, trust grant or database change is implemented by this review.

## Recommended scope and owner decision

Approve a manually started Linux 2 trial that displays a bounded frozen view of
explicitly selected existing M4 bindings, through HTTPS in a new dedicated
ordinary-user browser environment with direct-leaf trust (Chromium tested; Firefox
peer-only trust failed). Retain the accepted root/sudo authorization step
per session, one-use grant, memory-only bearer, expiry/revocation, Host/Origin
checks, no cookies and no automatic collection. Existing HTTP-only origin/CLI
constants, query-string rejection and hard-coded `pilot:read` issuance must be
extended through closed root-selected settings; changing a URL alone does not
implement this scope. Pilot defaults remain synthetic. The meaningful new permission is
**showing the selected retained security data to that root-authorized browser**.

The profile adds trust for the trial's self-signed server leaf certificate. Its key
is confined to the VM and accessible only to root/designated backend service.
No certificate authority, OS-wide browser trust, existing browser-profile edits,
Mac changes, remote access or certificate-error bypass is included. This is intended
to address the plain-HTTP origin concern; actual TLS/browser verification must pass
before any real-data trial. That synthetic Chromium gate now passed; the real-data
projection/selection contract still needs approval. Normal-profile production
installation and lifecycle UX remain later design work.

One approval covers the fields, budgets, frozen-view behavior and HTTPS trust
boundary below. It does not approve a global ECS schema, broader human access,
unattended deployment, collection/source changes, rules/retention, export, writes,
commits or pushes. Implementation follows only after that approval.

## Evidence used and existing boundaries

Repository evidence:

- `engine/detection/m4_live.py`: fixed M4 destination, live application ID
  `0x48344c31`, distinct live hash domains, no source discovery from an API path.
- `m4_schema.py`/`m4_rule_store.py`: exact v2 five-table schema, frozen binding
  rule plans, event/rule content hashes, atomic stored evaluation/finding linkage.
- `m3_progress.py`/`m3_event.py`: closed native execution contract; exe/comm bytes
  use canonical Base64; nullable auid/session, separate observation/receipt/storage
  timestamps. No argv/environment values exist in this execution contract.
- Existing pilot: 39 component tests, 21 actual Ubuntu integration checks, Firefox
  as UID 1000, backend UID 994 with zero effective capabilities. HTTPS and real-data
  reads were deliberately excluded, so those tests do not establish this scope.

Last independently verified retained state: 357 healthy M3 databases; M4 v2 has
19 events, two bindings, one approved rule, three evaluations and one informational
finding. The original 16 events remain unevaluated and the v1 backup retains them.
This review uses those recorded counts, not newly sampled event payloads or chat
memory as a substitute for source. No recreation is needed.

Read-only VM tool inventory this session: Python-linked SQLite 3.46.1,
OpenSSL 3.5.5, existing Firefox; `openssl` exists and `certutil` is absent. A version
string is not a package-patch/security assessment. Record actual package/build
provenance before acceptance; do not silently upgrade installed M3 dependencies.

## HTTPS and browser trust

Use a root-created listener at exactly `https://127.0.0.1:18765`. Reject occupied
port, plaintext HTTP, foreign Host/Origin, proxy authority and alternate addresses;
no HTTP redirect listener or fallback transport. Retain systemd ownership/reservation
of the named listener and root-only Unix control directory/socket.

Provision one self-signed **leaf**, SAN IP `127.0.0.1`, server-auth usage and
CA=false, using the existing VM OpenSSL. Generate a fresh private key, never print
it, store it at a fixed root-managed path in a root-owned 0750 directory whose
only service traversal group is the existing backend primary group. Key ownership
root:backend, mode 0440; no new groups/account or ordinary-user key access. The
unprivileged TLS server may read the key; root/service compromise remains outside
the confidentiality claim. Public certificate/fingerprint are not session secrets.
Pin its SHA-256 fingerprint in root configuration. Use a seven-day trial certificate;
not-yet-valid/expired certificate, fingerprint/key mismatch, unsafe key permissions
or missing key refuses startup. Validate SAN, server-auth usage and CA=false
explicitly: loading a TLS key/certificate alone is not that validation. Require
remaining validity beyond the ten-minute trial and recheck validity before minting.
No automatic renewal/trust update.

For the private Chromium test build, the proposed trial reuses the proven temporary
AppArmor permission for its exact root-owned binary so its own sandbox can run.
Remove that permission afterward; preserve the global namespace restriction and
normal-user NSS inventory. No wildcard allowlist, setuid helper, insecure flags or
permanent installation policy is included. [Measured comparison scope](../validation/no-ca-browser-comparison.md).

Trust the exact public leaf as an SSL peer in a new isolated environment for an
explicitly compatible browser, running as the already authorized ordinary account.
Chromium is tested. Its Linux NSS trust database is shared by HOME, so use a new
private HOME/XDG paths **and** user-data directory; a profile directory alone is
insufficient. Preserve the normal HOME/NSS inventory. Root-controlled provisioning
selects the certificate; the browser runs unprivileged. Use Ubuntu NSS tooling
as needed in the VM and record its source/version. Do not modify system trust or
existing profiles. Leaf import is an additional trust entry, not exclusive browser
pinning: normal built-in browser trust may still exist. The server-side fingerprint
check pins what the service loads, not every certificate the browser might accept.
Inventory the actual profile trust/configuration in evidence; do not claim a
leaf-only trust store or alter built-in trust implicitly. Successful certificate
verification must be proven with
certificate-error bypass disabled (`ignore_https_errors=False` in the tested
Chromium harness; `acceptInsecureCerts=false` for Firefox), including rejection
of an untrusted replacement, wrong hostname and trusted-but-expired leaf. If exact leaf trust is unsupported, report the evidence; do not
substitute a CA or disable verification without review. TLS 1.2 minimum, modern
library defaults, no custom cryptography. Certificate/key creation and trial
activation are separate from starting any collector.

The root CLI obtains links through the protected local socket and emits only the
fixed configured HTTPS origin. The ready check includes successful TLS setup and
certificate/config validation. New `history:read` sessions are confined to this
view. The synthetic mode's `pilot:read` credential cannot authorize history routes;
request bodies cannot request or change scope. Retain 60-second one-use grants,
300-second idle/1,800-second absolute expiry and four combined grants/sessions.

This is still an entrusted ordinary browser/account. Extensions, XSS, debugger/
memory access or same-account malware can use an authorized session or displayed
data. The new profile reduces origin baggage; it is not isolation from its owner.
Verified HTTPS rejects an impostor with an untrusted replacement certificate;
prove that rejection in the actual profile. Do not claim exclusive fingerprint
pinning or protection from compromised trust authorities/browser/backend/root.

Primary references: [Python TLS contexts](https://docs.python.org/3.14/library/ssl.html),
[NSS certificate trust operations](https://nss-crypto.org/reference/security/nss/legacy/tools/nss_tools_certutil/index.html).
These support the design, not a claim that leaf trust has already passed Firefox.

## Frozen read-only view, not a live database session

Root configuration selects the fixed `/var/lib/hids/m4/store/handoff.sqlite`,
its expected device/inode and one or two exact existing binding keys. The path is
not an HTTP/CLI argument. Configuration has a new closed version/mode, fixed TLS
paths/fingerprint and explicit bindings; missing/unknown fields refuse. Scope
selection is authorization to read retained HIDS history, not new OS collection.

Keep the existing unprivileged backend identity and zero-capability restrictions.
Map only the store directory read-only; hide M3 state/runtime, M4 backups and
other sensitive HIDS state. Sharing a UID with the writer does not provide strong
isolation against a fully compromised same-UID process; this review adds no account
split or broader permission grant.

Before enabling history grants, load one finite view inside a short SQLite read
transaction using URI `mode=ro`, query-only and trusted-schema-off settings.
Validate canonical paths/owner/modes/file identity, live application ID, exact v2
schema and selected binding identities. Use existing valid WAL/SHM when required;
never instantiate the existing writer-opening `LiveStore`/`RuleStore` constructors,
create missing state or sidecars, set immutable, checkpoint, repair, migrate,
change journal mode or acquire the writer's lock. Missing/unsafe input produces
unavailable state. WAL-sensitive reads must not copy the main DB alone.
[SQLite read-only/WAL requirements](https://www.sqlite.org/wal.html#read_only_databases)
and [URI semantics](https://www.sqlite.org/uri.html) explain these constraints.

Load at most **128 events, 128 evaluations, 32 findings, one rule and two bindings**;
read cap-plus-one to detect overflow and refuse the whole view rather than silently
truncate. Validate selected row relationships, canonical envelopes/hash domains,
rule hashes/plans and finding-to-matched-evaluation linkage. Refuse contradictions
or unsupported schema/rule content. Do not run detection, repair a result or
re-evaluate the original 16 events. Unselected binding data is not serialized.
Use fixed parameterized SQL only, no caller SQL/table/path or arbitrary filter.

Bound canonical ASCII envelopes/definitions at 16 KiB **before fetching/decoding
full values**: use bounded SQL projections/length checks, reject noncanonical or
over-limit rows, and cap text in explanations, reasons, plans and metadata too.
A row-count limit alone does not bound a SQLite cell or Python allocation. Bound
the canonical serialized view at four MiB; that is not a four-MiB Python heap/RSS
guarantee. Preserve the service MemoryMax=256M/TasksMax=32 limits and measure
actual peak usage in the synthetic acceptance. SQLite busy timeout
50 ms, progress checks and a two-second cooperative overall loader budget, with
no retry loop. This is not a hard deadline for blocked kernel I/O; the trial has
an external ten-minute supervisor. Close the transaction/connection before serving
any history route. Refuse oversized/malformed data instead of opening a partial view.

The browser subsequently reads only that frozen memory view. It never holds a
SQLite connection/transaction open. There is no automatic refresh or silent live
update: a newly root-configured restart and new session loads a new view. Label
it **stored snapshot**, with `view_loaded_at` as preparation time, not activity time
or a guarantee of current monitoring. No source health/coverage verdict follows
from stored rows. A missing initial store must not appear as an empty healthy view;
locked static UI and root revoke remain available, but new history grants refuse.

These caps are provisional bounded-trial choices, not release throughput/resource
thresholds, retention policy or a finalized production API design.

## Closed response contract and pagination

Response format `hids.m4.history-view/1`, separate from the native envelope/ECS.
All history routes independently require `history:read`; unauthorized requests
receive a generic denial before metadata, cursor or record serialization.
No unauthenticated host/status/DB errors. Keep the pilot's no-store, CSP/text-only
rendering, no-referrer, bounded headers/bodies/concurrency and credential redaction.
No route changes SQLite or source state.

Before exposing real data, fix the existing pilot UI's stale-response behavior:
an in-flight access check can complete after logout and restore its message while
status remains Locked. This was reproduced from the current exact function source
with synthetic deferred promises; it is not a claim of backend authorization bypass
or real-data leakage from the current synthetic-only endpoint. Use a monotonically
increasing client authorization generation, abort prior requests where possible,
and ignore stale successes **and failures**. Logout/expiry/new authorization must
invalidate the generation and clear all event/finding/detail state immediately;
pending old responses cannot restore tokens, change a new session or populate any
locked/error presentation. Retain a captured credential only for the logout request,
then discard it. Client request abort alone is not sufficient.

The current five-minute client display timer also does not reset after a successful
access check even though the backend idle timer does. Define presentation timing
from accepted current-generation responses, retain the absolute cap and clear
sensitive UI on denial/expiry; do not introduce background keepalive. Test delayed,
reordered and overlapping requests across logout, expiry and reauthorization.
Backend deadlines/revocation remain authoritative; clearing UI cannot revoke
already copied data or promise protection from a compromised browser.

Closed endpoints:

| Endpoint | Returned fields |
|---|---|
| `GET /v0/history` | Format, random per-start view ID, `view_loaded_at`, `history_only=true`, `monitoring_status=not_assessed`, selected counts and explicit snapshot limits |
| `GET /v0/history/events` | Up to 20 items: event ID, import time, exe escaped preview (256 characters plus explicit truncation flag), pid/ppid, uid/euid, success/result and stored evaluation-state summary; next cursor or null |
| `GET /v0/history/events/{id}` | Selected event ID/content hash, binding/scope source/activation/generation, native identity/offset, full existing closed execution object and observation/receipt/persistence/import metadata, plus stored rule evaluation references/state/reason/time |
| `GET /v0/history/findings` | Up to 20 informational, non-demo findings: ID, creation time, triggering event ID, rule ID/revision/hash, bounded stored explanation and matched values; next cursor or null |
| `GET /v0/history/findings/{id}` | Same finding provenance plus exact approved rule definition/conditions and limitations, linked to its one triggering event |

No raw Audit logs, argv/environment, backend filesystem paths, arbitrary file
reads, exports/downloads, free-text search, source/settings controls or SSE in this
first slice. The existing stored execution fields are the complete detail allowlist;
new JSON keys do not become public automatically. Native exe/comm Base64 remains
available in authenticated technical detail to preserve exact bytes; escaped
previews are display aids. Render all native strings as text, including control/
bidirectional/invalid-byte representations; no HTML interpretation or silent
normalization. Missing nullable values remain null with explicit absence labels.

Encode every non-null nanosecond timestamp, 64-bit offset and execution result as
a decimal string **consistently**, including zero; do not vary JSON types by magnitude.
Preserve null for an absent timestamp. These lossless wire types are explicit API
projections of native fields, not the native object copied verbatim; uint32 PIDs/UIDs
and Booleans remain their native types. Do not reinterpret Audit IDs as trusted
activity timestamps, substitute import/observation time or finalize global ECS
mappings. Show imported/observed labels explicitly.

Events sort by stored `imported_at` then event ID descending; findings by stored
creation time then finding ID descending. This is a deterministic snapshot order,
not execution chronology or a finalized release alert-feed clock. Every supported
finding currently has severity informational; do not invent other bands.

Lists accept only an optional opaque `cursor` (maximum 512 bytes), at most 20
items per page; no offset/limit/search parameters. Deterministic byte packing may
return fewer items to keep the response within 64 KiB, with a next cursor when needed. The cursor is authenticated with a fresh
per-process HMAC key, binding view ID, route, next position and session-token digest.
It confers no access without that session. Wrong view/session/route, malformed,
forged or out-of-range cursors refuse; restart/logout/expiry invalidates access.
No raw token/scope/record payload goes in a cursor. Pages are stable because the
view is frozen. Bound each JSON response at 64 KiB; detail bodies 32 KiB, explanation
4 KiB, preview 256 characters. Refuse over-budget input, not a partial explanation.

An event is **unevaluated** only when its frozen plan and absent evaluations support
that fact. Preserve pending/matched/no_match/unable/error as distinct stored
outcomes; missing expected rows are invalid, not no_match. The finding still means
only the approved dash/euid-0/success condition matched. Preserve benign explanations,
unavailable Audit login attribution and no claim of maliciousness/confidence.

## Implementation and acceptance after approval

1. Keep the synthetic pilot as a regression. Implement the frozen view adapter,
   explicit history scope and TLS in the accepted FastAPI/React stack; add no new
   runtime framework. Build from verified snapshots/private VM environments.
2. Use synthetic stores first: strict schema/identity/hash/plan/linkage/size tests;
   missing WAL/SHM, writer contention/loader interruption, replaced/symlink files,
   invalid/missing store, unselected bindings and snapshot stability after later
   commits. Prove source/main/WAL/backup preservation, no sidecar creation and
   no lingering SQLite reader. Do not require SHM lock bookkeeping bytes to stay
   identical during a concurrent-writer fixture; retain its identity/permissions.
3. Exercise actual TLS verification, foreign/expired certificate, wrong IP, plaintext
   connection and stopped-port impostor rejection in the explicitly compatible
   browser, with sandboxing and certificate errors disallowed. Do not use `verify=False` or insecure browser capabilities
   to obtain a pass. Verify ordinary-user key-file denial and actual backend access.
4. Test scopes/cursors/replay/restart/expiry/denial and hostile-text rendering across
   every new endpoint, including delayed responses arriving after logout/expiry
   or during new authorization. Prove old unevaluated events stay unevaluated; no source,
   detection, write/export or unprotected debug route appears.
5. Only after those pass, run a root-selected, at-most-ten-minute real Linux 2 trial,
   with collectors/M4 worker stopped. Select the two existing bindings explicitly;
   compare projected rows/counts/finding linkage with protected ground truth and
   view them in the isolated ordinary-user browser environment. Keep payload-bearing reports/
   screenshots private in the VM; no real history artifact in Git/chat/Mac outputs.
6. Recheck baseline DB/WAL/backups/artifact/source-prefix/Audit preservation, then
   stop the view, invalidate sessions and remove only this trial's activation/config.
   Retain private evidence and trial key/certificate/profile securely; no existing
   history/profile deletion. Report exact scopes/limits and any unresolved failure.

A pass establishes this first protected stored-history view only. Search, ongoing
refresh, full first-run UI, health monitoring, production certificate lifecycle,
normal-browser setup, unattended service, packaging and release gates remain open.

## Double-check findings

Review completed against current source, accepted constraints and private evidence.
Existing acceptance still reports all 21 checks passed, and a fresh read-only check
matched the original file/policy/artifact/source-prefix baseline. All three pilot
units are inactive, their config is absent and port 18765 has no listener. The
retained independent report still records 357 healthy M3 databases, M4 19 events /
three evaluations / one finding and the 16-event backup. No integrity checks were
rerun or substituted for that recorded result; current preservation was rechecked.

Confirmed UI race reproduction: exact current frontend SHA-256
`0a0dba5fc6affb5d7fa76c5b89685251e835a35267143bcfb8a85e47f528f87c`;
private report `/home/ivy/hids-dashboard-build.zpoci9uz/review-ui-race.json`.
The harness extracted the actual checkAccess/logout functions and controlled their
promise completion order: logout cleared state, then a late success restored the
synthetic message with status Locked and bearer still cleared. This is a function-
level scheduling reproduction, not a new full-browser test or an implemented fix.
The locked branch currently renders that message, so the issue must be fixed before
those functions are used for sensitive history. The previous browser suite did not
exercise this overlap; its pass remains valid for its narrower recorded scope.

Corrections above distinguish added leaf trust from exclusive pinning, require
explicit certificate validation, bounded database-field reads and a serialized-size
budget separate from process memory, consistent 64-bit wire types, a read-only
adapter rather than writer constructors, and client stale-response/timer gates.
HTTPS trust and history scopes remain unimplemented and unapproved. No certificates,
profile changes, new service activations, software installs, commits or pushes were
performed during this double-check. Recommendation: retain the design direction,
with these gates resolved before any real-data acceptance is claimed.


Subsequent browser comparison preserved the no-CA direction: 15 browser/TLS/
synthetic-dashboard checks passed in Chromium, with protected root control,
unprivileged backend, no verification/sandbox bypass and complete temporary-policy
cleanup. [Exact versions, failed attempts and constraints](../validation/no-ca-browser-comparison.md).
This is compatible-browser evidence, not approval of this real-data scope or a
requirement to bundle Chromium in the product.


## Accepted implementation outcome

The owner accepted this bounded contract in the continuation following the
explicit approval question. The implementation then passed synthetic gates,
real selected-history HTTPS/browser/ground-truth checks and independent cleanup.
[Executed evidence](../validation/m4-history-view-acceptance.md) supersedes the
historical unimplemented/unapproved wording above. Collection stayed stopped;
CA trust and broader deployment remain unapproved. This contract is a trial
surface, not approval of a global event schema or complete dashboard.
