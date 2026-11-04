# HIDS Event Schema Design Process

**Document version:** 0.1  
**Status:** Initial process baseline  
**Last updated:** November 4, 2026  
**Applies to:** Research, design, validation, and evolution of the HIDS event schema

## 1. Purpose

This document defines how the HIDS event schema will be researched, evaluated, implemented, and changed over time.

The schema is a foundational interface shared by the collector, analysis engine, database, API, and dashboard. Decisions made here affect nearly every part of the application.

The goal is not to design a comprehensive schema in advance. The goal is to develop a useful, accurate, and extensible representation based on real operating-system data and actual detection requirements.

HIDS uses Elastic Common Schema (ECS) as its foundational event model. This process describes how to map real Linux events into ECS and when HIDS-specific extensions may be justified.

## 2. Design Principles

The schema design process follows these principles:

1. **Use established conventions:** Prefer ECS fields and semantics over inventing HIDS-specific equivalents.
2. **Design from evidence:** Base mappings on actual source records and documented source behavior.
3. **Start with useful coverage:** Implement a manageable set of event families before expanding.
4. **Preserve meaning:** Do not combine different concepts or identifiers merely because they look similar.
5. **Make gaps visible:** Document information that is unavailable, not collected, incomplete, or unreliable.
6. **Extend deliberately:** Add HIDS-specific fields only when ECS does not provide an appropriate field.
7. **Preserve provenance:** Retain enough source information to understand where an event came from.
8. **Evolve compatibly:** Avoid breaking existing consumers and stored events unnecessarily.
9. **Protect privacy:** Collect and retain only information that has a justified monitoring purpose.
10. **Test with real examples:** Validate mappings against representative Ubuntu event records.

## 3. Scope and References

### 3.1 Initial platform

The initial target is Ubuntu 26.04 LTS. The first implementation will support one Linux distribution.

Source behavior, field availability, package versions, permissions, and collection mechanisms must be verified on the target platform.

### 3.2 Primary reference: ECS

Initial ECS reference version: **9.5.0**.

Use the official ECS documentation and field reference to determine:

- Whether a suitable field already exists.
- The field's intended meaning.
- Its data type.
- Whether it is Core or Extended.
- Its allowed values or conventions, where defined.

Useful references:

- ECS documentation: https://www.elastic.co/guide/en/ecs/current/index.html
- ECS field reference: https://www.elastic.co/guide/en/ecs/current/ecs-field-reference.html
- ECS GitHub repository: https://github.com/elastic/ecs

The project should pin its reference version and record any later decision to update it.

### 3.3 Linux source references

Investigate the source documentation and actual output for each proposed collection mechanism.

Initial candidates include:

- systemd journal and `journalctl`.
- Linux Audit and `auditd`.
- Process information exposed through `/proc`.
- systemd service and unit information.
- Filesystem monitoring interfaces, if needed.
- Kernel journal records.

These are candidates for investigation, not a commitment to use every source.

## 4. Event Inventory

Before defining fields, identify the activities HIDS wants to observe.

The initial inventory is:

| Event family | Example activities | Initial priority |
|---|---|---|
| Authentication | Successful and failed logins, logout, session activity | High |
| Process | Process execution, termination, parent-child relationships | High |
| Privilege and identity | `sudo`, UID/GID changes, account-related activity | High |
| Filesystem | Creation, modification, deletion, permission or ownership changes | High |
| Services and persistence | Service installation, enablement, startup, scheduled tasks | Medium |
| Network | Connections, listening ports, relevant network activity | To be determined |
| System | Relevant kernel, system, and security configuration changes | Medium |

Priorities are planning guidance, not claims about detection effectiveness. They should be revisited after source feasibility and implementation effort are understood.

The inventory should grow in response to concrete monitoring and detection requirements, not simply to maximize the number of collected fields.

## 5. Research Workflow

Each event family should follow the same research process.

### 5.1 Define the activity

Describe exactly what activity we want to observe.

Avoid vague descriptions such as "monitor processes." Prefer a specific activity such as "observe process execution with its executable path, process ID, parent process ID, and executing identity where available."

Record why the activity matters to the intended monitoring and detection scope.

### 5.2 Identify candidate Linux sources

Determine which operating-system source can report the activity.

