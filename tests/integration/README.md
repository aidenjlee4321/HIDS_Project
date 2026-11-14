# M1 synthetic fixture-to-database validation

This readme covers M1 only. For current source/handoff verification use
[M2](M2-README.md), [M3](M3-README.md), and
[M4 workflow/sandbox evidence](../../docs/validation/m4-handoff-implementation-validation.md).
M1 acceptance is subsequently owner-reported; its original gate wording below
remains the scope of that runner, not current global project status.

This harness implements only the [approved M1 contract](../../docs/implementation/m1-pilot-contract.md).
It never starts the native collector or opens a netlink subscription. No real
security records, accounts, elevated privileges, configuration changes, HTTP,
rules, alerts or v0.2 functionality are involved. Python alone writes SQLite.

## Ubuntu acceptance commands

Use the existing Ubuntu ARM64 compiler and Python, as an ordinary user. No sudo,
package installation, pip, CMake, pkg-config, SQLite CLI or C++ SQLite dependency.
The pinned header/license/provenance must retain their approved SHA-256 values.

From the repository or a complete copied source tree:

```sh
bash tests/integration/validate_m1.sh
# Repeat with sanitizers only if the existing compiler/runtime supports them:
bash tests/integration/validate_m1.sh --sanitize
```

The script contains the exact strict compilation/link/test commands. It compiles
all three unchanged native production translation units, reruns both native
regression suites and complete production link smoke, builds M1 contract tests
and the synthetic producer, runs Python storage/validation and policy tests, runs
the actual Linux integration suite, then performs a demonstrable final round trip.
The sanitizer variant adds `-fsanitize=address,undefined -fno-omit-frame-pointer`;
an unavailable requested sanitizer fails explicitly and installs nothing.

Build output goes to a fresh mode-0700 `/tmp/hids-m1-build.XXXXXXXX` directory.
Socket/DB/test evidence goes to fresh mode-0700 `/tmp/hids-m1-*` directories on a
verified local filesystem, with mode-0600 socket, DB/sidecars and report files.
The shared folder may contain source files, **never runtime databases/sockets**.
The runner disables Python bytecode files so source trees remain unchanged.
When a transferred source tree includes `M1_SOURCE_MANIFEST.json`, the runner
checks every recorded file before compilation and prints the manifest digest;
it also records the built producer digest. Neither step is a Git operation.
Private directories are retained for review; no broad automatic deletion occurs.

The final runner prints a synthetic event ID, commit ACK result, preserved native
monotonic timestamp, null activity wall time, retrieved-envelope SHA-256 and its
private evidence directory. Successful retrieval compares the entire envelope to
the original frozen message, not only its hash. `result.json` is a protected
synthetic summary, not a raw real-source report.

For individual commands after a producer is built:

```sh
python3 -B -m unittest discover -s tests/unit -p 'test_m1_python.py' -v
python3 -B -m unittest discover -s tests/integration -p 'test_m1_harness_policy.py' -v
HIDS_M1_PRODUCER=/absolute/private/build/m1_producer \
  python3 -B -m unittest discover -s tests/integration -p 'test_m1_integration.py' -v
python3 -B tests/integration/run_m1.py --producer /absolute/private/build/m1_producer
```

## Implemented boundaries and tests

| Boundary / contract cases | Implementation and evidence |
|---|---|
| Synthetic Linux UAPI EXEC → existing parser | `m1_native_fixture.cpp` constructs zero-initialized headers; fixed-slot DecodeSink copies one event; no source socket. Existing parser regression covers truncation, malformed lengths and alignment |
| C++ normalization, UUID, clocks, validation | `collector/src/pilot/contract.cpp`; native values remain native, timestamp roles separate. `m1_contract_test.cpp` exercises closed fields, all response types, calendar, UUID short-read/EINTR/terminal error, injected clock/serialization failure and the shared corpus |
| Bounded producer transport | `transport.cpp`; nonblocking CLOEXEC Unix stream, exact peer PID/UID/GID, one frozen line, LF outside caps, partial I/O, SIGPIPE-safe sends. C++ fake-channel tests cover offsets, stale readiness, cap, 3 attempts, 30-second deadline and uncertain results |
| Independent Python contract/framing | `m1_contract.py`; strict UTF-8/duplicate-key checks, depth precheck, exact fields/types, same corpus; split/coalesced and byte-limit unit tests |
| SQLite / read-only retrieval | `m1_store.py`; explicit transactions, WAL/FULL, independent reader/writer profiles, immutable ID comparison, 100-row cap, URI encoding, schema verification. Unit tests cover duplicate/collision/version priority, lock/full/clock/write/commit faults, sidecar modes, read-only writes rejected, reopen and retrieval failure |
| Real Linux two-process boundary | `test_m1_integration.py`: C++ fixture producer → Python socket receiver → SQLite → fresh read-only lookup; split/coalesced frames, malformed/oversized data, versions, collisions, partial disconnect, lost ACK, terminal storage failures/restart, replacement producer, malformed responses, wrong PID, startup and SIGINT cleanup |
| Explicit harness policy | `test_m1_harness_policy.py`: one separately requested retry operation, no automatic budget reset/unlimited retries, no retry after ACK, previous uncertainty survives later rejection |

`m1_harness.py` uses inherited private control pipes for startup and exact peer-PID
authorization. A prepared producer publishes its frozen synthetic line to harness
RAM before event transmission. Replacement producers are held until their new PID
is authorized and resend that exact original line. Harness policy permits only one
explicit extra operation per event (three attempts/30 seconds per operation).
Receiver restart is explicit after terminal failure and cleanup, never background
supervision. No durable outbox or production restart guarantee exists.

Fault callbacks/response transformations exist only as callable injection seams in
the test process. They are not event-wire commands or arbitrary executable actions.
Negative UID/GID tests use credential doubles; actual different-account testing is
not authorized. Actual Linux tests check positive SO_PEERCRED and a real wrong PID.
Same-UID peers are a synthetic harness boundary, not production privilege isolation
or authorization for ordinary humans to read real HIDS data.

## Evidence limits

The runner refuses non-Linux/root use; Linux integration tests report explicit skips
without a configured producer on macOS. Skips do not satisfy M1 acceptance.
Local macOS tests can exercise portable contract/storage/policy code and the native
parser with pre-existing temporary Linux headers/POSIX shim. This is not Ubuntu
socket/credential or compiler evidence. See the
[current validation record](../../docs/validation/m1-pilot-validation.md).

M1 is not complete until the actual Ubuntu suite and final fixture round trip pass
with recorded environment and source/dependency provenance. No live cn_proc,
production service identity, v0.1 dashboard or real-source reliability is validated
by this synthetic milestone.
