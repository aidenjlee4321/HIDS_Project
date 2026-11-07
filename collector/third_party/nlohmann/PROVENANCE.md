# nlohmann/json 3.12.0 provenance

Vendored dependency only; this addition does not implement the M1 event pipeline.
The upstream header and license are unmodified.

## Upstream identity and acquisition

- Project: [JSON for Modern C++ (nlohmann/json)](https://github.com/nlohmann/json).
- Release: [v3.12.0](https://github.com/nlohmann/json/releases/tag/v3.12.0).
- Release artifact: https://github.com/nlohmann/json/releases/download/v3.12.0/json.hpp
- Pinned commit: `55f93686c01528224f448c19128836e7df245f72`.
- Pinned single-header source: https://raw.githubusercontent.com/nlohmann/json/55f93686c01528224f448c19128836e7df245f72/single_include/nlohmann/json.hpp
- Pinned license source: https://raw.githubusercontent.com/nlohmann/json/55f93686c01528224f448c19128836e7df245f72/LICENSE.MIT
- Acquisition timestamp (UTC): **2026-11-07T10:50:26Z**. Existing private staging
  artifacts were reused; this timestamp records the completion time retained as
  the last downloaded file's filesystem modification time, not a signed timestamp.
- Artifact verification completed (UTC): **2026-11-07T10:54:24Z**.
- Canonical include-path smoke test completed (UTC): **2026-11-07T10:55:40Z**.
- Acquisition used HTTPS with certificate validation and HTTPS-only redirects.
  No system package was installed, and no Git operation was used.

## Integrity and source comparison

The expected header digest was supplied by the owner and independently listed in
[upstream's release notes](https://github.com/nlohmann/json/releases/tag/v3.12.0).
All digests below use SHA-256 over complete original file bytes.

| Item | SHA-256 |
|---|---|
| Published/expected release header | `aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63` |
| Locally computed release header | `aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63` |
| Locally computed pinned-commit source header | `aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63` |
| Locally computed pinned-commit LICENSE.MIT | `46a65cffd1ea955132d95a8dd921640714a8d6b537d2e4e482d31145ae95b603` |

Release/pinned source byte comparison: **identical**, 953,436 bytes.
The repository copy was checked byte-for-byte against the verified staged header
and license. The license is 1,076 bytes. No upstream-published
license checksum was supplied; its digest above is a local verification record.

## Version and license verification

Each macro must have exactly one definition whose right-hand side is a decimal
integer, followed only by whitespace and an optional trailing `//` comment.
A full-match check rejects expressions, quoted integers, malformed values and
duplicate/missing definitions. The three values were independently extracted and
compared, rather than inferred from the filename or package version:

| Macro | Required and observed integer |
|---|---|
| `NLOHMANN_JSON_VERSION_MAJOR` | 3 |
| `NLOHMANN_JSON_VERSION_MINOR` | 12 |
| `NLOHMANN_JSON_VERSION_PATCH` | 0 |

The original check incorrectly rejected upstream's trailing comments; that parser
was corrected before vendoring. Negative parser checks reject missing/duplicate
macros, expressions, quoted integers and malformed suffixes. The header was never
edited to make verification pass.

License: **MIT**. Copyright **(c) 2013-2025 Niels Lohmann**. The complete pinned
license was reviewed and checked against the full MIT grant, notice requirement
and disclaimer, ignoring whitespace only for that semantic check. The original
license bytes (including heading whitespace) and embedded header notices are
preserved unchanged in [LICENSE.MIT](LICENSE.MIT) and [json.hpp](json.hpp).
Checksum/source matching and license checks were performed; no local OpenPGP
signature verification is claimed.

## Minimal C++20 compilation and execution

- Host: Darwin 23.5.0, arm64.
- Compiler: Apple clang version 15.0.0 (clang-1500.3.9.4).
- Flags: `-std=c++20 -Wall -Wextra -Wpedantic -Werror`.
- Explicit canonical include directory: `/Users/aidenlee/Downloads/hids/collector/third_party`.
- Include: `<nlohmann/json.hpp>`.
- Static assertions independently require version macros 3, 12 and 0.
- Test parses an object with integer, Boolean and string values, checks each,
  serializes through the library, reparses and verifies value equality.
- A temporary mirror of the final vendor layout passed compilation and execution
  before repository placement. The canonical vendored include path then passed
  the same strict compilation and execution; both exit statuses were **0**.
- Execution result: `PASS: nlohmann/json 3.12.0 parse/serialize/reparse {"count":7,"name":"pilot","ok":true}`.
- Test source and both binaries were kept outside the repository in private
  temporary storage. No test/build artifact is included here.

These are local dependency smoke checks, **not Ubuntu/GCC validation**, production
collector validation or M1 integration tests. Ubuntu ARM64/GCC 15.2.0 compilation
of this dependency remains to be performed. No live process collection, service
identity/privilege change, logging configuration change or pipeline implementation
was part of acquisition. Builds should use this pinned copy without automatic
network fetching; updates require a separate reviewed dependency decision.
