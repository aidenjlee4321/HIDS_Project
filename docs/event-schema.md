# HIDS Event Schema

**Document version:** 0.2.2  
**Status:** Proposed initial schema  
**Last updated:** November 6, 2026  
**ECS reference version:** 9.5.0

The ECS reference choice is established; the field contract, custom namespace,
and machine-readable schema remain proposed and unimplemented. This document was
moved from `event-schema-design-process.md` on November 5, 2026; existing research
and candidate mappings are retained. Document versions describe this draft, not
an implemented event-schema release.

## 1. Purpose

Ubuntu logging sources produce source-native records, not ECS events. C++ collects, ingests and parses native records and produces normalized events using the shared ECS-based representation. Python receives and validates these normalized events; it does not independently collect OS records.

Different Linux sources produce different kinds of records. The canonical schema gives the analysis engine, database, API, and frontend a consistent representation so those components do not need to understand each source's original format.

The canonical event format is shared between the C++ collector and Python analysis engine.

ECS is a data model, not a requirement to use Elasticsearch or the Elastic Stack. HIDS will use ECS field names and semantics while retaining its own local processing, storage, and detection architecture.

Release scope is governed by [ADR-007](decisions/007-initial-release-scope.md)
and [release scope](release-scope.md). v0.1 implements individual-event detection
and basic categorization; correlation, detection windows/sequences and multi-event
supporting evidence are v0.2 plans. Preserving information for future use does not
make those consumers v0.1 requirements.

## 2. ECS Adoption

HIDS adopts ECS 9.5.0 as its initial reference version.

HIDS will not implement every ECS field. It will populate fields relevant to the event sources and detection requirements that the project actually supports.

When mapping source information:

1. Prefer an appropriate ECS Core field.
2. Use an ECS Extended field when it is appropriate and useful.
3. Use the HIDS custom namespace only when no suitable ECS field exists.
4. Do not invent ECS fields or repurpose existing fields to mean something different.
5. Preserve source information where practical and safe.
6. Document fields that cannot be populated reliably.

The ECS reference version and HIDS schema version are independent. Updating the HIDS schema does not automatically mean adopting a new ECS version.

## 3. Canonical Event Structure

Normalized events use ECS field names and semantics. The following fields are proposed for the initial HIDS event contract.

| Field | Purpose | Initial HIDS treatment |
|---|---|---|
| `@timestamp` | Time the activity represented by the event occurred | Proposed activity-time field where reliable source evidence supports it; handling missing/unreliable activity time remains unresolved |
| `ecs.version` | ECS version used for the event | Required; initially `9.5.0` |
| `event.kind` | High-level kind of event | Set to `event` for normalized source events |
| `event.id` | Identifier for the event | Assign or preserve a stable event identifier |
| `event.category` | Broad event category | Populate with applicable ECS category values |
| `event.type` | Standardized event type | Populate with applicable ECS type values |
| `event.action` | Specific action represented by the event | Populate where known |
| `event.provider` | Software or subsystem that produced the event | Populate where known |
| `event.module` | HIDS collection module associated with the event | Populate where applicable |
| `event.dataset` | Dataset name for the event | Populate consistently for each supported dataset |
| `event.created` | Time the event was first read or created by the collection pipeline | Populate when available |
| `event.ingested` | Time the event entered HIDS persistent storage | Populate when available |
| `event.original` | Original raw event text | Preserve when available and appropriate |

This table describes the proposed initial HIDS contract, not a claim that every listed field is mandatory in every ECS use case. Event-specific fields and requirements will be documented as source mappings are researched.

### 3.1 Event categories and types

Use ECS `event.category`, `event.type`, and `event.action` according to their documented meanings.

- `event.category` is an array of broad categories, such as `process`, `authentication`, `file`, or `network`.
- `event.type` is an array describing the kind of event, such as `start`, `end`, `creation`, `change`, `allowed`, or `denied`, where appropriate.
- `event.action` is a more specific description of the action.

Do not use a single custom `event_type` string as a substitute for these fields. Exact category/type/action combinations must be researched and documented for each event family.

### 3.2 Event and observation timestamps

HIDS must distinguish when an activity occurred from when the application observed and stored it.

- `@timestamp`: Time the activity represented by the event occurred.
- `event.created`: Time the event was first read or created by the collection pipeline, when available.
- `event.ingested`: Time the event entered HIDS persistent storage, when available.

Missing or unreliable activity timestamps are an unresolved schema decision.
Do not invent an activity timestamp or silently substitute collection time.
Collection/observation time and processing/storage time remain separate from
activity time; neither resolves missing activity time. Representation, acceptance
and any future time-dependent rule handling require further source research and explicit
schema decisions. Detection windows and event-sequence rules are v0.2 work, not
a reason to invent activity time for v0.1. No fallback policy is finalized.

Historically this draft required `@timestamp` and suggested the "best defensible
timestamp." That language did not settle missing-time handling and is superseded
by the explicit unresolved status above; no collection-time fallback is authorized.