For each candidate, investigate:

- What causes a record to be emitted?
- What information does it contain?
- Does it record the activity directly or report a related consequence?
- Does it require additional configuration?
- What permissions are needed to collect it?
- Can records be lost, delayed, duplicated, or split across multiple messages?
- Does it provide a stable source identifier?
- What are its performance and storage implications?

Do not assume that a source captures an activity merely because it exposes related information.

### 5.3 Collect representative source records

Generate the activity in a controlled Ubuntu test environment and collect the actual source output.

For each event family, collect examples covering:

- Normal successful activity.
- Failed or denied activity, where applicable.
- Different users or privilege levels.
- Missing or optional fields.
- Relevant edge cases.
- Repeated or duplicate records.
- Delayed, interrupted, or incomplete collection where it can be tested safely.

Save sanitized examples as test fixtures. Remove or replace passwords, tokens, personal data, private paths, and other sensitive values before committing fixtures to the repository.

### 5.4 Understand source semantics

Before mapping fields, establish what each source field actually means.

For example, Linux may expose several distinct user identifiers:

- Real UID.
- Effective UID.
- Saved UID.
- Filesystem UID.
- Login or audit UID.

These must not be collapsed into one generic user ID. Map each value to an ECS field only when its meaning matches that field. Otherwise, document a justified HIDS extension.

Also investigate event grouping. Some sources, including Linux Audit, can represent one logical activity using multiple related records. The collector must understand how those records are associated before emitting a normalized event.

### 5.5 Map to ECS

For each source field:

1. Search the pinned ECS field reference.
2. Confirm the field's meaning and data type.
3. Prefer an appropriate ECS Core field.
4. Use an ECS Extended field if it is appropriate.
5. If neither fits, document the gap.
6. Propose a HIDS-specific field only when there is a concrete need.

Do not repurpose an existing ECS field to avoid creating a custom field.

### 5.6 Record gaps and limitations

Document:

- Information the source does not provide.
- Information that requires another source.
- Information that is available only with additional permissions or configuration.
- Information that may be unreliable.
- Events that cannot be distinguished.
- Collection blind spots and possible loss conditions.

A field should not be added to the schema merely because it would be useful if no reliable source can populate it.

### 5.7 Validate the normalized event

Create a normalized ECS-based example and test it against the proposed HIDS schema.

Verify:

- Field names and types.
- ECS semantics.
- Timestamp meaning.
- Source provenance.
- Preservation of relevant source information.
- Correct handling of missing fields.
- Correct grouping of multi-record source events.
- Compatibility with the collector/backend interface.

### 5.8 Update project artifacts

When an event family has been researched:

- Update `event-schema.md`.
- Update the coverage matrix in this document.
- Add or update sanitized source fixtures.
- Add validation and normalization tests.
- Record significant architectural decisions in an ADR when appropriate.
- Add implementation tasks to the project TODO list.

## 6. Initial Event Coverage Matrix

This matrix tracks research and implementation status. Proposed ECS mappings are starting points only; they must be verified against actual source records.

| Activity | Candidate source | Candidate ECS fields | Research status | Implementation status |
|---|---|---|---|---|
| Successful login | systemd journal, authentication logs, Linux Audit | `event.category`, `event.type`, `event.outcome`, `user.*` | Not investigated | Not implemented |
| Failed login | systemd journal, authentication logs, Linux Audit | `event.category`, `event.type`, `event.outcome`, `user.*` | Not investigated | Not implemented |
| Process execution | Linux Audit, process metadata | `process.*`, `user.*`, `event.*` | Not investigated | Not implemented |
| Process termination | Linux Audit or another verified source | `process.*`, `event.*` | Not investigated | Not implemented |
| Privilege-related activity | Linux Audit, systemd journal | `process.*`, `user.*`, `event.*` | Not investigated | Not implemented |
| File creation or modification | Linux Audit; filesystem monitoring if needed | `file.*`, `process.*`, `user.*`, `event.*` | Not investigated | Not implemented |
| Permission or ownership change | Linux Audit | `file.*`, `user.*`, `event.*` | Not investigated | Not implemented |
| Service changes | systemd and Linux Audit | `service.*`, `user.*`, `process.*`, `event.*` | Not investigated | Not implemented |
| Network activity | Source to be selected | `source.*`, `destination.*`, `network.*`, `process.*` where supported | Not investigated | Not implemented |

