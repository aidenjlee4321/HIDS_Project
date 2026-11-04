# HIDS Event Schema

**Document version:** 0.1  
**Status:** Proposed initial schema  
**Last updated:** November 4, 2026

## 1. Purpose

All collection sources must produce events conforming to a shared canonical format.

Different Linux sources produce different kinds of records. The canonical schema gives the analysis engine, database, API, and frontend a consistent representation so those components do not need to understand each source's original format.

The canonical event format is shared between the C++ collector and Python analysis engine.

## 2. Proposed event structure

The initial event structure contains these fields:

| Field | Purpose |
|---|---|
| `schema_version` | Identifies the event schema version |
| `event_uid` | Unique event identifier |
| `timestamp` | Time the event occurred |
| `ingested_at` | Time the application ingested the event |
| `source` | Originating collection source |
| `event_type` | Normalized event category |
| `actor` | User or entity associated with the activity |
| `process` | Process information, when applicable |
| `object` | Object affected by the event, when applicable |
| `metadata` | Additional source-specific or event-specific information |

## 3. Example event

The following is an illustrative process execution event:

```json
{
  "schema_version": 1,
  "event_uid": "unique-event-id",
  "timestamp": "2026-11-03T20:00:00Z",
  "ingested_at": "2026-11-03T20:00:01Z",
  "source": "linux_audit",
  "event_type": "process.exec",
  "actor": {
    "username": "alice",
    "uid": 1000
  },
  "process": {
    "pid": 1234,
    "ppid": 1200,
    "executable": "/usr/bin/python3",
    "command_line": "python3 script.py"
  },
  "object": null,
  "metadata": {}
}
```

Not every event will contain every field. For example, an authentication event may contain authentication-specific information without process executable information.

## 4. Schema conventions

The initial conventions are:

1. All timestamps use UTC.
2. Every event has a unique identifier.
3. Every event identifies its originating source.
4. Event types use consistent naming conventions.
5. Optional fields may be null or omitted according to the schema.
6. Source-specific information is retained in `metadata` where appropriate.
7. Schema changes must be versioned.

## 5. Normalization

The collector's normalization layer converts source-specific records into the canonical event format.

The detection engine should not need to understand the original source format.

Initial collection sources include:

- systemd journal entries.
- Linux Audit events.
- Filesystem monitoring events, when implemented.
- Process information retrieved from `/proc`.

The exact mappings from each source into canonical fields remain to be specified as each adapter is implemented.

## 6. Event types

The architecture anticipates at least the following event categories:

- Authentication activity.
- Process execution.
- Filesystem changes.
- User and privilege-related activity.
- Relevant security-sensitive operations.

The final event type names and required fields for each type remain open design work.

## 7. Validation and compatibility

Incoming events must be validated by the Python ingestion component before being processed and stored.

The schema includes a `schema_version` field so changes can be tracked.

The following details have not yet been finalized:

- Which fields are mandatory for every event.
- Exact types and constraints for every field.
- Whether optional fields should be omitted or explicitly set to `null`.
- The policy for accepting older schema versions.
- The exact source-specific mappings.
- The machine-readable JSON Schema.

These should be settled before the event format is treated as a stable implementation contract.

## 8. Related files

- Machine-readable schema (planned): `shared/schemas/event-v1.json`
- Architecture: `architecture.md`
- IPC framing and acknowledgment behavior: to be specified as part of the collector/backend protocol.
