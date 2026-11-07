# Limited M1 process EXEC contract

The [owner-approved pilot contract](../../docs/implementation/m1-pilot-contract.md)
is authoritative for `m1.process-exec/0.1.0` and wire protocol integer `1`.
It is not a finalized production ECS schema or general native-event contract.

Executable validation is independently implemented in
[C++](../../collector/src/pilot/contract.cpp) and
[Python](../../engine/ingestion/m1_contract.py). Both run the same
[62 sanitized contract vectors](../../tests/fixtures/process/m1-contract-cases.json).
The [EXEC envelope fixture](../../tests/fixtures/process/m1-exec-envelope.json)
illustrates explicit absent activity wall time and a lossless monotonic decimal
string. The [native fixture](../../tests/fixtures/process/synthetic-exec-001.json)
feeds the existing C++ parser through a test-only UAPI packet builder.

No runtime JSON Schema package, automatic ECS remapping, unknown-field retention
policy for other families, or new dependency is introduced. M1 rejects unknown
keys and unsupported versions; production evolution requires explicit review.
