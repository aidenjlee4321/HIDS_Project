# TLS generation failure privacy — November 14, 2026

Later first-build maintenance: [`.14` source stop ownership](source-control-safety.md).
The `.13` evidence below remains historical and unchanged.

Continued owner-authorized first-build review with Copilot. This is permission
hardening for new TLS generations, not a new CA, source, role or renewal policy.

## Evidence and correction

Initial restricted source review reported no concrete defect:
`hids-copilot-review-3c762f8fd2904bd689af1116e73fddce`, normalized packet
`55dbd1cad0b6e948503f34d4f0045853d11829419192d9da11dea81f4cfbe754`.
Independent VM fault injection then showed that a newly generated, unused key was
backend-readable after final validation failed. Existing leaf/key bytes remained
unchanged. Reproduction: `/opt/hids-tls-failure-before.g85sflxt/report.json`.
It used synthetic test keys only; the reproduction directory was subsequently
restricted to 0700. This does not show exposure to ordinary users, stolen keys or
damage to a production certificate. The backend already legitimately reads the
active server key; the improvement limits access to unvalidated failed attempts.

New generations now start root:root 0700, with the private key root:root 0600.
The same certificate/pin/signature/SAN/EKU/lifetime/key-match validation runs before
backend permission handoff. Its internal staging option requires both real and
effective UID 0 and exact private metadata. Normal service validation keeps its
existing 0750 directory/0440 key, designated backend group and crypto requirements.
Root syncs new material and metadata before return; catchable failures restrict the
generation directory to 0700 and preserve it for inspection. Existing material is
not overwritten or automatically deleted, and no background renewal is introduced.

Copilot reviewed the correction separately and found no further concrete defect:
`hids-copilot-review-b00019a55535430ea5b0cc564e1f75d1`, packet
`abbfa9880e14d59fa7ecd998d18d423eb1acf8e2ed9266ec0314b4675c198c05`.
Both reviews used one auto-selected `gpt-6-luna` request each, zero tools and zero
model-applied changes. Only inspected source was supplied; no certificate/key
contents, runtime records or credentials went to the reviewer. The first review's
miss demonstrates why executable failure checks remain necessary.

## Actual Ubuntu failure and lifecycle checks

Final snapshot: `hids-src-20261114T120549Z-ab10feb3709e`, 427 source files.
Manifest: `d8e795d1e8d73c2fdc0d1c7484a0e24126e2ad6fad0eb2b1adac518654a789d0`.
VM source:
`/home/ivy/hids-copilot-build.uwa242qg/verified/hids-src-20261114T120549Z-ab10feb3709e`.
Eleven-phase report:
`/home/ivy/hids-copilot-build.uwa242qg/tls-staging-checks/run-20261114T112316Z-b1a6e0c25ee9/report.json`.
179 Python tests, 24 client tests, TypeScript and three frontend builds passed
without skips. Two added component checks reject nonroot staging and non-boolean
staging flags before OpenSSL invocation.

Final fault report: `/opt/hids-tls-faults.0hp6jvbx/report.json`.
Ten cases passed: OpenSSL failure before creation; timeout after actual generation;
validation failure; backend ownership handoff failure; file sync failure; directory
sync failure after handoff; directory-mode failure; KeyboardInterrupt; actual
SIGKILL after OpenSSL; and actual SIGKILL during private validation. A real backend
identity could read the valid fixture key, could not read failed-generation keys,
and could read successfully retried/validated keys. Original material stayed
byte-identical. Successful unused retries were retained privately after checking.
All material was newly generated under a test root, with no listeners/trust edits.
Near-expiry clocks were mocked in the test process only; the VM clock was unchanged.

Existing reuse, wrong-pin, unsafe-key, near-expiry and expired-leaf checks passed:
`/opt/hids-tls-lifecycle-final.68u2t333/stdout.log`.
The checks preserve seven-day max lifetime, localhost-only identity and CA:FALSE.

Unvalidated material stays private through generation/validation. A SIGKILL after
validated material has been handed to the backend can still leave a valid unused
generation; arbitrary forced termination cannot run Python cleanup. Physical
power-loss and every filesystem failure variant are not claimed tested.

## Packaged result and preservation

Version `0.1.0~dev20261114.13`, Ubuntu 26.04 AArch64/Python 3.14 only.
Size: 3,058,514 bytes. SHA-256:
`8ba8b4d5158c3bbf7134c77eb028d4e131cad152e5fb4fbc663cad2328bb475c`.
VM artifact:
`/home/ivy/hids-copilot-build.uwa242qg/development-packages/hids-development_0.1.0~dev20261114.13_arm64.deb`.
Verified local installer:
`/private/tmp/hids-first-build/hids-development_0.1.0~dev20261114.13_arm64.deb`.

Independent copy-on-write Ubuntu roots passed `.12`→`.13` upgrade/downgrade refusal
(`/opt/hids-package-acceptance.gfvvzscz/report.json`) and fresh install/reinstall
(`/opt/hids-package-acceptance.n7jt8ndg/report.json`). The real backend served
packaged HTTPS with the normal validation mode. Session revocation, frozen fixture
display, history/IDs/keys/choices, no-grant/legacy-gap refusal, boot-without-authority
and all 24 existing installed configuration SIGKILL/retry cases passed across the
two roots. These are not newly provisioned full-VM boot tests. Native code and
dependencies were unchanged and reused after source/recipe/hash checks.

Final proof: `/opt/hids-tls-staging-final._ckvnwx6/report.json`.
The 396-file baseline, installed hashes, Audit policy and preserved source prefixes
matched. Seven source/viewer units stayed inactive, with no pending process grant.
The process DB retained three events, its clean-stopped/no-ACK interval, quick_check
`ok` and unchanged cold bytes. All 649 regular payload files passed ownership,
privilege-bit, private-key, VM-identity/path and runtime-state exclusion checks;
package provenance version matched. No running VM installation, source authority,
Mac software/settings/credentials, commit or push changed. Only the installer was
retrieved; test keys, native evidence and credentials remain private on the VM.