All normalized timestamps should use an unambiguous UTC representation.

### 3.3 v0.1 traceability foundations

Preserve stable event identification, source provenance, original event type and
useful available native information; retain available timestamps with distinct
activity/observation/storage roles and process/parent identifiers where provided.
Exact field paths, required fields by event family and identifier construction
remain proposed. Source fields such as PID or per-CPU sequence are not by
themselves globally unique event identifiers. No new ECS field becomes mandatory
merely to anticipate v0.2.

A v0.1 alert must reference its one triggering normalized event and identify its
rule and matched condition. This is a logical traceability requirement, not a
final alert schema, foreign key or `alert_events` table decision. Preserve the
provenance of the native records forming that individual event under privacy and
retention controls; this does not implement a multi-event evidence store.
Evidence aggregation, complex relationships and correlation graphs are v0.2 plans.
A parent's identifier in one event is context, not a v0.1 requirement to construct
or analyze a process lifecycle graph. No detection-history query may be hidden
inside normalization or enrichment to circumvent the one-event boundary.

## 4. ECS Field Mapping

The [candidate field catalog](research/field-discovery.md) is broader than this
contract and can grow independently. Native information may remain unmapped while
protected originals retain provenance. Individual rules declare their own evidence
requirements; candidate fields are not universally required.

The following are common mappings to investigate. They are not a complete or finalized mapping of every Linux source.

| Information | ECS field |
|---|---|
| User ID | `user.id` |
| Username | `user.name` |
| Login/audit UID | Unresolved; retain native meaning and review ECS 9.5.0 rather than inventing `user.audit.id` |
| Process ID | `process.pid` |
| Parent process ID | `process.parent.pid` |
| Executable path | `process.executable` |
| Command-line arguments | `process.args` |
| Command line | `process.command_line` |
| File path | `file.path` |
| File owner | `file.owner` |
| File group | `file.group` |
| Host name | `host.name` |
| Host identifier | `host.id` |
| Source provider | `event.provider` |
| Source event code | `event.code` |
| Source dataset | `event.dataset` |

