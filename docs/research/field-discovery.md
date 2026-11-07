# Field discovery and detection coverage

**Status:** Established design principles; proposed implementation, not implemented  
**Documented:** November 5, 2026  
**Last updated:** November 7, 2026  
**Initial ECS reference:** 9.5.0

## 1. Purpose and design philosophy

Maintain a broad, evolving catalog of potentially useful information, then
investigate what the existing Ubuntu environment provides. Do not define what
Ubuntu must emit by choosing a narrow schema first. Equally, a large catalog is
not permission to collect every value. Discover broadly; retain deliberately.

The catalog is a research tool, separate from the normalized event schema and
from each detection's evidence requirements. Catalog entries can be added without
changing the schema. No source, host, or individual event is expected to contain
every candidate. Useful fields may remain candidates even when the initial logging
configuration cannot provide them.

Established requirements in this document govern discovery, evidence handling,
privacy, and responsibility boundaries. Report layouts, example rule requirements,
storage structures, schedules, and runtime status names remain proposals. No
analyzer, capability manager, collector, or coverage dashboard is implemented.

Related documents: [architecture](../architecture.md),
[schema process](../schema-design-process.md), [schema draft](../event-schema.md),
[authentication observations](authentication.md), [threat model](../threat-model.md),
and [evidence policy](../confidence.md).

Temporary [Ubuntu research scripts](../../scripts/research/README.md) can gather
bounded inventory and controlled process observations for this methodology. They
are manually run research aids, not the capability manager or field analyzer.
One owner-reported [cn_proc lifecycle experiment](process-connector.md) now supplies
scoped Ubuntu evidence; broad validation and sanitized full fixtures remain pending.

## 2. Relationship to capability discovery

No separate capability-discovery specification existed when this document was
written. These boundaries establish the design without inventing prior research.
The named components are logical responsibilities, not required new processes.

Graceful degradation is an initial-release requirement. If a collection source
is missing, inaccessible, or failing, other functioning sources must continue
operating. The dashboard and stored data must remain accessible under the existing
authorization policy. Report the affected source's status and limitations of rules
that require unavailable information; recovery must be detectable. This does not
promise historical backfill. Concurrency, process isolation, and supervision
mechanisms remain undecided.

| Responsibility | Determines | Does not establish |
|---|---|---|
| System Capability Manager | Which existing sources/mechanisms are present, enabled, accessible to the actual collector identity, and usable; source-state changes | That a particular event or field will be emitted |
| Field Discovery and Coverage Analyzer | What information inspected records actually contain, source-native types, mapping gaps, scoped availability, and field limitations | A security score or universal detection readiness |
| Detection engine | Whether each rule's declared requirements are met for the applicable event/window; limitations when evidence is missing | That a quiet event stream means no relevant activity occurred |
| Dashboard/API | Explain source health, field observations, rule limitations, evidence, and recovery state to the authorized user | Human authorization merely because a connection is local |

