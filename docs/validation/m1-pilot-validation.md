# M1 pilot implementation and validation status

Historical November 7 checkpoint: the original pending status/tests below are
preserved. Later repository summaries record owner-reported Ubuntu M1 acceptance;
see [current state](../current-state.md). That report does not turn the local
results below into an independently inspected Ubuntu transcript.

**Recorded:** November 7, 2026  
**Status:** Implemented synthetic pilot; local boundary checks passed; Ubuntu acceptance pending  
**Authority:** Owner approved P-01–08 and authorized M1 implementation only

M1 is **not complete** until the actual Ubuntu two-process suite and final
persistence/retrieval demonstration pass. No local test substitutes for that gate.
The [approved contract](../implementation/m1-pilot-contract.md) remains authoritative;
the [validation runner documentation](../../tests/integration/README.md) describes use.

## Preserved baseline and dependency

Before modification, a SHA-256 inventory of existing non-Git repository files was
captured in private temporary storage. All existing production native headers,
three native translation units, native regression tests, ADRs and vendored
dependency files are preserved. New C++ pilot modules are separate from the
unchanged native collector. No live backend is linked into the fixture producer.

Canonical dependency checks matched the owner-validated Ubuntu transfer:

| File | SHA-256 |
|---|---|
| `json.hpp` | `aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63` |
| `LICENSE.MIT` | `46a65cffd1ea955132d95a8dd921640714a8d6b537d2e4e482d31145ae95b603` |
| `PROVENANCE.md` | `b9f053dd87b9d2289d075aabce9421b5e15dea2614f23f2a712929ceaaf41600` |

No acquisition, package installation or dependency update was needed for M1.

## Implemented scope

- Test-only UAPI EXEC packet construction and existing `decode()` parser reuse.
- Separate C++ normalization, strict duplicate-safe JSON validation, injected
  clock/UUID/serialization seams and nonblocking Linux UUIDv4 generation.
- One immutable event line, explicit Unix stream transport, capped framing,
  peer PID/UID/GID verification, deadlines, partial I/O and bounded retry outcomes.
- Independent Python contract validation and bounded framing.
- Python-only explicit SQLite transactions, WAL and independent connection
  profiles, full-content ID deduplication/conflict rejection, 100-row cap,
  schema verification and URI-encoded read-only retrieval.
- Private test-control pipes, startup readiness/peer authorization, replacement
  producer with original event preserved, terminal receiver exit, explicit-only
  restart and one explicit extra retry operation. No durable outbox.
- Synthetic fixtures, shared valid/invalid vectors, unit/integration tests and
  a shell acceptance runner with optional existing sanitizer support.

## Owner-reported Ubuntu prerequisite evidence

The owner reports Ubuntu 26.04.1 LTS, kernel `7.0.0-42-generic`, `aarch64`, GCC
15.2.0/C++20, Python 3.14.4, Python SQLite runtime 3.46.1 and standard-library
imports working. The exact vendored 3.12.0 header passed strict version and JSON
parse/serialize/reparse compilation/execution in that VM. These are prerequisite
results, **not execution of the newly implemented M1 pipeline**. Full transcripts,
execution time and M1 source-to-binary hashes have not yet been supplied.

## Local validation performed

Host: macOS ARM64 (Darwin); Apple Clang 15.0.0; Python 3.9.6; SQLite runtime
3.43.2. Python 3.9 exercised portable unit code only, not the recommended deployed
interpreter. Existing temporary official Linux UAPI headers and a POSIX test shim
were reused for native parser/regression checks; no new headers were downloaded.
The shim does not establish Linux Unix-socket/credential behavior.

| Check | Result / evidence boundary |
|---|---|
| Native collector offline suite | Passed strict compilation/execution and ASan/UBSan locally |
| Native Linux backend syscall-double suite | Passed strict compilation/execution and ASan/UBSan locally; no live netlink socket |
| Complete production link smoke | Passed strict linking/execution and ASan/UBSan locally; never calls `start()` |
| Synthetic native fixture/parser/normalization executable | Passed strict compilation/execution and ASan/UBSan locally with real UAPI-format bytes; no socket |
| M1 C++ contract/transport unit executable | Passed strict compilation/execution and ASan/UBSan locally; 62 shared vectors, UUID, calendar, response validation and fake-channel timing/partial-I/O tests |
| Python contract/storage tests | 17 tests passed locally, including actual private SQLite WAL/read-only operations, lock/full/commit faults and preserved native timestamps |
| Harness policy tests | 3 tests passed locally; no real processes used by those policy tests |
| Producer link and `--validate` fixture mode | Passed locally using separately compiled native parser/fixture objects and the non-Linux fail-closed socket branch; no transport execution |
| Linux integration suite | 12 tests explicitly skipped on macOS; **no Ubuntu acceptance evidence yet** |
| Shell / Python / fixture / Markdown checks | Syntax, sanitized JSON and local-link checks performed; no executable/build artifacts placed in repository |

