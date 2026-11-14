# Explicit process stop ownership — November 14, 2026

Continued owner-authorized first-build reliability review with Copilot. This fixes
pending authorization cancellation and active stop ownership within the approved
process pipeline. No source/rule meanings, collection authority, logging policy,
HTTP fields, native IPC or retained-data contracts change.

## Findings and correction

Initial inspected-source review: `hids-copilot-review-569b8649e38140d4bc3db9c98c326780`,
packet `01de250862507b5570e8c6554eb735e87e2bd54de67548554dfa8c840452998a`.
Copilot identified that interruption after one-use grant creation could leave Stop
unable to cancel the matching authorization when no matching status was published.
It also identified that a saved status file alone does not establish ownership of
the currently running service or its component processes.

Stop now acquires the runtime owner lock before revoking an exact matching unused
grant, including an expired grant. Foreign/malformed authorizations are retained.
The root source/activation/generation ownership journal remains authoritative for
matching; saved source choices gain no activation authority. Removal is synced.
A running coordinator holds the same lock, preventing concurrent grant consumption.

The coordinator now publishes version 2 internal root control metadata: its PID
and systemd invocation ID. Active Stop matches those values against live systemd
state before and after opening a PID descriptor, then signals that descriptor.
The coordinator performs its existing cleanup. The adapter requires inactive
components afterward and never blindly stops unknown active component names.
Status presentation still reads version 1 and typed version 2 records without
exposing the internal witness. An active unbound version 1 runtime is refused;
existing stopped-before-upgrade requirements prevent an automatic takeover.
[Interface and compatibility](../implementation/source-control-status.md).

Follow-up review `hids-copilot-review-6e103aaf6c5e41fda92a156872b978f1`, packet
`917a840db0aa7fb60cc1fa4dcb54f8072b52430f6793081a264eac408982691f`, found that
requiring every unit to be inactive before cancelling could leave a grant behind
when a unit had failed. The correction revokes the exact unused grant under the
owner lock regardless of other unit state, but confirms Stop from revocation alone
only when every relevant unit is inactive. Unknown active or failed components
remain unconfirmed; cancellation does not stop them or claim recovery.

Final review: `hids-copilot-review-23038f4d3a924cbd8d62964003f8bf1b`, packet
`555acb9a7f7adf2628b5f0c10b4688058351ba2a9f49f19eca7600e4b23fbb82`.
Copilot found no further concrete defect in that packet. All three reviews used
one auto-selected `gpt-6-luna` request each, zero tools and zero model-applied
changes. Only inspected source was supplied, with no runtime records or credentials.
Review results are bounded evidence, not proof that every race/failure is excluded.

## Verified source and executable checks

Final snapshot: `hids-src-20261114T141630Z-97ef5ec2cdfa`, 431 files.
Manifest: `751b2094c436bbb97746dec94a246cce3769b66a29c545579320ce2ef95d46e9`.
VM source:
`/home/ivy/hids-copilot-build.uwa242qg/verified/hids-src-20261114T141630Z-97ef5ec2cdfa`.
Twelve-phase report:
`/home/ivy/hids-copilot-build.uwa242qg/source-control-final-checks/run-20261114T130254Z-6e97eb6e0e5a/report.json`.
194 Python tests, 24 client tests, TypeScript and three frontend builds passed
without skips. The named workflow now explicitly includes seven existing process
setup regressions; seven new cancellation/ownership checks and one typed-status
check are included in the other named groups. Native binary and dependencies were
unchanged and reused only after existing source/recipe/hash verification.

Root/source-free systemd report: `/opt/hids-source-control.ij7590lg/report.json`.
The test runs actual root permissions, immutable selection files, root ownership
journal, manager/adapter, owner flock, PID descriptors and systemd invocation IDs
with unique test-only units. A copied real publisher writes status from a synthetic
coordinator; the other test units only sleep. No native collector, production
source activation, retained-event write, policy/trust edit or network listener is
used. The ten assertions passed:

- Missing-status matching pending grant is cancelled.
- A failed service's grant is cancelled without falsely claiming Stop.
- A foreign grant remains byte-identical.
- Published version 2 metadata matches the actual test invocation.
- The owned live test coordinator exits through the targeted PID descriptor.
- Stale status cannot signal a different live invocation.
- An unknown active component remains running and Stop stays unconfirmed.
- Selection bytes remain unchanged.
- Original HIDS state is preserved.
- Production source/viewer units remain inactive.

Test-only units were stopped and removed. Earlier attempts exposed fixture-only
namespace-package and restrictive-umask assumptions; these were corrected before
the final snapshot. The second attempt's private failure record remains at
`/opt/hids-source-control.6v66fgae/report.json`. No production failure or successful
native-source run is inferred from these synthetic coordinator checks. The earlier
real native pipeline evidence remains separate.

## Installer and preservation

Development version `0.1.0~dev20261114.14`, Ubuntu 26.04 AArch64/Python 3.14 only.
3,059,236 bytes; SHA-256:
`78f9bc89a31727f502fdffa05b916e3fb62fcd129569642c1acf50e18c3c07c5`.
VM artifact:
`/home/ivy/hids-copilot-build.uwa242qg/development-packages/hids-development_0.1.0~dev20261114.14_arm64.deb`.
Verified local artifact:
`/private/tmp/hids-first-build/hids-development_0.1.0~dev20261114.14_arm64.deb`.

Independent copy-on-write Ubuntu roots passed `.13`→`.14` upgrade/downgrade refusal
(`/opt/hids-package-acceptance.5zxbllf8/report.json`) and fresh install/reinstall
(`/opt/hids-package-acceptance.jqdn68y3/report.json`). Packaged HTTPS/frozen fixture
presentation, session revocation, identity/data/key/choice preservation, no-grant
refusal, legacy-gap refusal, boot metadata without authority and all 24 installed
configuration SIGKILL/retry cases passed across the two roots. These tests use
synthetic fixtures and isolated namespaces; they are not fresh full-VM boot tests.
The actual running VM installation was not replaced.

Independent final proof: `/opt/hids-source-control-final.anmnqbxy/report.json`.
The original 396-file baseline, installed hashes, Audit policy and original source
prefixes matched. Seven process/viewer units remained inactive, with no pending
process grant; saved choices stayed empty at revision 6. An immutable read as the
actual database owner retained three process events, interval `[0,1,0,1]`,
quick_check `ok` and unchanged cold store bytes. All 649 regular payload files
passed root ownership, privilege-bit, private-key and VM identity/path exclusions;
exact provenance and the version-independent installed guide matched. The builder's
653 staging files include four Debian control files, which are not regular payload
members. An initial final-audit count assertion used the staging count; the
corrected independent audit passed without any package change. Its earlier private
receipt remains `/opt/hids-source-control-final.euzeceni/report.json`.

Only the installer was retrieved to Mac temporary output. Protected test records,
keys and credentials remain on the VM. No Mac software/settings/credentials,
Git commit/push, source activation, security-history deletion or CA change occurred.
This remains a development checkpoint within first-build maintenance, not a full
v0.1 release or expansion into additional product features. This evidence and
handoff documentation were written after the immutable artifact snapshot.