The architecture must support startup discovery, periodic reassessment, changes
in source availability, collection-gap/failure identification, and recovery when
sources become available again. For first run, the accepted [product experience](../product-experience.md#first-run-experience)
requires metadata/non-collecting access discovery, explained draft selections and
explicit confirmation before any security-event sampling, event-reader initialization
or subscription. Before confirmation, field information is documented possibility
or scoped prior authorized evidence, not current sampled/Observed values. Static
capability/access evidence is distinct from demonstrated runtime functionality.

After confirmation for selected sources (or separately authorized research), a
proposed assessment lifecycle is: inspect source/access state, inspect bounded
samples and health signals, update scoped field evidence, reevaluate affected
individual rules and publish changes with reasons/freshness. Unselected or newly
discovered sources must not start collecting as a side effect of reassessment.
A source returning does not erase a prior gap or prove historical backfill.
Revalidate access and record continuity before describing monitoring as restored.

Actual collector identities must be tested; a root research session's ability to
read logs does not prove that an unprivileged service can read them. Discovery
must remain read-only toward system sources/configuration and must not grant
privileges, enable logging, install packages, or change journald configuration,
PAM configuration, auditd configuration, or Audit rules. The initial-release
restriction applies during installation, startup, discovery, and runtime; extra
logging configuration requires separate design and approval. HIDS application
files/services are distinct from Ubuntu logging configuration. Polling intervals, change triggers,
probe design, process placement, persistence, and recovery guarantees are open.

## 3. Source-native fields versus ECS

Ubuntu sources emit native records, not ECS events. C++ owns collection, native
ingestion/parsing, normalization and collection-side processing. Python receives
and validates normalized contracts, performs detection/correlation/analysis, and
owns SQLite writes; it does not independently collect OS records. Preserve
appropriate input/output validation in C++ and independent contract validation
in Python across IPC.

Keep three information layers conceptually separate:

| Layer | Examples | Treatment |
|---|---|---|
| Source-native | Audit `auid`, `uid`, `acct`, `ses`, `addr`, `terminal`, `res`, `exe`; journal `_PID`, `_UID`, `_EXE`, `_COMM`, `_SYSTEMD_UNIT`, `_AUDIT_LOGINUID`, `MESSAGE` | Preserve names, values where justified, encoding, source origin, and record linkage; do not assert every listed field was observed |
| Normalized ECS | `process.pid`, `user.id`, `event.outcome` where meanings match | Use ECS 9.5.0 Core and relevant Extended fields; ambiguous mappings remain unresolved |
| Detection requirements | An authentication rule needs a result, usable identity key, time, and evidence references | Declare requirements by rule and applicable event family; do not demand them on all events |

Do not silently discard potentially useful unmapped native information; preserve
it and provenance where practical under privacy controls. Missing or unreliable
activity timestamps remain an unresolved schema decision. Keep activity, collection
and processing/storage times separate; do not invent activity time or silently
substitute collection time. No fallback policy has been finalized.

Source fields with similar names may describe different entities. Journal metadata
about the emitting process can differ from an account named inside `MESSAGE`.
Audit UID, audit login UID, effective UID, and target account are not interchangeable.
Keep individual Audit events distinct from a correlated sudo activity and preserve
any multi-record event grouping separately from cross-event correlation.

Preserve source-native information where practical even before mapping is resolved,
subject to privacy and retention controls. Raw records and normalized events are
distinct artifacts connected by provenance; their storage/link representation is
undecided. Textual `event.original` is not a catch-all structured-data container.
A declared capture/export format's types may differ from semantic types: record
both rather than coercing away information. Allow for repeated or binary fields.

The upstream [systemd 259 field reference](https://github.com/systemd/systemd/blob/v259/man/systemd.journal-fields.xml)
documents journal field possibilities and representation caveats; this is not
proof of presence in our VM samples. The pinned
[ECS 9.5.0 definitions](https://github.com/elastic/ecs/tree/v9.5.0/schemas)
are the mapping reference. In particular, consult the
[process definitions](https://github.com/elastic/ecs/blob/v9.5.0/schemas/process.yml)
and [file definitions](https://github.com/elastic/ecs/blob/v9.5.0/schemas/file.yml)
when reviewing candidates. Names below are mapping proposals, not approved
contracts or a complete field-reference audit. Prefer existing ECS semantics;
custom fields require a demonstrated gap and explicit design review. `hids.*`
remains provisional. Never invent an ECS path to fill a gap.

## 4. Candidate field catalog

Catalog names below are human-readable research keys, **not schema field paths**.
Each row is one candidate concept; source alternatives do not imply equivalence.
“Investigate” means a potential source to examine, not a promise it provides it.
Snapshot sources describe current context, not necessarily event-time history.
Additional probes, integrity scans, or telemetry are future possibilities, not
initial-release collection requirements.

Expected types are semantic research expectations, not observed serialization or
final schema types. `ID string` preserves identifier semantics; `time` still needs
units, clock, timezone, precision, and reliability research. Review ECS types before
normalization. `Unresolved` means no mapping selected, not a proven ECS gap.

Research status legend:

- **O-A:** Observed information in the owner-reported Audit authentication sample;
  complete raw field layout/types remain unverified.
- **O-J:** Observed information in the owner-reported journal authentication sample;
  sudo key versus message origin remains unverified; see O-S for SSH.
- **O-S:** Observed in the owner-reported SSH journald follow-up (Ubuntu 26.04.1,
  systemd 259.9, OpenSSH 10.2p1); native keys and message content distinguished,
  complete exports/types and per-record availability pending.
- **O-P:** Observed in one owner-reported ordinary-user cn_proc lifecycle experiment;
  full report/compiler provenance and broader coverage pending.
- **O-E:** Reported experiment environment/status, not an event field observation.
- **D-J:** Documented journal-field possibility in the reference above, not observed
  as that exact key in supplied records.
- **U:** Unknown; candidate for investigation, no established VM availability.

These evidence labels do not replace the scoped availability states in section 6.
Missing sample transcripts mean that unmentioned candidates remain Unknown, not
“Not emitted” or automatically “Not observed in sample.” Sensitive concerns apply
independently of status or rule importance; an apparently ordinary field can become
sensitive in combination with others.

### Event identification and timestamps

| Candidate | Description / potential source | Proposed ECS equivalent | Expected type | Detection use | Sensitivity | Status |
|---|---|---|---|---|---|---|
| Source event type | Audit `USER_AUTH`, etc. | `event.code` | string | Select authentication versus session steps | Activity | O-A |
| Audit serial | Source event serial, not whole sudo activity | Unresolved identity scheme | ID string | Record grouping and deduplication | Linkability | O-A |
| Activity timestamp | Investigate record timestamps | `@timestamp` | time | Ordering, time windows | Behavioral timeline | U |
| Source clock/precision | Investigate timestamp provenance | Unresolved | string + units | Avoid invalid cross-source ordering | Low alone | U |
| Observation time | Future collector clock | `event.created` | time | Measure observation delay | Behavioral timeline | U |
| Storage arrival time | Future backend clock | `event.ingested` | time | Pipeline-gap analysis | Behavioral timeline | U |
| Journal cursor | SSH journal `__CURSOR` key observed; value not supplied | Unresolved | opaque string | Checkpoint continuity and overlapping-query deduplication | Linkability | O-S |
| Message type ID | Journal `MESSAGE_ID` | `event.code` if semantically suitable | ID string | Stable message classification | Application use | D-J |

Additional SSH native candidates (expected semantic types; export types unverified):

| Candidate | Observed source | Candidate mapping / limitation | Expected type | Sensitivity |
|---|---|---|---|---|
| Journal realtime time | `__REALTIME_TIMESTAMP` | Unresolved clock/role mapping; no automatic activity-time substitution | time with units pending | Behavioral timeline |
| Journal monotonic time | `__MONOTONIC_TIMESTAMP` | Preserve with boot scope; not wall-clock `@timestamp` | duration/ticks with units pending | Behavioral timeline |
| Emitter GID | `_GID` | Credential role/mapping unresolved; distinct from account group | ID string | Sensitive membership |
| Journal unit | `_SYSTEMD_UNIT` | Preserve native unit; service mapping unresolved | string | Service inventory |
| Systemd session | Reported association `5`; native key unspecified | Unresolved; distinct from Audit session `5` and POSIX session | ID string | Sensitive linkability |
| SSH protocol token | Message `ssh2` | Mapping unresolved; does not establish transport/cipher | string | Activity |
| Logout-related diagnostic | `syslogin_perform_logout: logout() returned an error` | Meaning unresolved; not evidence of failed closure | string | Session history |

All rows above have O-S scope. SSH PAM message `uid=0`, `euid=0`, `tty=ssh`,
`user=test-user`, and session-opening name/UID roles are also observed; see the
[sanitized SSH record summary](authentication.md#7a-ssh-journald-follow-up).
They do not establish equivalence with emitter `_UID`/`_GID`. Audit session `5`
is reported as associated context, not a supplied corresponding Audit record set.

### Host and operating system

| Candidate | Description / potential source | Proposed ECS equivalent | Expected type | Detection use | Sensitivity | Status |
|---|---|---|---|---|---|---|
| Host identifier | Investigate existing host metadata | `host.id` | ID string | Scope correlations | Persistent identifier | U |
| Host name | Investigate journal/system metadata | `host.name` | string | Attribute events | Device/person names | U |
| Boot identifier | SSH journal `_BOOT_ID` key observed | Unresolved | ID string | Bound PID/time reuse | Session linkability | O-S |
| OS name/release | Reported Ubuntu 26.04.1 LTS | `host.os.name`, `host.os.version` | strings | Scope source behavior | Fingerprinting | O-E |
| Kernel release | Reported `7.0.0-42-generic` | `host.os.kernel` | string | Compatibility limitations | Fingerprinting | O-E |
| CPU architecture | Reported `aarch64` | `host.architecture` | string | Interpret platform-specific data | Fingerprinting | O-E |
| Virtualization context | Investigate existing VM metadata | Unresolved | string | Explain source differences | Infrastructure details | U |

### User and identity

| Candidate | Description / potential source | Proposed ECS equivalent | Expected type | Detection use | Sensitivity | Status |
|---|---|---|---|---|---|---|
| Record UID | Audit `uid`; role must be verified | `user.id` or `process.real_user.id` only if justified | ID string | Attribute subject identity | Sensitive identity | O-A |
| Journal UID key | SSH journal `_UID`; distinct from message `uid`/`euid` | Identity mapping unresolved pending credential semantics | ID string | Identify emitting process credentials | Sensitive identity | O-S |
| Effective UID | Failed journal observation; raw origin unknown | `process.user.id` | ID string | Explain process privilege | Sensitive identity | O-J |
| Audit login UID | Audit `auid` semantic observation | Unresolved; not `user.audit.id` | ID string | Login attribution across privilege changes | Sensitive identity | O-A |
| Journal login UID key | Journal `_AUDIT_LOGINUID` | Unresolved | ID string | Compare attribution across sources | Sensitive identity | D-J |
| Original username | Successful sudo journal observation | `user.name` after actor review | string | Actor-based grouping | Sensitive identity | O-J |
| Account acted on | Audit `acct`; event-dependent role | `user.name` or `user.target.name` after review | string | Distinguish authenticating and target account | Sensitive identity | O-A |
| Target username | Successful sudo journal target root | `user.target.name` | string | Detect unexpected account transitions | Sensitive identity | O-J |
| Real/effective GID | Investigate source credentials | `process.real_user.group.id` / `process.user.group.id` if applicable | ID strings | Group-based privilege context | Sensitive membership | U |
| Supplementary groups | Investigate existing process/account context | Unresolved | list of IDs | Permission interpretation | Sensitive membership | U |
| Saved/filesystem UID | Investigate distinct Linux credentials | `process.saved_user.id` for saved UID; filesystem UID unresolved | ID strings | Privilege transition context | Sensitive identity | U |

### Process information

| Candidate | Description / potential source | Proposed ECS equivalent | Expected type | Detection use | Sensitivity | Status |
|---|---|---|---|---|---|---|
| Sudo PID | Audit and journal experiment PIDs | `process.pid` | integer | Link sudo steps within scope | Linkability | O-A, O-J |
| Journal PID key | SSH journal `_PID=5855` | `process.pid` | integer | Emitting process context | Linkability | O-S |
| Executable path | Audit executable information; failed journal executable | `process.executable` | string | Executable-based rules | Private paths | O-A, O-J |
| Journal executable key | SSH `_EXE=/usr/lib/openssh/sshd-session` | `process.executable` | string | Compare executable attribution | Private paths | O-S |
| Command name | SSH `_COMM=sshd-session`; `sshd` query missed these records | `process.name` | string | Process selection | Application use | O-S |
| Full command line | Failed journal `sudo id` observation | `process.command_line` | string | Explain invoked action | Sensitive; credentials possible | O-J |
| Argument vector | Investigate existing execution records; not reconstructible reliably from display text | `process.args` | list of strings | Argument-sensitive rules | Sensitive; credentials possible | U |
| Working directory | Successful journal observation | `process.working_directory` pending semantic review | string | Execution context | Private paths | O-J |
| Process start time | Investigate existing records or contextual snapshot | `process.start` | time | Disambiguate reused PIDs | Behavioral timeline | U |
| Exit status | Investigate completion records | `process.exit_code` | integer | Separate request from completion | Activity | U |
| Environment keys/values | Future restricted research; no blanket collection | Unresolved | names / strings | Selected execution context | Sensitive; tokens/passwords possible | U |

### Process connector observations (O-P scope)

| Native concept | Observed information | Mapping / limitation |
|---|---|---|
| Lifecycle kind | FORK, EXEC, EXIT | Candidate process event classification; action/type contract unresolved |
| Kernel PID / TGID | Child `13184` / `13184` | Preserve thread ID versus process ID; equal in this single-thread test only |
| Parent PID / TGID | `13178` / `13178` on FORK/EXIT | Preserve roles; EXEC does not provide parents |
| Emitting CPU | FORK CPU 2, EXEC/EXIT CPU 3 | Source provenance; not permanent process affinity |
| Connector sequence | 1, 2, 3 with CPU scope | Not a global event ID or an exact loss counter |
| Kernel monotonic time | Actual nanosecond values in [research record](process-connector.md#actual-reported-results) | No wall-clock substitution or mandatory ECS mapping |
| Child termination | Successfully reaped with status 0 | User-space experiment observation; do not equate with a normalized native EXIT code |

These additions do not establish executable-path, command-line or credential
availability from the requested lifecycle mask. `/proc` enrichment remains
best-effort future work; short-lived processes can disappear before inspection.
The live subscription is distinct from historical source records, and ordinary-user
access in this experiment does not prove access for the eventual service identity.

### Parent and child relationships

| Candidate | Description / potential source | Proposed ECS equivalent | Expected type | Detection use | Sensitivity | Status |
|---|---|---|---|---|---|---|
| Parent PID | Observed cn_proc FORK/EXIT parent ID; retain PID/TGID roles | `process.parent.pid` only after role review | integer | Parent-child patterns | Linkability | O-P |
| Parent executable | Investigate parent context at event time | `process.parent.executable` | string | Unexpected launch origin | Private paths | U |
| Parent start time | Investigate time-scoped parent identity | `process.parent.start` | time | Avoid parent PID reuse errors | Behavioral timeline | U |
| Child execution identity | Investigate actual child execution evidence | Separate child event's `process.pid`; relationship unresolved | ID / integer | Distinguish sudo request and child execution | Linkability | U |
| Ancestry / process entity key | Investigate reliable source IDs or derived provenance | `process.entity_id` only with documented construction | ID string / links | Multi-step execution chains | Linkability | U |

### Authentication and session information

| Candidate | Description / potential source | Proposed ECS equivalent | Expected type | Detection use | Sensitivity | Status |
|---|---|---|---|---|---|---|
| Authentication result | Audit `res` semantic result; journal PAM result | `event.outcome` for that check | string | Failed/successful check patterns | Security history | O-A, O-J |
| Authentication operation | Audit `USER_AUTH` and journal PAM context | `event.action` naming unresolved | string | Distinguish checking credentials from opening session | Security history | O-A, O-J |
| Authentication mechanism | SSH Failed/Accepted messages report `password`; PAM reports `pam_unix(sshd:auth)` | Unresolved; method and module/service are distinct | string | Differentiate mechanisms | Security configuration | O-S |
| Grantors | Audit observation `?` | Unresolved | raw string / parsed list if justified | Explain authentication path | Security configuration | O-A |
| Failure reason | Investigate explicit error information | `event.reason` if supported | string | Explain failed checks | Account/policy details | U |
| Attempt sequence/retry marker | Investigate source markers, not inferred from duplicates | Unresolved | ID / integer | Count genuine attempts | Behavioral timeline | U |
| Audit session ID | Audit `ses` semantic observation | Unresolved; not POSIX session ID by assumption | ID string | Scope login attribution | Sensitive linkability | O-A |
| Terminal | Audit and journal `/dev/pts/0` observations | Unresolved | string | Local/session context | Sensitive linkability | O-A, O-J |
| Session open/close | Audit `USER_START` / `USER_END`, journal open | `event.action`; classification pending | string + time if supplied | Session lifecycle patterns | Behavioral timeline | O-A, O-J |
| POSIX session/process group | Investigate `/proc` or existing event context | Process session/group leader fields only if equivalent | IDs | Process session relationships | Linkability | U |
| Desktop/remote session kind | Investigate existing session records | Unresolved | string | Differentiate login paths | User behavior | U |

### Network information

| Candidate | Description / potential source | Proposed ECS equivalent | Expected type | Detection use | Sensitivity | Status |
|---|---|---|---|---|---|---|
| Authentication peer address | SSH message address and PAM `rhost=127.0.0.1` | `source.ip`; original `source.address` after role validation | IP or original string | Authentication origin; loopback only observed | Sensitive identifier | O-S |
| Source address/port | SSH messages report client `127.0.0.1` port `60018` | `source.ip`, `source.port` after parsing | IP + integer | Connection origin; not server port | Sensitive identifier | O-S |
| Destination address/port | Investigate existing connection/application records | `destination.ip`, `destination.port` | IP + integer | Unexpected destinations | Sensitive identifier | U |
| Protocol/transport | Investigate existing network records | `network.protocol`, `network.transport` | strings | Protocol-specific behavior | Activity | U |
| Direction | Investigate host-relative network context | `network.direction` | string | Incoming/outgoing patterns | Activity | U |
| DNS question | Investigate already available resolver/application logs | `dns.question.name` | string | Domain-based investigation | Sensitive browsing/service history | U |
| Byte counts | Investigate existing flow/accounting data | `source.bytes`, `destination.bytes` if equivalent | integers | Data-transfer context | Usage patterns | U |
| Listening endpoint / socket owner | Investigate existing socket context; snapshots are not history | Endpoint and process fields after review | endpoint + process ID | Unexpected listeners | Service inventory | U |

### Filesystem, file metadata, and integrity

| Candidate | Description / potential source | Proposed ECS equivalent | Expected type | Detection use | Sensitivity | Status |
|---|---|---|---|---|---|---|
| Affected file path | Investigate existing file-related logs | `file.path` | string | Sensitive-path changes | Sensitive paths | U |
| File operation | Investigate explicit operation records | `event.action` | string | Distinguish create/change/delete | Activity | U |
| Rename source/target | Investigate paired path evidence | Unresolved role mapping | strings | Persistence/rename chains | Sensitive paths | U |
| Inode/device | Investigate existing file records or metadata | `file.inode`, `file.device` if equivalent | ID strings | Disambiguate path reuse | Linkability | U |
| Symlink target | Investigate existing metadata | `file.target_path` | string | Redirected sensitive paths | Sensitive paths | U |
| File owner/group | Investigate existing file metadata | `file.uid`, `file.gid`, `file.owner`, `file.group` | IDs / names | Ownership changes | Sensitive identity | U |
| File permission mode | Investigate existing mode information | `file.mode` | string | Unexpected writable/set-ID files | Security configuration | U |
| File size/type | Investigate existing metadata | `file.size`, `file.type` | integer / string | Explain changed objects | Inventory | U |
| File modification/change times | Investigate existing metadata; preserve clock semantics | `file.mtime`, `file.ctime` if equivalent | times | Change timelines | Behavioral timeline | U |
| File digest / algorithm | Future scoped integrity research; may require extra reads | `file.hash.sha256` for that algorithm | digest string | Content-change detection | Sensitive content fingerprint | U |
| Baseline digest and provenance | Future baseline design, not observed | Unresolved | digest + reference | Explain integrity comparisons | Sensitive fingerprint | U |
| ACL / extended attributes | Future scoped metadata research | Unresolved | structured entries | Permission/persistence changes | Sensitive policy/identity | U |
| Package ownership / verification | Investigate existing package metadata; no package installation | `package.name`, `package.version` for package identity; verification unresolved | strings + result | Explain expected installed files | Software inventory | U |

### Services, systemd, privileges, and permissions

| Candidate | Description / potential source | Proposed ECS equivalent | Expected type | Detection use | Sensitivity | Status |
|---|---|---|---|---|---|---|
| Emitting systemd unit | Journal `_SYSTEMD_UNIT` | Unresolved; unit is not automatically `service.name` | string | Attribute service logs | Service inventory | D-J |
| Service name/state | Investigate existing service messages/state | `service.name`, `service.state` if equivalent | strings | Unexpected service transitions | Service inventory | U |
| Unit definition path | Investigate existing unit metadata | `file.path` only for a file-centric event | string | Persistence investigation | Private paths | U |
| Unit invocation identifier | SSH journal `_SYSTEMD_INVOCATION_ID` key observed | Unresolved | ID string | Bound service restarts | Linkability | O-S |
| Service enablement / override | Investigate existing records/configuration context | Unresolved | state / path | Persistence changes | Security configuration | U |
| Credential lifecycle step | Audit `CRED_REFR` observed | `event.action` naming unresolved | string | Separate credential setup from authentication | Security history | O-A |
| Privilege transition | Investigate before/after credentials; target root alone insufficient | User/effective/target fields where justified | identity pair + operation | Explain privilege changes | Sensitive identity | U |
| Capability sets | Investigate existing process metadata | Unresolved | list of capability names | Excess process permissions | Security configuration | U |
| Authorization decision | Investigate explicit policy decisions; not inferred from EUID | `event.outcome`, `event.reason` if equivalent | result + string | Denied privilege operations | Policy/account details | U |
| Confinement profile / denial | Investigate existing AppArmor or other security messages | Unresolved | profile + operation + result | Explain sandbox violations | Security policy/paths | U |

### Source, collection, correlation, and future context

| Candidate | Description / potential source | Proposed ECS equivalent | Expected type | Detection use | Sensitivity | Status |
|---|---|---|---|---|---|---|
| Original message / record | Journal `MESSAGE` documented; complete records not supplied | `message` for message; `event.original` for appropriate original text | text / protected structured record | Explain/reparse observations | Sensitive; arbitrary secrets possible | D-J |
| Source provider/dataset | Future adapter metadata plus verified source identity | `event.provider`, `event.dataset` | strings | Scope parsing/rules | Software inventory | U |
| Transport / origin path | Investigate journal transport or existing log location | `log.file.path` only for actual file origin | string | Diagnose source differences | Private paths | U |
| Collector identity/version | Future collector metadata | `agent.id`, `agent.version` if equivalent | strings | Reproducibility | Persistent identifier | U |
| Source versions | Reported systemd, auditd, sudo-rs versions | Unresolved role-specific mapping | strings | Explain source behavior | Fingerprinting | O-E |
| Access result / denial reason | Future read-only capability probe | Unresolved | result + reason | Explain inaccessible evidence | Permissions/inventory | U |
| Parser/normalization diagnostics | Future collection/validation results | `error.message` only if equivalent | reason + field references | Expose processing failures | May echo sensitive source values | U |
| Checkpoint / gap interval | Future collector continuity observations | Unresolved | opaque ID + times | Bound incomplete rule windows | Behavioral timeline | U |
| Audit lost/backlog | Reported Audit status: both zero at check | Unresolved | counters + observation time | Diagnose collection limitations | Operational state | O-E |
| Normalized event identity | Future deduplication design | `event.id` | ID string | Evidence references | Linkability | U |
| Source record reference | Future source/cursor/serial linkage | Unresolved | opaque reference | Trace normalized values to originals | Linkability | U |
| Correlated activity identity | Future link across distinct events | Unresolved | ID string + references | Sudo sequence or multi-event pattern | Sensitive linkability | U |
| Container / namespace context | Investigate existing metadata where relevant | `container.id` for actual container ID; namespace unresolved | IDs | Prevent cross-namespace PID confusion | Infrastructure identity | U |
| Scheduled task definition | Investigate existing scheduler records | Unresolved | path / command / schedule | Persistence context | Sensitive commands and identities | U |
| Software install/change | Investigate existing package-manager logs | `package.*` fields after review | package identity + operation | Explain administrative changes | Software inventory | U |
| Time synchronization state | Investigate existing clock/service state | Unresolved | status + offset/time | Explain uncertain ordering | Operational state | U |
| User investigation notes | Future explicitly supplied context, not OS evidence | Unresolved, separate interpretation | text | Explain legitimate activity | Sensitive free text | U |

All U entries remain Unknown, including candidates that would need configuration
not allowed initially. No row establishes a requirement to enable a source.
D-J establishes documented possibility only. O-A/O-J/O-S/O-P/O-E are bounded by their
reported experiment scopes; they are not availability promises for other events.

## 5. Field importance and sensitivity

| Classification | Meaning within a specified detection |
|---|---|
| Required | The detection cannot operate correctly without this information |
| Important | Its absence substantially limits that detection; disclose the limitation |
| Optional | Additional useful context |
| Sensitive | Independent privacy consideration, combinable with any importance level |

Declare importance per rule, event role, and where relevant correlation window.
A peer IP may be Required for a rule about repeated failures from one IP, Optional
for failures grouped by account, and Not applicable to a purely local event.
No global field ranking, numerical field-importance score, confidence score, or
automatically assigned confidence label is permitted. No absence of a Sensitive
marker means that retention is automatically safe.

## 6. Field availability classifications

Availability is scoped to host/environment, source/version/configuration, access
identity, event family, investigated conditions, time window, and record/sample.
Record the evidence and last assessment time. Documentation possibilities, field
availability, mapping maturity, and retention policy are separate dimensions.

| State | Meaning / evidence needed |
|---|---|
| Observed | Actually found in inspected records; cite the record/sample and distinguish owner-reported observations from inspected raw fixtures |
| Not observed in sample | Absent from records actually examined; broader availability unknown; record sample boundaries |
| Not emitted by source | Established non-emission under stated conditions, supported by source semantics and investigation; never infer from one missing field |
| Not applicable | The information has no meaning for this particular event or role |
| Inaccessible | Information may exist, but the actual collector lacks access; document the denied path/operation and identity |
| Collection failure | Retrieval, parsing, transport, or processing failed; record which stage and affected interval |
| Unknown | Insufficient evidence for another state, including untested candidates |

Classify source absence/disabled configuration at the capability layer and explain
its effects in field assessments; it is not automatically proof of non-emission
in every configuration. Preserve separate evidence for conflicting states across
records or sources instead of collapsing them to one universal field state.
“Observed” once does not establish continuous availability or current health.
A discovered-but-not-retained value needs a separate retention-policy annotation;
it is not an access failure. A malformed value can be observed while its parsing
failed. Document both facts rather than replacing presence with validity.

An empty history does not establish functioning monitoring. Missing data does not
establish that an activity did not occur. Avoid empty strings, zeroes, guessed
values, and inferred negatives as substitutes for these distinctions. The older
schema draft's broad missing-data terms must be read with these finer research
states; no new mandatory per-event custom diagnostic fields are introduced here.

The product's recommendation/preselection is a usability choice, not a source
ranking or proof of coverage. Explain usable/partial/unavailable/unsupported/
unverified evidence to the authorized user, preserve draft versus confirmed versus
runtime state and allow subsets. Runtime initialization can fail after confirmation.
None of these distinctions finalizes the assessment schema or creates a capability
manager implementation.

## 7. Initial collection methodology

For every controlled experiment:

1. Identify the exact activity, detection objective, and expected experiment
   boundaries; distinguish activity expectation from expected emitted fields.
2. Identify relevant existing sources and record capability/access evidence,
   versions, collector identity, and existing logging configuration.
3. Generate a controlled example in an authorized test environment; record exact
   commands and outcomes. Do not change logging configuration to meet expectations.
4. Collect available records from all relevant sources using recorded queries,
   formats, time ranges, and read identities; record failed collection attempts.
5. Preserve representative originals in the protected research environment with
   bounded retention, access controls, and source identifiers. Do not put private
   originals in Git; retain only justified values.
6. Extract exact native field names, original encodings/serialization types,
   multiplicity, semantic types, and origin (metadata versus parsed message).
7. Compare observed concepts with the catalog; add justified candidates without
   changing the core schema solely because a new native key exists.
8. Record scoped availability, missingness reasons, source health, and limitations.
9. Propose ECS mappings only where meaning and type are justified against 9.5.0;
   preserve unresolved native information without forcing a custom normalized field.
10. Identify missing information that would improve specific rules; distinguish
    existing-source alternatives from configuration changes or future collection.
11. Record unanswered questions, sanitizer transformations, fixture references,
    follow-up experiments, and which results have or have not been validated.

The [sudo research](authentication.md) is an initial example, not a complete
execution of this protocol. It reports UID, login UID, account, session, terminal,
PID, executable, authentication result, and other context. Exact journal keys,
source serialization, timestamps and complete source records remain unavailable
for sudo in the documentation. The SSH follow-up separately reports `_UID` and
other native keys as observed; a message UID alone would not establish that. The reported `?` grantors value is present but unresolved, not a
known named grantor. Audit serials 407–411 describe five separate events; linking
them into one sudo activity must not erase that distinction. Audit status zeroes
and absence of explicit rules do not prove complete execution auditing.

The SSH follow-up establishes native key presence and message-level method/client
port information in one scoped sample. Its three selectors overlap; deduplicate
retrievals of the same source record separately from correlating distinct PAM and
SSH records that appear to describe one failure. Preserve both failure records
without automatically counting two attempts. Unit/boot/cursor/time key presence
does not supply their values, guarantee continuity, or finalize mappings. The
logout diagnostic remains unresolved, and the earlier `sshd` query miss is a
selection gap rather than evidence of absent SSH activity.

## 8. Field coverage assessment

A future descriptive report should retain evidence scope rather than output a
single percentage of security or overall monitoring coverage. Proposed contents:

- Environment, source states/access identities, assessment window, catalog/rule
  revisions, freshness, and unresolved health checks.
- Fields observed and their sample references, types, unresolved mappings, and
  persistence/redaction policy; record sample absence separately from non-emission.
- Unavailable, inaccessible, and failed collection paths with concrete reasons;
  identify configuration limits without automatically changing configuration.
- Rule-specific Required/Important/Optional information and affected event roles;
  explain which rules cannot operate, which have reduced context, and which
  limitations remain even when minimum requirements are present.
- Existing alternative sources worth investigating, the permissions they need,
  and whether their historical/time semantics fit the rule. Recommendations may
  explain logging gaps but must identify configuration changes as stretch-goal
  options requiring separate design/approval, never execute them or promise that they solve a gap. Monitoring coverage recommendations are within scope; threat remediation recommendations are outside initial scope.
- Source changes, stale assessments, interrupted intervals, and recovery/backfill
  status. Do not claim that source recovery retroactively evaluated a missing window.

Illustrative report wording (not experimental results): “Rule requires a peer IP;
no peer-IP evidence has been assessed for this local sudo sample. This rule cannot
be evaluated for remote-source grouping from these observations. Investigate
existing remote-login logs; no logging changes have been made.” Another case might
report a log read permission denial or parser failure separately. Avoid substituting
an empty alert list for a healthy capability/coverage report.

## 9. Detection-rule field requirements

[Release scope](../release-scope.md) and
[ADR-007](../decisions/007-initial-release-scope.md) limit v0.1 to individual-event
rules and alert-to-triggering-event/rule traceability. The broad catalog also
supports future research: time-window requirements, multi-event relationships,
aggregation and behavioral sequences belong to v0.2 planning. A single failed
authentication event may be categorized in v0.1; repeated failures and a subsequent
success cannot be a v0.1 rule. Source-native multi-record parsing and per-event
context are distinct from security correlation and must not conceal it.

Each rule must declare its objective, applicable event families and roles,
Required/Important/Optional information, source-semantic constraints, acceptable
alternative mappings, per-event freshness/context needs (correlation windows in
v0.2 only), and triggering-event provenance (multiple supporting events in v0.2),
missing-data behavior, and limitations/benign explanations. Sensitivity annotations
and retention needs belong alongside these declarations, not in a ranking.
An observed source value is not yet usable normalized evidence if mapping or
validation is unresolved. Rules should consume justified normalized semantics,
not silently depend on a particular raw source spelling.

Examples below are proposed research requirements, not finalized or implemented
rules or a mandatory v0.1 checklist. The inventory can grow without implementing
evidence aggregation/relationship machinery or prematurely finalizing contracts:

| Example detection | Required | Important | Optional | Missing-data consequence |
|---|---|---|---|---|
| Repeated authentication failures per account (v0.2 planning) | Identifiable authentication check, failed result, account key with defined role, usable times/window, distinct event/evidence identities | Complete collection interval, terminal/session context | Executable, requested command | No valid account/result/time or deduplication basis: cannot evaluate this rule as specified; incomplete interval must be disclosed |
| Success after failures for same account (v0.2 planning) | Above plus successful check and validated same-account linkage | Session context and continuity across sources | Working directory | No reliable linkage or success result: cannot assert the specified sequence |
| Execution from selected temporary paths (v0.1 candidate, source-dependent) | Actual execution evidence, executable path, evidence identity | Actor and reliable parent context | Requested command or session detail | Sudo command request alone is insufficient execution evidence |
| Selected sensitive-file integrity change | Comparable before/after digests for identified object, baseline provenance, compatible algorithm, observation times | Ownership/mode and collection continuity | Package context | A file path or modification message alone cannot establish content integrity change |

Rule readiness must be reassessed when sources/access/field evidence change and
again for each applicable record/window. With a missing Required field, do not
report a negative match as proof of safety. Missing Important context must be
explained; missing Optional context does not justify inventing values. Exact
runtime states, scheduling/deactivation behavior, fallback rules, and machine-readable
requirement syntax remain undecided. Alternate sources must preserve equivalent
meaning; a weakened rule is a separately documented rule, not a silent substitution.

## 10. Privacy and security considerations

- Discovering that a key exists is different from retaining its value. Field names,
  types, presence, and sanitized provenance can support research without retaining
  all payloads. Discovery itself can expose sensitive names and activity patterns.
- Arguments and environment variables can contain passwords, tokens, and keys;
  original messages can contain arbitrary secrets. Do not collect indiscriminately
  or preserve full values just to populate this catalog.
- Usernames, addresses, paths, host/session IDs, DNS names, fingerprints, and
  cross-event correlations require data-minimization and retention decisions.
- Protect originals, derived inventories, diagnostics, backups, and exports.
  Restrict human dashboard/security-data access to root while granting services
  only necessary access; authentication and sudo-admin eligibility remain open.
- Sanitize examples before any future Git commit, consistently replacing identities
  and correlation keys where needed. Preserve joins for testing without exposing
  actual identifiers; document transformations and re-identification limits.
- Treat every source value and discovered key as untrusted input. Future parsers,
  reports and dashboards need escaping/validation and bounded sampling/field sizes;
  failure diagnostics must not leak raw sensitive values.
- Keep information local by default. Optional AI interpretation does not authorize
  external transmission. Never raise privileges or enable extra logging automatically.

Raw-record storage, redaction, encryption/key management, retention duration,
sampling limits, and safe diagnostics remain design work, not implemented controls.

## 11. Evolution of the catalog and schema

Add candidates freely when there is a plausible detection/research use, recording
description, source hypothesis or reference, type expectations, sensitivity, and
status. Retain contrary observations and source/version-specific meanings.
Use separate catalog, assessment, mapping, rule, and event-schema revisions; exact
version formats and storage are proposed implementation details.

Promote a candidate into the normalized contract only after representative source
records establish its semantics, an appropriate ECS field has been reviewed, a
concrete consumer needs it, privacy is addressed, and fixtures/validation support
it. Document uncertain mappings instead of forcing them. Custom fields need a
real ECS gap; no mandatory `hids.*` fields follow from this catalog. Schema changes
follow the [schema process](../schema-design-process.md), including compatibility
and migration decisions where needed. An unmapped source key can remain preserved
in protected originals while the normalized schema stays unchanged.

The schema process's event-family priorities are historical planning suggestions,
not universal field importance rankings. Field importance is always rule-specific.
Its coverage matrix tracks event-family research maturity; this catalog tracks
candidate concepts, while runtime assessments would describe particular environments.
Do not confuse any of these with a security-coverage percentage.

## 12. Open questions and future research

1. Which exact native fields and types appear in full structured successful/failed
   sudo records, and which reported values are parsed message content?
2. How do cached credentials, retries, cancellation, alternate targets, and remote
   logins change field presence and identity roles without new Audit rules?
3. Which fields can each actual service identity read? Distinguish permission denial,
   absent/disabled sources, empty samples, and parser failures without modifying the VM.
4. What source/host/boot/time/session keys reliably distinguish Audit events,
   cross-source duplicates, correlated activities, and reused PIDs?
5. What bounded startup/periodic probes can assess health without generating sensitive
   activity, overloading the host, or interpreting silence as success?
6. How should capability changes, stale samples, collection gaps, recovery and
   historical replay affect rule evaluation and explainable dashboard state?
7. What catalog/assessment storage, raw-record references, rules syntax, assessment
   intervals, retention and redaction policy should be adopted? None is finalized.
8. Which ECS mappings are justified, especially audit login UID/session and
   source-versus-target identity? Do not approve custom fields before this review.

Next: repeat sudo experiments with protected complete records and exact capture
transcripts; inventory fields and types before mapping. Compare read access using
intended identities in a separately authorized VM experiment. Then investigate
additional SSH methods, paired failure records and logout semantics, console
records, and source continuity across naturally occurring
rotation/restart boundaries. No experiments or implementation occurred in this
documentation task; no configuration change is authorized by these proposals.
