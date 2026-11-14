# Dashboard session mechanism — accepted pilot decision D-12b

**Status: owner accepted the mechanism and synthetic-only pilot, November 12, 2026.**
The owner answered “continue” to the explicit implementation/test request.
The synthetic-only implementation and acceptance now passed; see
[executed evidence and remaining limits](../validation/dashboard-session-pilot.md)
and [build/run guide](../../api/README.md). Approval alone was not a test pass.
[D-12a eligibility is accepted](dashboard-access-eligibility-review.md): explicit
UID-0 authorization, including OS-authorized sudo, for each new session. This
packet records approval of the concrete mechanism and a synthetic-only Ubuntu
pilot. It does not authorize real-data HTTP routes, unattended collection, a
new rule, source changes or a finished dashboard.

## Accepted pilot experience and scope

A root/sudo HIDS command prints a one-use local link. The administrator opens it
in their ordinary browser. The resulting session lives only in that tab's memory;
a full refresh, tab closure or process restart requires another root authorization.
Normal in-page navigation does not. A visible logout ends the server session.
The proposed limits are 60 seconds to use the link, five minutes without an
accepted authenticated request, and 30 minutes maximum session lifetime.

The owner approved this mechanism for a synthetic-only, manually started Linux 2 pilot,
including its ordinary-browser trust boundary, memory-only bearer transport,
expiry/revocation and acceptance gates below. These limits are conservative pilot
choices, not measured release performance thresholds. A persistent-login UX,
new dedicated API identity, or a different authentication mechanism would need
separate review. No commits/pushes or Mac system changes are included.

## Privilege boundary and authorization path

1. A root-owned, non-setuid HIDS CLI checks real/effective UID 0 and uses a fixed
   trusted installation/import path (Python isolated mode). It invokes no shell,
   accepts no arbitrary paths or commands, and never handles a password. Sudo
   remains the OS's decision, including its existing credential-cache policy.
   `SUDO_USER`, group membership, frontend claims and Audit auid are not identity
   proof. This records root approval, not a verified initiating human name.
2. The CLI connects only to a fixed pathname Unix control socket inside a
   root-owned 0700 directory; socket owner root and mode 0600, no symlink path.
   Root-owned systemd socket units create and pass named listener descriptors to
   one unprivileged API process under the existing backend identity. No new root
   daemon or privilege-bearing API helper is introduced. The API verifies the
   connecting control peer's UID 0 using Linux `SO_PEERCRED` before reading an
   operation. The CLI verifies the protected path and root-created listener.
   Do not mistake listener-creator peer credentials for the accepting service's
   identity: socket activation can initially identify systemd/root, while a
   subsequent `listen()` by the designated backend can identify that backend.
   The CLI permits exactly root or the NSS-resolved backend UID, together with
   the root-owned directory/socket checks; other peer UIDs refuse. Server-side
   clients must still be UID 0. Python pathname cleanup is disabled for the
   inherited Unix listener: only systemd owns/removes that root-only pathname.
3. Closed control operations are `mint` and `revoke_all`, with protocol version,
   bounded JSON framing, four-KiB maximum request/response and short deadlines.
   Unknown fields/operations, trailing messages, non-root peers and unexpected
   listener descriptors refuse. No shell, SQL, file read/export or collection
   operation exists in this protocol. Named TCP and Unix descriptors must match
   the expected type/address and root unit configuration before readiness.
4. Minting requires the same process's HTTP listener and control loop to be ready.
   The configured HTTP origin is exactly `http://127.0.0.1:<port>`; the numeric
   port comes from root-owned configuration, never a caller-supplied redirect.
   Binding fails closed if occupied; no wildcard/IPv6/proxy forwarding. The
   root-managed TCP listener stays reserved across API process restarts while
   the pilot socket unit is active. All grants are nevertheless invalidated on
   API restart. No persistent enablement or automatic collection follows startup.
5. The server creates a cryptographically random 32-byte bootstrap value, canonical
   unpadded base64url, expiring after 60 monotonic seconds. Only its SHA-256 digest,
   expiry and scope are retained in memory. Maximum four combined unexpired
   grants/sessions; reject at capacity without evicting another session. Expired
   entries are discarded on access and periodic bounded housekeeping.
