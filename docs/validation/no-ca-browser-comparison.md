# No-CA browser comparison and synthetic HTTPS integration

**Date:** November 13, 2026. **Result:** passed for the named Chromium build and
bounded synthetic scope. The owner authorized comparing no-CA alternatives after
clarifying that Firefox is not an architectural requirement. No CA was created;
real stored-history access remains gated by D-12c.

## Recommendation and alternatives

| Approach | Evidence / tradeoff | Current disposition |
|---|---|---|
| Directly trusted server leaf in Chromium | Actual verified TLS and synthetic dashboard flow passed; no certificate-signing authority added. Needs isolated Linux HOME/NSS and a compatible browser build | Recommended for the next bounded integration |
| Direct leaf peer trust in Firefox | Correct entry in actual Firefox 154 profile still rejected with verification enabled | Unsupported by the tested method; not a reason to require a CA for every browser |
| CA trusted in a dedicated Firefox profile | Conventional trust route, but a new signing authority/key lifecycle and broader authority inside that profile | Optional unapproved alternative, not the current blocker |
| HTTP-only loopback | Existing synthetic pilot works, but does not authenticate the server against a replacement local listener | Synthetic baseline only; not the proposed real-data trust solution |
| Certificate-error overrides / insecure flags | Suppress certificate verification rather than demonstrate the required trust | Excluded |
| Custom browser wrapper/native bridge | Could enforce custom trust but adds a new component/runtime and security interface | Not implemented or recommended for this first build |
| Publicly issued certificate/domain | Adds domain/control/renewal and external-service requirements to a local-first product | Not assumed or introduced |

This recommends a lab access path, not a product requirement to install/bundle one
browser. Normal-browser installation UX, stable-browser support matrix, updates,
certificate renewal and production packaging remain separate work. No custom
wrapper, public domain or external certificate service was added to the product.

## Verified runs

Browser-only pass: `/opt/hids-browser-leaf.hm5jjtlq/report.json`.
Snapshot `hids-src-20261113T053458Z-051bd40ff347`, manifest
`5ca768fe22b0d35ee17cbec29e0b9e1943a051d72f766c2a0a9e52a5d2cdd07e`.

Actual synthetic HTTPS authorization pass:
`/opt/hids-browser-leaf.940b2j6b/report.json`.
Snapshot `hids-src-20261113T092134Z-df704d0fe946`, manifest
`029448347a18b93395949ec14a59c3a9ce5a7e109e867519f048e0540abecbee`.
Adjacent `independent.json` rechecks original HIDS preservation, source identity,
closed trial ports, removed temporary policy, no browser processes left and absence
of history configuration. Host/guest timestamp strings are identifiers, not proof
of event-time semantics or elapsed performance.

Private automation environment `/home/ivy/hids-browser-compare.9z_gnv_e` pins
Playwright 1.65.1; its lock/setup logs and browser downloads remain there. The
browser is upstream Chromium reported through CDP as `Chrome/158.0.8127.18`,
binary SHA-256 `40c121f803bd7f2c3dc394a12f064d14af1faea4baf7938dd2a8edd5175086f6`.
That is a privately downloaded test build, not evidence for every Chrome stable,
Ubuntu Snap package or browser/version/platform. No global browser/package install.