Two initial local strict-build failures were corrected: a Linux-only private
field triggered Clang's unused-field warning in the non-Linux fail-closed branch,
and temporary Linux UAPI headers supplied with `-I` exposed external GNU-extension
warnings. The non-Linux branch now explicitly marks the field used; external
headers use `-isystem`, matching their system-header role on Ubuntu. Project
source warnings remain `-Wall -Wextra -Wpedantic -Werror`. No native collector
source was altered to suppress errors.

## Reproducible commands

From the complete source tree on Ubuntu, without sudo:

```sh
bash tests/integration/validate_m1.sh
bash tests/integration/validate_m1.sh --sanitize
```

The [script](../../tests/integration/validate_m1.sh) records compiler, kernel,
architecture, Python/SQLite and dependency hashes, then contains each exact
strict compile/link/test command. Sanitizer mode first checks the existing runtime;
it fails rather than installing anything if unavailable. Preserve its stdout and
stderr privately along with the final `result.json` and source/dependency digests.

Portable boundary checks used locally:

```sh
python3 -B -m unittest discover -s tests/unit -p 'test_m1_python.py' -v
python3 -B -m unittest discover -s tests/integration -p 'test_m1_harness_policy.py' -v
bash -n tests/integration/validate_m1.sh
```

Local C++ core command (replace the private output directory as appropriate):

```sh
c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror \
  -I collector/include -I collector/third_party \
  collector/src/pilot/contract.cpp collector/src/pilot/transport.cpp \
  tests/unit/m1_contract_test.cpp -o /absolute/private/build/m1_contract_test
/absolute/private/build/m1_contract_test \
  tests/fixtures/process/m1-exec-envelope.json \
  tests/fixtures/process/m1-contract-cases.json
```

For ASan/UBSan append `-fsanitize=address,undefined -fno-omit-frame-pointer` to
the compiler command. Local native commands follow `collector/README.md`, adding
`-isystem /private/tmp/hids-cnproc-validation-1wejko38/include/uapi` and
`-include /private/tmp/hids-cnproc-validation-1wejko38/mac-shim.h` for that
pre-existing macOS-only test environment. These paths are not Ubuntu dependencies.

## Outstanding acceptance evidence and limitations

The actual Ubuntu run must establish the full producer → receiver → committed
row → fresh read-only lookup, not merely compile/test-double success. The final
runner compares the complete retrieved envelope with the immutable original and
records its event ID, ACK result, raw monotonic value, null activity wall time and
retrieved canonical hash in a protected synthetic report. That report is not
available yet, so no actual two-process round trip is claimed here.

Still pending: real Linux socket flags/credentials, UAPI producer linking with
GCC 15.2.0, integration failure/restart/signal cases, Ubuntu WAL/SHM permissions,
Python 3.14.4 execution and sanitizer compatibility. Different-UID/GID negative
checks are doubles; no identity/grant changes are authorized for testing.

No live cn_proc, `/proc` enrichment, journal/Audit ingestion, real security records,
production identities/deployment, dashboard/API, rules/alerts/correlation, or
configuration changes are implemented or validated. Own-process capability/mount
metadata is inspected only to enforce the private unprivileged test environment.
No system packages, automatic privilege escalation, Git operations or OS logging
changes occurred. Same-user synthetic access does not replace root-only human
authorization or production privilege separation.

## Files created and modified

Created for M1:

- `collector/include/hids/pilot/contract.hpp`
- `collector/include/hids/pilot/transport.hpp`
- `collector/src/pilot/contract.cpp`
- `collector/src/pilot/transport.cpp`
- `docs/validation/m1-pilot-validation.md`
- `engine/database/m1_store.py`
- `engine/ingestion/m1_contract.py`
- `engine/ingestion/m1_io.py`
- `engine/ingestion/m1_receiver.py`
- `engine/ingestion/m1_security.py`
- `shared/schemas/m1-process-exec-0.1.0.md`
- `tests/fixtures/process/m1-contract-cases.json`
- `tests/fixtures/process/m1-exec-envelope.json`
- `tests/fixtures/process/synthetic-exec-001.json`
- `tests/integration/README.md`
- `tests/integration/m1_harness.py`
- `tests/integration/m1_native_fixture.cpp`
- `tests/integration/m1_native_fixture.hpp`
- `tests/integration/m1_producer.cpp`
- `tests/integration/run_m1.py`
- `tests/integration/test_m1_harness_policy.py`
- `tests/integration/test_m1_integration.py`
- `tests/integration/validate_m1.sh`
- `tests/unit/m1_contract_test.cpp`
- `tests/unit/m1_native_fixture_test.cpp`
- `tests/unit/test_m1_python.py`

Modified documentation/guidance:

- `AGENTS.md`
- `docs/README.md`
- `docs/implementation/m1-pilot-contract.md`
- `docs/implementation/v0.1-implementation-plan.md`
- `todo.md`

No existing production source, native regression, dependency, ADR, research utility,
architecture, threat-model or event-schema file was changed.
