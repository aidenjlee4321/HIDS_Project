# ADR-006: Provisional live process lifecycle collection

**Status:** Provisional direction authorized by owner; production suitability unresolved  
**Date:** November 6, 2026

## Evidence

The [process-connector research](../research/process-connector.md) records one
ordinary-user Ubuntu 26.04.1 ARM64 experiment: FORK, EXEC and EXIT for a controlled
child were delivered, no receive-error indicators were reported, and the child
was reaped successfully. LISTEN was not formally acknowledged; IGNORE was sent
but its kernel completion is unconfirmed. Two aggregate sequence discontinuities
are preserved without interpreting them as two lost events.

This establishes narrow feasibility, not reliability, complete coverage or
permissions for every Ubuntu/service configuration. Long-running, high-volume,
concurrent-subscriber and forced-crash behavior remain untested. Upstream cleanup
concerns require conservative serialized lifecycle management.

## Provisional decision and accepted boundaries

Use cn_proc as the primary candidate for live process lifecycle notifications.
Begin a narrow production C++ adapter behind a testable native interface. Use
`/proc` for best-effort context/enrichment, existing Linux Audit for complementary
security/authentication evidence, and journald for complementary existing logs.
Neither Audit nor journald is presumed to contain a complete execution history.

The owner explicitly changes the initial implementation order from the earlier
journald-first roadmap to the production process adapter. This preserves the
historical journal plan, and the reliable end-to-end pipeline remains the next
integration objective; it is not implemented by this milestone.

ADR-001–005 remain in force: C++20 native collection/parsing/normalization, Python
normalized-event receipt with independent validation and SQLite writes, separate
processes, Unix sockets/JSON Lines, FastAPI, local dashboard and privilege
separation. This ADR does not finalize ECS fields, an IPC event contract, storage
schema, service identity, dependencies or packaging.

## Consequences

- Preserve source-native PID/thread-ID versus TGID/process-ID semantics, optional
  parent relationships, CPU/sequence context and kernel monotonic timestamps.
  Do not invent wall-clock times or required ECS fields.
- Validate untrusted native datagrams, bound work/memory, distinguish ACK from
  delivered events, report collection failures and possible/incomplete intervals.
- Treat per-CPU sequence discontinuities as diagnostic comparisons, not a loss
  count. First samples establish baselines; filtering can skip sequence positions.
- Serialize LISTEN/IGNORE, attempt explicit unsubscribe before close, do not wait
  for a final IGNORE ACK or automatically reconnect/retry as root. No kernel
  experiment is repeated as part of implementation tests.
- Process-source unavailability must not stop other adapters or authorized access
  to existing data. This milestone supplies a bounded adapter API, not application
  supervision, dashboard availability or historical recovery guarantees.
- Root-only HIDS data access remains required. Independent ordinary-user kernel
  observation on the tested host lies outside what dashboard authorization can
  prevent. Production components must not expose a public event-printing CLI.

## Open questions before broader deployment

Installed-kernel fixes and service permissions; long-running loss behavior;
namespace/boot/process identity; `/proc` races and sensitive enrichment policy;
restart/backoff and source supervision; shared normalization/IPC contracts and
timestamp policy; retention/backpressure and persistence. Revisit this provisional
mechanism using evidence, without silently replacing accepted architecture.