The trials reused the earlier protected synthetic CA=false leaf and expired/
foreign fixtures from `/opt/hids-tls-synthetic.8m5rf1fp`; they did not generate a
CA, enable a certificate override or change an existing browser profile. NSS
`P,,` peer entries were used; no custom CA trust flags were added. Default browser
roots can still exist: this is added direct-leaf trust, not exclusive browser
fingerprint pinning. [Chromium's official Linux trust instructions](https://chromium.googlesource.com/chromium/src/+/main/docs/linux/cert_management.md)
explicitly distinguish self-signed server peer trust from CA trust.

## Isolation and sandbox evidence

Chromium's NSS database is shared by Linux HOME, not merely isolated by
`--user-data-dir`. Every test uses a completely new private HOME, XDG paths and
user-data directory. Both normal-user NSS locations are inventoried before/after
and remain unchanged, including absence where no database existed. Testing with a
private user-data directory alone would not establish this isolation. No Mac or
OS-wide trust change. Browser/driver run as ordinary UID 1000; the actual API runs
as existing backend UID 994 with no supplementary groups in the observed trial.

A downloaded Chromium initially refused to start with sandboxing enabled under
Ubuntu's user-namespace policy. The accepted test solution copied its binary/tree
to a root-owned `/opt/hids-browser-leaf.*` directory, removed writable/setuid modes,
and temporarily loaded an exact-binary AppArmor rule allowing user namespaces.
It used no wildcard, global sysctl change, setuid helper or sandbox-disabling flag.
The rule has `flags=(unconfined)` plus `userns`: it selectively permits this binary's
namespace use, not an added restrictive filesystem profile. It is a VM lab setup
cost, not a proposed silent product-install action.

The browser's actual command line has no certificate/sandbox bypass; Chromium
reports namespace sandbox, PID/network namespaces and seccomp enabled, plus its
positive sandbox verdict. After every bounded run the temporary rule is unloaded
without cache or persistent `/etc` policy installation. The global namespace
restriction remains 1. The independent final check finds no trial browser process
or listening test port. The initial private browser startup failure and failed
intermediate reports remain truthful.
[Upstream AppArmor guidance](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md)
describes the namespace restriction; the test deliberately uses an exact root-owned
path rather than its broader development-directory example.

## What passed

The final report contains **15 successful browser checks**:

- Additional trust is peer-only and the actual launch uses no TLS/sandbox bypass.
- Trusted leaf returns the expected synthetic page; untrusted replacement,
  wrong hostname and explicitly trusted but expired leaf fail with the expected
  certificate error codes. Plaintext does not serve the TLS response.
- Namespace/PID/network/ seccomp sandbox status is enabled; the valid TLS endpoint
  still works after all negative probes.
- A protected synthetic API request without a bearer is denied in the browser.
  The actual root-only Unix control handler issues a one-use HTTPS grant; the
  ordinary browser redeems it and displays the literal hostile-text example.
- The grant fragment disappears, cookies/localStorage/sessionStorage stay empty,
  logout removes displayed data and the consumed grant cannot authorize again.
  `/v0/history` remains absent. No retained event or finding is exposed.

`api/pilot_app.py` now accepts an explicit trusted `scheme` of http/https, default
http. Host/Origin and the physical ASGI transport scheme must agree with that
selection; no forwarded header or caller-provided URL selects it. Three new cases
cover HTTPS Origin, physical transport mismatch and unsupported schemes. The
synthetic service/CLI's existing operator configuration remains HTTP-only; no
permanent HTTPS service/config was installed or enabled by this prototype.

The HTTPS test uses the existing FastAPI app, session core, root-peer Control
handler, built frontend and validated leaf/key context, under the existing backend
identity. It does not replace the accepted stack or introduce a new production
entry point. The factory's explicit HTTPS mode is exercised with an actual TLS
transport; successful ASGI-only tests are not substituted for browser acceptance.
Final affected-scope checkpoint runs 42 API/session/client cases and nine client
race/timer cases against the exact accepted snapshot, with before/after manifest
verification and retained phase logs. Checkpoint report:
`/home/ivy/hids-browser-compare.9z_gnv_e/check-results/run-20261113T031826Z-9efa33b3dfec/report.json`.
M3/M4 implementation was not changed.

## Intermediate attempts retained

- `...rls2ak91/report.json`: browser ran, but CDP command-line inspection required
  the standard `--enable-automation` flag; added that test-metadata flag only.
- `...qvoscckf/report.json`: all certificate checks passed; pending error navigation
  interrupted the subsequent sandbox page. Isolate negative probes in separate pages.
- `...2_737ndv/report.json`: certificate checks passed and the sandbox was actually
  enabled, but its newer table label was not recognized. Require actual `Layer 1
  Sandbox=Namespace`, PID/network and seccomp Yes values plus the positive verdict.
- `...6yib_1he/report.json`: HTTPS API became ready as UID 994, but the harness
  passed text input to a binary-mode subprocess. Enable text mode; no protocol or
  certificate assertion was relaxed.

Failed reports are not upgraded to passes or deleted. Every reported attempt
preserved the production baseline and removed its temporary policy/stopped servers.
The private VM login helper was separately tightened after browser diagnostics
resembled password prompts: exact literal prompt matching, a separate private
credential file and output redaction. No credential was added to the repository;
this is not a change to VM passwords, SSH configuration or Mac settings.

## Remaining gate

Firefox is optional. A CA is not necessary for this demonstrated Chromium path.
The next stored-history review should preserve no-CA direct-leaf trust with an
explicitly compatible isolated browser environment, rather than add a CA merely
to accommodate Firefox. The complete D-12c fields/selection/frozen-view/limits
contract still needs owner approval before implementation or real-data exposure.
Keep its provisional budgets and browser/default-root trust limitations explicit.
