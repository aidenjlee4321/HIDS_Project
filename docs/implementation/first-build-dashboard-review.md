# First installable build: protected dashboard and access lifecycle

Status: owner authorized continuation after the concrete P-01–P-04 review request
(November 13, 2026; response: “continue”). Implementation/acceptance follows;
approval is not a validation result. The approved process pipeline explicitly
reserved wider HTTP fields/routes and production access/certificate lifecycle for
this review. The packet itself authorized no activation. The bounded implementation and retained-data
trial subsequently passed; see [evidence and remaining gates](../validation/combined-dashboard-acceptance.md).
Existing D-12a/b/c, D-14a and C-01–04 approvals remain valid.

## Recommendation

Approve a bounded, root-authorized dashboard preview over the **already approved
stored fields** from the process pipeline and the existing selected M4 history.
Use the tested local HTTPS/direct-leaf Chromium approach, explicit root launch and
fresh volatile sessions. Then assemble a local Debian development package, verify
its install/start/stop/restart behavior and reassess before extras. This is an
installable development build target, not a waiver of open v0.1/release criteria.

This proposal changes the authenticated presentation scope and specifies its TLS
and launch lifecycle. It does not add kernel fields, enrichment, journal/log read
grants, detections, remediation, external network exposure, automatic collection,
automatic data deletion, a CA, Mac system changes or Git publication.

## P-01: one new closed read scope

Add a fixed `dashboard:read` session scope to the new dashboard mode. Root selects
its finite data families/scopes in root-owned configuration; the browser cannot
supply paths, SQL, field sets, source IDs or activation IDs. Existing pilot,
history:read and setup:draft tokens keep their current meaning and do not acquire
new access. Every new route independently requires dashboard:read; no token is
accepted based on mere existence or membership in a human group.

Preserve the implemented root/sudo-only authorization, 60-second one-use bootstrap,
four-grant/session cap, five-minute idle and 30-minute absolute expiry, memory-only
bearers, logout/revocation, restart revocation, secret-free access logging and
Host/Origin/content-type/body limits. No cookie or persistent browser login.
Session creation and source collection remain separate; HTTP cannot start/stop a
collector, save confirmed source choices, install code or change logging policy.
Root CLI remains necessary for source confirmation/start/stop under D-14a.

## P-02: exact view and routes

At explicit root launch, load a **finite frozen snapshot** of the selected stored
data. Close all SQLite connections before serving requests. Show its capture time,
truncation and source limitations; opening the view is not proof of current
monitoring, and it does not refresh silently. The root launcher can explicitly
replace the view/reopen the dashboard for newer records, revoking old sessions.
Live SSE, unrestricted queries and arbitrary search/export remain later work.

| Route | Allowed result |
|---|---|
| GET `/v0/dashboard` | Snapshot time, per-family availability/caps, ordinary event/finding counts, historical interval flags and explicit current-monitoring-not-assessed status |
| GET `/v0/process/events` | At most 20 stored process summaries per page, using only an authenticated opaque cursor |
| GET `/v0/process/events/{event_id}` | One validated retained process record from the selected snapshot |
| GET `/v0/history` and existing selected-history list/detail paths | The existing D-12c M4 projection and meaning, under the new closed dashboard mode; the legacy history service remains unchanged |

Reuse the existing authentication endpoints for redemption/logout and fixed static
assets. No additional write, control, filesystem, shell, SQL or export route.
Malformed/unselected/absent IDs return a generic unavailable response after auth.

For process records expose only C-02 fields: event/producer/source/activation/boot
IDs, profile/version, native kind/code, TID/TGID/optional parent, CPU/sequence,
lossless raw monotonic decimal string, raw exit status/signal, explicit absent
activity wall time, observation/receipt UTC, backend arrival ordinal and their
validated normalized subset. Summaries show kind, PID/TID, observation time and
unknown activity-time indicator; technical provenance belongs in details.
Do not infer executable/user identity, process entity IDs, whole-process termination
from a thread exit, or maliciousness. No arguments/environment/raw datagrams exist.

Historical interval details may show the approved ACK/delivery/incomplete/stopped
flags, bounded reason and 20 saturating typed diagnostic counts. Label them as
interval evidence, not a live health guarantee. Sequence diagnostics are not lost
event counts. No ignored/unrelated process payload is added to the view.