6. The CLI displays the link only to its interactive terminal, never launches a
   root browser or puts a secret in process arguments, files or shell history.
   The bootstrap is in the URL fragment, not query/path. The local static shell
   removes it immediately with history replacement, then redeems it once using
   same-origin JSON POST. No external asset, analytics, service worker or redirect.
   URL fragments are not sent with HTTP retrieval; this reduces server-log leaks
   but does not make terminal/clipboard/browser-history/extension exposure vanish.
7. Atomic redemption consumes the grant and issues a **different** random 32-byte
   session value, scope `pilot:read`. The server retains a digest and monotonic
   issue/last-request times; the browser keeps the raw value only in memory and
   sends it as `Authorization: Bearer ...` to fixed same-origin routes. No cookies,
   localStorage, sessionStorage, URLs, durable session DB or refresh tokens.
   Strict canonical lengths/encoding and duplicate-header rejection apply.

Systemd listener passing and Linux peer-credential behavior are documented in
[systemd.socket](https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html)
and [unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html).
Actual Ubuntu identity/modes/descriptor behavior must pass before acceptance;
latest upstream documentation alone is not evidence of guest behavior.

## HTTP surface and browser defenses

| Surface | Authorization and result |
|---|---|
| `GET /`, fixed packaged assets | Locked shell only. No host identity, health, rule, event, count, source or version metadata |
| `POST /v0/auth/redeem` | One-use grant in bounded JSON, exact Host/Origin and same-origin Fetch Metadata; returns session token once |
| `GET /v0/pilot` | Valid `pilot:read` bearer; fixed synthetic example with text fields only, no M3/M4 access |
| `POST /v0/auth/logout` | Valid bearer plus exact Origin; revoke that session server-side |
| Everything else | Closed route/method set; no debug/docs/schema endpoint or sensitive error detail |

All requests enforce the exact configured Host including port; reject malformed,
multiple, unrecognized and proxy-supplied authority. No trusted proxy headers or
CORS enablement. All browser API calls require `Sec-Fetch-Site: same-origin`;
POST also requires exact Origin and JSON content type, body at most one KiB,
closed schema and no credential in query. GET may omit Origin (normal same-origin
fetch behavior); an Origin, if present, must match. Foreign/null origins and
cross-site fetches refuse before any grant is consumed. Local programs can forge
these headers; the bearer/root control proof remains the actual authorization.
Cross-origin preflights receive no access grant. Cookies confer no authority.

Session validation runs on every protected request. At idle/absolute deadline,
logout, root `revoke_all` or API restart, reject old credentials. Successful
protected requests renew idle time only; no request extends absolute lifetime.
A closed tab loses its client token but **does not guarantee immediate server
revocation**: browser close signals are unreliable; server timeouts remain binding.
An HTTP retry after a lost successful redemption cannot reuse the consumed link;
the user must request a new link. No persistent recovery bypass.

Responses use `Cache-Control: no-store`, no-referrer, nosniff, frame denial and
CSP limited to packaged same-origin code/styles/connections, no inline/eval code,
no third-party resources or embedding. Sensitive bodies and credentials are
excluded from request/access/error logs; error output is bounded and generic.
Render synthetic and later event text as text, never HTML. Do not persist tokens
or sensitive response content in browser storage or offline caches. Pilot request
concurrency, input deadlines and body limits must be bounded; overload refuses
without changing storage/source state or minting a grant.

