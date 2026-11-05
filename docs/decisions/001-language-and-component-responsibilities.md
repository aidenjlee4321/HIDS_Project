# ADR-001: Language and Component Responsibilities

**Status:** Accepted; responsibilities clarified November 5, 2026  
**Date:** November 4, 2026

## Context

The HIDS needs to collect operating-system events and perform detection, enrichment, and correlation.

The initial architecture separates system-level collection from higher-level analysis.

## Clarification — November 5, 2026

The original baseline assigned Python "ingestion" without qualifying the input.
That wording meant backend receipt of normalized events, not independent
operating-system collection. The current decision below explicitly separates
source ingestion from normalized-event receipt; the original multi-process and
language rationale remains in force.

## Decision (current)

Responsibilities:

- **C++20** owns operating-system source collection, source-native record ingestion,
  source-native parsing, event normalization, and collection-side event processing.
- **Python** owns receiving normalized events from C++, validating normalized event
  contracts, detection rules, event correlation, security analysis, enrichment,
  alert generation, and SQLite writes as established in [ADR-002](002-sqlite-storage.md).

Python event ingestion must not independently collect operating-system records.
Preserve appropriate validation on both sides of IPC: C++ validates native inputs
and its outgoing normalized representation; Python independently validates received
normalized-event contracts. Exact validation limits and failure handling remain
to be specified; neither side may assume the other makes untrusted input safe.

The collector and analysis engine will run as separate processes and communicate through a documented interface.

## Rationale recorded in the architecture

C++ handles operating-system integration and source processing through normalization. Python handles normalized-event receipt/validation, security analysis, detection, enrichment, correlation, and persistence.

The architecture is modular so components can be independently maintained and connected through documented interfaces.

## Consequences

- The collector/backend interface must be specified and versioned.
- Event representation must be shared across the components.
- The two processes need a defined startup, shutdown, and failure-handling model.
- Tests must cover communication between C++ and Python.

## Open questions

- Exact C++ library and build dependencies.
- Exact Python package and environment management.
- Process supervision and restart behavior.
