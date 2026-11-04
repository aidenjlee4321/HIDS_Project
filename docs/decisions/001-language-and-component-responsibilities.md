# ADR-001: Language and Component Responsibilities

**Status:** Accepted for initial architecture baseline  
**Date:** November 4, 2026

## Context

The HIDS needs to collect operating-system events and perform detection, enrichment, and correlation.

The initial architecture separates system-level collection from higher-level analysis.

## Decision

Use:

- **C++20** for the event collector and Linux system integration.
- **Python** for ingestion, enrichment, detection, correlation, and alert generation.

The collector and analysis engine will run as separate processes and communicate through a documented interface.

## Rationale recorded in the architecture

C++ is assigned operating-system integration and event collection. Python is assigned detection, enrichment, and correlation.

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