Cookie sessions were considered, but cookies do not isolate same-host services by
port ([RFC 6265 section 8.5](https://www.rfc-editor.org/rfc/rfc6265#section-8.5)).
Memory-only bearer headers avoid that automatic cross-port credential sharing.
This is an application-specific recommendation, not a claim bearer JS memory is
immune to XSS. [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
explains server-enforced expiration, logout and browser-storage risks; exact pilot
limits here are our proposal. [Fragment behavior](https://developer.mozilla.org/en-US/docs/Web/URI/Reference/Fragment)
supports the one-use handoff transport, not confidentiality from the browser.

The accepted SSE direction is preserved for later integration. A bearer session
needs authenticated fetch streaming rather than native `EventSource`, whose
constructor exposes no arbitrary-header option
([browser API reference](https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource)).
No token in an SSE URL, cookie fallback, new stream dependency or actual stream
endpoint is approved by this pilot. Later streams must enforce expiry/revocation
throughout their lifetime; server frames cannot renew session idle time.

## Explicit trust limits

- An authorized ordinary browser is entrusted with sensitive viewing authority.
  Same-account malware, extensions, injected JavaScript, debugger/process-memory
  access, clipboard and terminal exposure can steal/use the bearer or data.
  CSP reduces opportunities; it does not turn a compromised browser into root
  isolation. No claim that every HTTP request proves the current OS user is root.
- Loopback HTTP is local transport, not authenticated TLS. Ordinary remote peers
  cannot directly connect to its listener, but a stopped/released listener's port
  can be occupied by another local process. Old pages/links, origin reuse and
  pre-existing malicious service workers are residual risks. The pilot must use a
  clean test-browser profile/origin and test occupied-port refusal. No real-data
  exposure is approved by that test precaution; production origin ownership and
  browser trust must be reviewed with the real-data contract. No Mac certificate,
  trust-store, SSH tunnel or remote browser access change is included.
- Existing backend identity access remains trusted. A read-only API mount can
  prevent accidental writes but cannot promise isolation from a fully compromised
  same-UID writer/API process. This proposal adds no account/groups/capabilities;
  splitting that principal requires D-01 review. Fully compromised root/backend
  and malicious installed application code remain outside the claimed protection.
- Scope is read-only synthetic viewing plus session mint/revoke. Authentication
  cannot select sources, start collection, enable rules, alter history, reconfigure
  OS logging or bypass first-run confirmation. No real SQLite store is mounted
  into the pilot's data view.

## Approved implementation and evidence plan

Repository inspection: `api/` and `frontend/` have scaffold directories but no
implemented app or dependency manifests. Reuse the accepted FastAPI and
React/TypeScript/Vite stack. First inventory existing guest tool/package versions;
then use pinned, private VM environments for the minimal required framework and
build dependencies. Record exact resolutions and available license/security
metadata; no global installation, new runtime framework or Mac system change.
Root-owned runtime code/assets must be separate from unprivileged dependency
build inputs. No production deployment is implied by a private pilot build.

1. Implement a small framework-independent session core with injected monotonic
   clock/random source, strict protocol parsing and no data/collector imports.
   Test expiry boundaries, one-use concurrent redemption, random-source failure,
   capacity, scope, revocation, restart and redaction; use real randomness in the
   integrated pilot. Tests must exercise state transitions, not mirror code.
2. Integrate the FastAPI app and minimal ordinary-browser page, single worker with
   in-memory state. Multiworker/reload mode refuses unless a separately reviewed
   shared-state design exists. Implement inherited listeners and CLI with trusted
   install paths; root unit/config provisioning is private/manual in Linux 2.
3. Run negative integration cases under actual root, ordinary-user and backend
   identities: socket traversal/connect and UID checks, forged fields/groups,
   wrong listener/address, occupied port, root control errors, lost redemption,
   oversized/slow/malformed/duplicate messages, cross-origin/forms/preflights,
   missing/stale bearer, expiry/logout/root revoke/restart. Confirm every protected
   route rejects before serialization; inspect logs for seeded synthetic secrets.
4. Exercise the real browser: successful root-link handoff, no token request URL,
   fragment removal, no durable storage/cookies, refresh needs reauthorization,
   text-only rendering of hostile strings, locked unauthenticated view and logout.
   If browser tooling fails, fix/replace the access path; do not substitute HTTP
   client success for browser acceptance.
5. Independently compare real M3/M4 history/backup/artifact/policy baseline and
   service states before/after; stop/remove only newly created pilot activation
   and retain private reports. No changes to installed M3 files, Audit/PAM/journal
   policy, existing history or default source/rule activation.

Completion means this bounded synthetic authorization pilot passes, with failures
and residual risks documented. Next review the exact read-only M4 API fields,
query/cursor/budget contract and production origin trust; only then expose real
stored data. Pilot success is not dashboard, M4, security-audit or release completion.
