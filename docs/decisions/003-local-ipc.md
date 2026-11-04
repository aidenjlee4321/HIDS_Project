# ADR-003: Local Inter-Process Communication

**Status:** Accepted for initial architecture baseline  
**Date:** November 4, 2026

## Context

The C++ collector and Python backend run as separate processes on the same host.

They need a communication mechanism for transmitting normalized events.

## Decision

Use Unix domain sockets for communication between the collector and backend.

Use JSON Lines as the initial serialization format.

## Rationale recorded in the architecture

The architecture specifies local communication between processes on the same machine and does not require the collector/backend connection to use a network service.

JSON Lines is the selected initial event serialization format.

## Consequences

- The socket path and permissions must be specified.
- The protocol must define message framing and validation.
- The protocol must define how the sender learns whether an event was accepted.
- The collector must handle backend unavailability and avoid unbounded buffering.
- Protocol and event schema versions must be managed.

## Open questions

- Socket path and ownership.
- Message framing details beyond the initial JSON Lines choice.
- Acknowledgment and retry behavior.
- Backpressure and local spooling behavior.
- Whether the initial protocol needs a handshake or health message.