The earlier draft proposed `user.audit.id` for login UID. That unverified path is
withdrawn as a mapping candidate; the native value remains worth preserving. See
the [authentication identity discussion](research/authentication.md#7-candidate-ecs-950-mappings).

A field must only be populated when the source information has the same meaning as the ECS field. For example, different user identifiers (real UID, effective UID, login/audit UID) must not be collapsed into one field if doing so loses their meaning.

Use ECS data types. For example, user identifiers are represented as strings in ECS even when the Linux source provides a numeric UID.

## 5. HIDS Custom Fields

The proposed `hids.*` namespace is provisional, not mandatory. The custom namespace and exact field paths require an explicit design decision. Introduce a custom field only when existing ECS Core or relevant Extended fields do not adequately represent the required information.

Custom fields should be introduced only when:

- The information is needed by the collector, detection engine, storage layer, or dashboard.
- No appropriate ECS field exists.
- The meaning and data type can be documented.
- The field does not duplicate or redefine an ECS field.

Do not create a generic catch-all `metadata` object as a substitute for a considered mapping.

Potential custom information includes HIDS schema version, collection health, source-specific record references, and normalization diagnostics. Exact field names and structures remain to be designed.

The HIDS schema version must be tracked independently from `ecs.version`. Its exact location and representation remain undecided; `hids.schema.version` is only a candidate, not a required field.

## 6. Source Provenance and Original Records

HIDS should preserve enough provenance to trace a normalized event back to its native source records. Preserve potentially useful source-native information where practical even when no ECS mapping is established. Do not require immediate mapping of every native field or silently discard unresolved information; protect retained raw records under privacy and retention controls.

Where available and appropriate, retain:

- The originating subsystem or provider.
- The HIDS collection module.
- The source dataset.
- The source event code or record identifier.
- The original event text using `event.original`, when it is textual.
- A reference to any separately retained structured source record.

`event.original` is intended for the original event text. It should not be treated as an unrestricted container for arbitrary structured data. The representation, access controls, and retention policy for structured raw records remain design questions.

Original records may contain sensitive information. Preservation must follow the project's data-minimization, access-control, and retention requirements.

## 7. Event Families and Initial Collection Scope

The architecture anticipates the following event families:

| Event family | Candidate sources | Research status |
|---|---|---|
| Authentication activity | systemd journal, authentication logs, Linux Audit | Owner-reported sudo and SSH password journald observations; full fixtures, validated mappings and other login paths pending |
| Process execution | cn_proc lifecycle (provisional), `/proc` context, complementary Audit/journal | One owner-reported FORK/EXEC/EXIT experiment; [evidence and limits](research/process-connector.md); normalized mapping remains open |
| User and privilege activity | Linux Audit, systemd journal | Investigating: initial owner-reported sudo observations only; broader privilege activity and raw fixtures pending |
| Filesystem changes | Linux Audit; filesystem monitoring where needed | Not investigated |
| Service and persistence changes | systemd journal, systemd state, Linux Audit | Not investigated |
| Network activity | Source selection and scope still to be determined | Not investigated |
| System and kernel activity | systemd journal, kernel journal records | Not investigated |

Use existing Ubuntu logging and auditing. Throughout the initial release, HIDS must not modify journald configuration, PAM configuration, auditd configuration, or Linux Audit rules. This applies during installation, startup, discovery, and runtime. Do not assume auditd or required records exist. Additional logging configuration is a stretch goal requiring separate design and approval; additional filesystem collectors are future proposals. Report resulting visibility limits.

These are candidate sources, not guarantees of coverage. The schema design process must establish which events each source actually provides, which permissions are required, and what information can be collected reliably.

A single logical source event may consist of multiple records. The collector must investigate source-specific grouping requirements rather than assuming that every input record is a complete event.
This source-native parsing is distinct from v0.2 correlation of independent
normalized events; it cannot be used to hide multi-event behavioral analysis in
v0.1. The broad inventory includes future candidates and is not a promise that
all event families ship in v0.1; [release scope](release-scope.md) defines that gate.

The process adapter's internal native C++ records are not a shared normalized
contract. Preserve kernel PID/TGID roles, event-dependent parents, CPU/sequence and
monotonic nanoseconds with provenance; do not require all ECS events to contain
them or populate wall-clock `@timestamp` from these values. No schema field or
version change is implied by adding this adapter. See
[ADR-006](decisions/006-provisional-process-collection.md).

## 8. Missing, Unknown, and Inapplicable Information

HIDS must not invent values to fill gaps.

The schema design and normalization process should distinguish:

- **Unavailable:** The source does not provide the information.
- **Not collected:** The information may exist, but HIDS did not collect it.
- **Not applicable:** The field does not make sense for this event.
- **Unknown or unresolved:** The available records do not establish the value.

Fields should generally be omitted when they are not available or do not apply, unless a specific event contract requires another representation. Do not use empty strings, zero, or fabricated defaults to disguise missing information.

Where missing information affects collection reliability or interpretation, expose that limitation through documented collection or parsing diagnostics. For discovery assessments, use the finer [availability states](research/field-discovery.md#6-field-availability-classifications): Observed, Not observed in sample, Not emitted by source, Not applicable, Inaccessible, Collection failure, Unknown. The broad terms above are conceptual summaries, not interchangeable runtime states or mandatory custom event fields.

## 9. Schema Versioning and Compatibility

The ECS version and HIDS schema version must be tracked independently.

HIDS will use semantic versioning for its own schema:

| Change | Version impact |
|---|---|
| Breaking change to an existing field's meaning, type, or required structure | Major version |
| Backward-compatible addition of an optional field or event representation | Minor version |
| Documentation clarification or correction that does not change the contract | Patch version |

Examples:

- Adding an optional `process.parent.pid` field may be a minor change.
- Changing the meaning or type of an existing field is a breaking change.
- Correcting a typo in documentation without changing the contract is a patch-level change.

Adding optional fields should generally be backward compatible. Existing field meanings and data types must not be changed silently.

Breaking changes require an explicit migration or compatibility strategy. Stored historical events must remain interpretable, even if the application later supports a newer schema version.

The exact policy for accepting older event versions and migrating stored data remains to be implemented and tested.

## 10. Validation and Testing

C++ validates source-native inputs and its outgoing normalized representation. Python independently validates normalized event contracts received from C++ before security analysis and storage. Python backend ingestion means normalized-event receipt, not OS collection. Validation on either side does not replace validation on the other; exact checks and failure handling remain to be specified.

Validation should check:

- The HIDS schema version.
- The ECS version.
- Required fields for the relevant event contract.
- Field names and data types.
- Allowed values where the schema defines them.
- Timestamp format and semantics.
- Event-specific requirements.
- The handling of unknown or unsupported fields.

A machine-readable JSON Schema is planned at `shared/schemas/`. Its exact structure and versioning layout will be established after the initial event families have been researched.

Each supported event family should have sanitized example fixtures and tests for valid, invalid, incomplete, and source-specific records.

## 11. Schema Evolution

The schema is expected to evolve as HIDS gains collection sources and detection requirements.

The project will not attempt to define every possible event field before implementation.

Instead:

1. Research a specific activity and its Linux sources.
2. Collect representative source records.
3. Map available information to ECS.
4. Identify information that cannot be represented or collected.
5. Add HIDS-specific fields only where justified.
6. Validate the proposed representation.
7. Update documentation, fixtures, and tests.
8. Version the schema change.

Unmapped source information should not be silently discarded when preserving it is practical, safe, and consistent with retention requirements.

See `schema-design-process.md` for the research and change workflow.

## 12. Related Documents

- Schema research and evolution process: `schema-design-process.md`
- Detection evidence and interpretation: `confidence.md`
- Security assumptions and requirements: `threat-model.md`
- Machine-readable schema (planned): `../shared/schemas/`
- Architecture: `architecture.md`
