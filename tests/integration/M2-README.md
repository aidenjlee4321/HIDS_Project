# M2 offline component validation

This readme preserves the original offline scope and commands. Later
[owner-reported Ubuntu runtime acceptance](../../docs/validation/m2-runtime-acceptance/ubuntu-runtime-acceptance.md)
records execution/cleanup with its own limits; the original pending-deployment
wording below is historical, not a revocation of later authorization.

Scope is the [approved M2 specification](../../docs/implementation/m2-journald-spec.md).
Production lifecycle entry points are now wired; **deployment and Ubuntu/live
acceptance remain unauthorized and unverified**.
M1 code/contracts/tests and evidence are unchanged.

## Implemented components

- Separate protocol-2 contract, independent C++/Python validators and shared vectors.
- Exact SSH executable/command pairing and injectable libsystemd match construction.
- Native normalization, cursor identity, immutable pending entry, activation-before-
  open, durable-boundary gate, explicit restart/rotation-gap handling.
- Linux libsystemd implementation behind `JournalIo`; non-Linux branch fails closed.
- Bounded authenticated Unix-channel primitives and response/retry validation.
- Python listener explicitly chowns/chmods/verifies its owned socket before listen.
- Per-connection authenticated PID lease, reconciliation, boundary and gap methods.
- Separate SQLite activations, events/rejected dispositions, progress and gaps;
  atomic checkpoint transactions, immutable conflicts, stale-revision protection,
  preserved first observations and URI-mode read-only lookup.
- Source-only systemd/tmpfiles artifacts, with no automatic service restart.

## Local commands

```sh
bash tests/integration/validate_m2_offline.sh
bash tests/integration/validate_m2_offline.sh --sanitize
```

On macOS, set `HIDS_NATIVE_UAPI` and `HIDS_NATIVE_SHIM` to the already available
private Linux-UAPI/header shim used for existing native regression checks. No
headers are downloaded. The runner keeps the shim out of M1/M2 socket transport
translation units. On Linux the native backend links `-lsystemd`; the test program
never constructs/opens a live journal. Running on Ubuntu still requires separate
owner authorization; do not interpret these commands as live acceptance authority.

The shell script contains all exact compilation and test commands. It uses strict
C++20 warnings and optional ASan/UBSan, private temporary binaries, Python `-B`,
no installs/build framework, and no Git commands. Temporary socket tests may need
sandbox approval on macOS; that permission concerns only owned test directories.
No runtime data is placed in UTM shared folders or the repository.

The synthetic two-process test constructs a native journal `Entry` from a committed
sanitized fixture, normalizes in C++, sends it over an inherited private socketpair,
validates/persists in Python and compares a fresh read-only lookup to the fixture.
No real journal is read or written. macOS uses an explicit test peer double because
Linux `SO_PEERCRED` is unavailable; this is not Linux credential evidence. Linux
fixture execution uses real same-account peer credentials, not the production
cross-account permission model. The child is reaped/terminated only by its owner.

## Remaining work before deployment or live acceptance

The production reader, ingestion and root-control entry points now exist. See the
[lifecycle validation record](../../docs/validation/m2-lifecycle-validation.md) for
activation/lease/shutdown and recovery semantics. The runner compiles the production
reader and runs its `--help` path only; the lifecycle subprocess executable links a
fake JournalIo and cannot open a real journal. Production entry points have no flag
to bypass root control, service identity or Linux credentials.

Systemd/tmpfiles files are source-only. **Do not install/enable/start them.** Actual
setup of hids-ingest/hids-ipc, installed paths and root-owned configuration still
requires separate approval. The config example's nulls are deliberately invalid
placeholders, not default source IDs or production storage limits. Activation
records authorization only; an administrator starts the reader separately after
activation. No service is spawned by a control request.

Outstanding validation includes actual libsystemd header/ABI/GCC compilation,
native API fault doubles for the Linux-specific backend, real tail/empty/rotation
behavior and actual service identities/groups/cross-account credentials. Existing
Linux M1 integration tests still skip on macOS. No local fake proves these gates.

Storage budgets are explicit caller inputs for fixtures; no production retention
budget is selected. SQLite page limits bound main database growth but do not alone
cap WAL growth under a long reader; unattended-operation limits/retention need
separate measured approval. Same-account fixture security does not replace root-only
human access or production reader/backend separation.
