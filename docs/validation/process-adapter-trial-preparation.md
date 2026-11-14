# Process adapter intended-account trial preparation

November 13, 2026. **Historical offline preparation; the later approved live trial passed.**
The [review packet](../implementation/process-adapter-trial-review.md) defines the
identity, privacy, retention and supervision scope. No service account was created
or subscription opened during this offline phase. The later separately approved
[live trial](process-adapter-live-trial.md) records those actual results.

## Target and verified source

Linux 2: AArch64, kernel `7.0.0-43-generic`, GCC Ubuntu 15.2.0-16ubuntu1.
Installed image `7.0.0-43.43` reports source package `linux-signed`; matching
linux-libc-dev reports source `linux` at that version. This package metadata is
not a review of the installed kernel's process-connector patches.
NSS lookup found `hids-process` absent.

Snapshot `hids-src-20261113T150019Z-c75a408a52e3`, manifest SHA-256
`7c01c8ac2b3ffd37fd0b81f6be5c6bb0b63ea62cd9212f7271a745142c5fbfdf`,
passed eight phases: strict collector compilation/test, syscall-doubled backend
compilation/test, complete real production link/no-start smoke, and trial
compilation/self-test. All compile commands used C++20 and
`-Wall -Wextra -Wpedantic -Werror`. No assertion-disabling flags were used.
Private VM report:
`/home/ivy/hids-browser-compare.9z_gnv_e/process-review-checks/run-20261113T090545Z-65c6763c6037/report.json`.

The probe was subsequently corrected to retry interrupted owned-child waits.
Final source snapshot `hids-src-20261113T150757Z-fff84d5d813a`, manifest SHA-256
`11b06b25d2b11be61ed62e1cd74c6b84314df6012ce54d8a397d7b7bf58cff19`,
passed strict recompilation and all 12 offline self-test groups. The final
invalid-delegation refusal also passed. Private VM report:
`/home/ivy/hids-browser-compare.9z_gnv_e/process-review-checks/run-20261113T091324Z-0afc5612d604/report.json`.
The earlier component phases remain
applicable because production sources and unit tests did not change.

## Bounded probe checks and limits

`tests/integration/process_adapter_trial.cpp` defaults to offline doubles. Its
12 assertion groups cover pre-target/unrelated/thread filtering, required owned
fork/exec/exit, serialized single LISTEN/IGNORE/close behavior, exact large integer
time serialization, null wall time/parent, fixed event cap and report descriptor
ownership/mode/access/offset rejection. Passing `--live --report-fd 1` separately
returned 2 with empty stdout, refusing before real-backend construction. This is
an invalid-delegation check, not proof of intended-account access.

No live role, kernel socket, event delivery, supervisor, account isolation,
resource hardening or real shutdown was validated by these checks. The backend
unit suite uses syscall replacements. The no-start link smoke constructs the
actual stopped production adapter without calling start. No sanitizer, dependency
installation, browser or complete application regression was needed for this
new test-only driver; existing first-run/history evidence is unchanged.

The trial does not integrate normalization, IPC, persistence or runtime selection.
Those remain future reviewed/tested steps after the native access evidence.