Keep exact old M4 binding/event/rule/finding fields and root-selected two-binding
maximum. Do not re-evaluate the old 16 events or activate a rule. Ordinary process
records belong in Activity; they do not become security alerts merely by existing.
The existing informational finding keeps its source/rule limitations and does not
become a supported cn_proc detection. An absent source/finding is not a clean bill
of health.

Bounds: at most 128 process events and 128 process interval rows, at most two
root-selected process activations, and existing D-12c caps for M4 (128 events,
128 evaluations, 32 findings, one rule, two bindings). Maximum 8 MiB serialized
combined frozen data, 64 KiB response, 32 KiB detail, 20 items/page, 50 ms DB busy
wait and two-second cooperative loader budget per family. Use fixed tables,
length-limited reads and independent schema/value/provenance checks. Cursors bind
view, family and session. A failing family reports unavailable while other valid
families and authorization remain usable. These are engineering containment caps,
not benchmarked release thresholds.

The loader never repairs a DB, changes its schema, writes event rows or deletes
sidecars. If stopped-WAL reading needs owned auxiliary files, the explicit root
launcher may run the existing DB owner for read-only preparation before creating
the viewer's read-only namespace. That may create normal private SQLite WAL/SHM
auxiliary files, never event rows. The HTTP worker itself remains read-only and
holds no DB connection while serving. Missing/unsafe/locked/replaced inputs fail
closed; no immutable-read shortcut may ignore a live WAL. Source collection is
unaffected by a failed view.

## P-03: local HTTPS and browser lifecycle

Continue HTTPS on `127.0.0.1:18765`, protected root control over a private Unix
socket, an unprivileged API and ordinary isolated Chromium. No root browser.
Use the existing tested direct-leaf trust path; no CA, global trust-store change,
existing browser-profile edits, certificate-warning bypass or HTTP fallback.

On explicit root dashboard launch, create a localhost leaf/key if missing, or
renew it if expired/too near expiry. Use a seven-day leaf and the existing
hostname/pin/private-key validation. Old material is retained root-private; no
background renewal. Refuse grants until the leaf, permissions, fingerprint and
TLS listener verify. Each launch uses a fresh private HOME/NSS/user-data profile
trusting only that leaf for the localhost service, with existing tested browser
sandboxing. No persistent root bearer is saved. Remove only that launch's new
transient browser profile after its browser exits; preserve prior profiles,
application configuration, security history and unrelated data.

Implementation must verify the browser/dependency path on supported Ubuntu; do
not claim a clean install works merely because the development VM has a browser.
Use official trusted packages/vendor distributions, report missing prerequisites
honestly, and do not weaken browser isolation to get a pass. No Mac installation,
settings or credential changes are covered.

## P-04: packaging and acceptance

Build a local Debian development artifact with pinned application/runtime inputs,
prebuilt frontend assets, source/license provenance and root-owned code/config.
Provision the approved nonlogin source/backend identities without extra log groups;
refuse conflicting existing accounts/unsafe files. Generate per-install IDs/keys;
never package VM databases, native reports, real credentials, private keys,
bootstrap grants or VM-specific identity into an installer.

Installation may create application directories, manual HIDS units and metadata
only. Do not enable/start collection, change Audit/journal/PAM policy or revive
saved choices. Root explicitly selects/starts a source later. Preserve existing
state on upgrades; no automatic downgrade, history removal or broad uninstall.
Source/viewer failures must not destroy each other's functioning subset or history.

Synthetic privacy/authorization, clock/size/cursor, malformed-store and failure
checks precede actual retained-data browser testing. Test the existing three real
process records and selected M4 history without a new subscription or old-event
re-evaluation. Verify ordinary-user denial, cross-scope denial, expired/revoked
sessions, no data in unauthenticated responses/logs, real browser isolation/TLS and
post-cleanup preservation. Then test installation in an independent clean Linux
test root/guest without overwriting Linux 2's existing history. Record the limits
of any namespace/chroot substitute for a full clean VM.

The first installable build still needs a truthful supported collection/detection
story, source health, protected display and installation evidence. This proposal
alone does not make the full project complete or authorize new source/rule meanings.
Reassess the project's next investment at the first usable installable checkpoint.
