# Firefox HTTPS trust amendment — optional, unapproved D-12c.1

**Subsequent result:** owner-authorized [Chromium comparison](../validation/no-ca-browser-comparison.md)
proved direct-leaf trust and the synthetic HTTPS dashboard without a CA. Firefox
is not an architecture requirement. This CA branch remains an unselected option
if Firefox support is later chosen; it is not necessary for the tested next step.

The owner authorized fixing the review issues. UI and resource-guard fixes are
implemented under synthetic acceptance. The original D-12c real-data/history
scope remains unapproved; this amendment requests only a replacement **synthetic
TLS trust test**, not permission to expose real data.

## Why the leaf-only proposal cannot be accepted as tested

Firefox 154.0 rejected the self-signed CA=false server certificate with certificate
bypass disabled. A follow-up checked the **actual running Firefox profile**, not
just the profile supplied to Selenium: the leaf was present with NSS `P,,` peer
trust, `acceptInsecureCerts=false`, and navigation still produced a certificate
error. Its private report is
`/home/ivy/hids-dashboard-build.zpoci9uz/tls-diagnostic.xky1jj5f/report.json`.

OpenSSL validation and verified Python TLS requests succeeded; fingerprint,
key mismatch, expiry, unsafe key mode, ordinary-user key denial, foreign certificate,
wrong hostname and plaintext-negative tests passed. Thus Python TLS success is not
browser success, and importing a peer-trust record is not evidence of Firefox trust.
The full synthetic TLS report correctly remains failed:
`/opt/hids-tls-synthetic.8m5rf1fp/report.json`.

Mozilla's verifier [uses CA trust for trust anchors](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/security/certverifier/NSSCertDBTrustDomain.cpp),
while [NSS documents peer and CA flags separately](https://nss-crypto.org/reference/security/nss/legacy/tools/nss_tools_certutil/index.html).
The current-source behavior corroborates the observed failure; it is not claimed
to be an exact source/binary provenance match for the installed Firefox build.
No CA trust, certificate override, insecure browser flag or plaintext fallback was
introduced to obtain a passing result. The extracted NSS tool package is private
to the VM, with no package installation or global trust change.

## Optional concrete amendment if the CA route is selected

Approve creating a local test CA, trusting its **public certificate only in a new
ordinary-user Firefox test profile**, and issuing a separate seven-day loopback
server certificate. Keep the CA signing key root-only in its own root-owned 0700
VM directory, key 0600; never give that signing key to the backend/browser. The
existing unprivileged backend receives read access only to its server leaf key
through root-managed group/modes. The server leaf remains CA=false, server-auth
only and SAN IP 127.0.0.1. Use a path-length-zero CA and no automated issuance API.

This is broader authority than leaf trust: possession of the CA key could issue
certificates for other names trusted by **that test profile**. Do not claim that
leaf SAN or path-length zero restricts CA issuance to loopback. Protect the signing
key and isolate the profile; host root and the trusted browser account remain
outside the confidentiality guarantee. No system/normal-profile/Mac trust change,
CA distribution, cloud service or new account is included.

First prove actual verified Firefox success and rejection of untrusted issuers,
wrong names and expired leaf certificates; require `acceptInsecureCerts=false`.
Keep all responses synthetic, keys/reports private to the VM, and stop every test
listener afterward. If the amendment fails, diagnose within these limits rather
than changing trust or bypassing verification. Do not switch on real history;
that remains the separately proposed D-12c contract.

Owner approval is needed because this replaces an explicitly leaf-only/no-CA
trust design, a reserved fundamental security decision. Existing blanket VM
maintenance access does not silently settle that browser trust choice.