Status meanings:

- **Not investigated:** No source research has been completed.
- **Investigating:** Source behavior and mappings are being examined.
- **Mapped:** Source fields have been mapped and reviewed against ECS.
- **Tested:** Representative fixtures pass normalization and validation tests.
- **Implemented:** The collector and ingestion path support the activity.
- **Known limitation:** The activity is only partially observable or has a documented gap.
- **Deferred:** The activity is intentionally outside the current implementation scope.

Do not mark an activity as implemented merely because a schema representation has been drafted.

## 7. Field-Mapping Record

For each event family, maintain a mapping record with the following information:

| Item | Description |
|---|---|
| Activity | The specific behavior being observed |
| Source | The Linux source that produced the record |
| Source field | Original field name and meaning |
| ECS field | Selected ECS field, if one applies |
| Data type | Source and normalized data types |
| Transformation | Any parsing, conversion, or normalization required |
| Availability | Always present, conditional, optional, or unavailable |
| Reliability | Known limitations or ambiguity |
| Provenance | How to trace the normalized value to its source |
| Tests | Fixture and test cases validating the mapping |

### 7.1 Mapping rules

- Never infer a value solely to satisfy a required field.
- Do not merge semantically different identifiers.
- Do not silently discard useful source information.
- Do not use custom fields when an ECS field already represents the information correctly.
- Do not use ECS fields for meanings they were not designed to represent.
- Record uncertainty and collection limitations explicitly.

## 8. Schema Evolution Process

The schema is expected to evolve as the project gains real source data and detection requirements.

A schema change should follow this process:

1. Identify a concrete requirement or limitation.
2. Find a representative source record demonstrating the need.
3. Check whether ECS already provides an appropriate field.
4. Propose the smallest change that preserves the required information.
5. Determine whether the change is backward compatible.
6. Update the HIDS schema version if the event contract changes.
7. Update fixtures, validation, and regression tests.
8. Document the change and its rationale.

### 8.1 Compatibility principles

- Adding an optional field should generally be backward compatible.
- Existing field meanings and data types must not change silently.
- Breaking changes require a major HIDS schema version change.
- Consumers must handle fields that are absent.
- Stored historical events must remain interpretable.
- ECS version changes and HIDS schema version changes are separate decisions.

The exact migration and compatibility implementation will be established before the event format becomes a stable implementation contract.

## 9. Privacy and Fixture Handling

Linux event records may contain usernames, command-line arguments, filenames, IP addresses, and other sensitive information.

Research and testing must follow these principles:

- Use a controlled test machine or VM.
- Sanitize sample records before committing them.
- Do not commit credentials, tokens, private keys, or unnecessary personal information.
- Preserve only the source details needed to test parsing and mapping.
- Document when a proposed field may contain sensitive information.
- Consider data minimization and retention when deciding whether to collect a field.

## 10. Research Log

Record meaningful findings and decisions here. Keep entries concise and link to supporting fixtures, documentation, or ADRs where available.

### Entry template

```text
Date:
Event family:
Activity investigated:
Source(s) examined:
Representative fixture(s):
ECS fields considered:
Mapping decision:
Information unavailable or uncertain:
Permissions/configuration required:
Tests added:
Open questions:
Related ADR or issue:
```

### Research entries

No event-family research has been completed yet. Initial status is recorded in the coverage matrix above.

## 11. Completion Criteria

An event family is ready for initial implementation when:

- The activity is clearly defined.
- At least one viable source has been identified.
- Representative source records have been collected and sanitized.
- Relevant source fields and their meanings are understood.
- ECS mappings have been reviewed.
- Missing information and source limitations are documented.
- The normalized representation has been validated.
- Test fixtures and regression tests exist.
- Required permissions and collection configuration are understood.

Completion does not mean the event family captures every possible detail. It means the supported behavior and its limitations are understood well enough to implement honestly.

## 12. Related Documents

- Current event contract: `event-schema.md`
- Detection evidence and interpretation: `confidence.md`
- Security assumptions and requirements: `threat-model.md`
- Machine-readable schemas and fixtures: `../shared/schemas/`
- Immediate work items: `../TODO.md`
