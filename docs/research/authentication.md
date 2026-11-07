# Ubuntu authentication research: sudo and SSH

**Status:** Initial observations; candidate mappings only, no implementation  
**Documented:** November 5, 2026  
**Experiment date:** Not supplied  
**ECS reference:** 9.5.0

## 1. Purpose and research scope

Record the project's Ubuntu authentication experiments: one successful sudo
operation, one deliberately incorrect sudo password entry, and additional SSH
journald investigation. The evidence is the VM
observations supplied by the project owner, not experiments rerun while writing
this document. Complete source records and capture transcripts were not supplied.

Sections marked **observed** report that evidence. Interpretations and proposed
mappings are explicitly separate. This is research into existing logging, not a
validated event contract, implemented collector, or guarantee of Ubuntu-wide
coverage. It does not cover all authentication methods or login mechanisms.

See the [schema research process](../schema-design-process.md),
[proposed schema](../event-schema.md), [evidence policy](../confidence.md), and
[threat model](../threat-model.md). See also the
[field-discovery catalog and methodology](field-discovery.md), which uses these
observations as research examples. The SSH follow-up identifies native journal
keys separately from message content; complete serialization types, per-record
field presence, and universal field availability remain unverified.

## 2. Test environment

Reported VM configuration:

| Item | Observed value |
|---|---|
| Distribution | Ubuntu 26.04.1 LTS (Resolute Raccoon) |
| Kernel | `7.0.0-42-generic` |
| Architecture | `aarch64` |
| systemd/journald | `259.9` |
| auditd | `4.1.2`; active |
| sudo implementation | sudo-rs `0.2.13-0ubuntu1.2` |
| Linux Audit | Enabled |
| Explicit Audit rules | None configured |
| Reported Audit status | `lost 0`, `backlog 0` |

These describe this VM, not an asserted default for every Ubuntu installation.
The status values are observations at the status check; they do not establish
complete capture throughout the experiments or absence of other visibility gaps.

## 3. Methodology and commands used

The reported successful experiment executed:

```sh
sudo -k
sudo id
```

The failed experiment deliberately supplied one incorrect password for the sudo
authentication attempt associated with `sudo id`. The exact invocation sequence
for that experiment, including any prior credential invalidation, was not supplied.
Do not infer retries, cancellation, or the process's eventual exit status.

Journald and Linux Audit observations were compared using the reported sudo PID,
account/session context, and Audit event serials. The exact journal/Audit query
commands, output formats, time filters, status commands, and observation window
were not supplied. Reproduction requires recording those details in a later run;
no unreported capture commands are presented here as having been executed.

No explicitly configured Audit rules were present. No logging or Audit configuration
changes are reported as part of these experiments. Throughout the initial release, HIDS must not modify journald configuration, PAM configuration, auditd configuration, or Linux Audit rules. This applies during installation, startup, discovery, and runtime. Additional logging configuration requires separate design and approval. Future experiments must
separate existing-configuration observations from any separately authorized setup.

**Sanitization:** Personal usernames and home-directory components are replaced
consistently with `test-user` and `/home/test-user` below. Numeric UID, PID, session,
and serial values are retained as local experimental references to preserve joins;
they are not globally unique identities. No host identifiers, passwords, or raw
private records are included. Tables are sanitized observation summaries, not
verbatim records or parser fixtures.

## 4. Successful authentication observations

**Observed — journald:**

| Information | Reported observation, sanitized |
|---|---|
| PAM session | Opened for `root` by `test-user` |
| Command execution request | `/usr/bin/id` |
| Original user | `test-user` |
| Target user | `root` |
| Terminal | `/dev/pts/0` |
| Working directory | `/home/test-user` |
| Sudo process PID | `4894` |

**Observed — Linux Audit:** Five separate events were associated with PID `4894`.

| Audit type | Serial | Reported meaning/result |
|---|---|---|
| `USER_AUTH` | `407` | Authentication succeeded |
| `USER_ACCT` | `408` | Account validation succeeded |
| `CRED_REFR` | `409` | Credential setup for root succeeded |
| `USER_START` | `410` | Root session opened |
| `USER_END` | `411` | Root session closed |

The reported records contained UID, audit login UID, audit session ID, executable,
terminal, account, and result information. Their exact values and per-record
availability were not supplied for this experiment; do not fill them from the
failed experiment or assume every record contained every field.

**Interpretation:** These observations support investigation of a sudo activity
comprising authentication, account validation, credential setup, and session
lifecycle steps. The five different serials identify five individual Audit events,
not five records of one Audit event and not five separate sudo invocations.
A higher-level sudo activity may link them while retaining each event and its
source provenance. The journal command request is not, by itself, an execution
trace, command output, or proof that `/usr/bin/id` completed successfully.

## 5. Failed authentication observations

**Observed — journald:** A PAM authentication failure included:

| Information | Reported observation, sanitized |
|---|---|
| Username | `test-user` |
| UID | `1000` |
| Effective UID | `0` |
| Terminal | `/dev/pts/0` |
| Sudo process PID | `5024` |
| Executable | `/usr/lib/cargo/bin/sudo` |
| Command line | `sudo id` |

**Observed — Linux Audit:**

| Information | Reported observation, sanitized |
|---|---|
| Audit type / serial | `USER_AUTH` / `458` |
| PID | `5024` |
| UID | `1000` |
| Audit login UID | `1000` |
| Audit session | `3` |
| Account | `test-user` |
| Result | Failed |
| Grantors | `?` |

No corresponding successful session-opening record for PID `5024` was observed.
This is an observation about the inspected evidence, not proof that no later
session or retry occurred. Preserve the raw `?` grantors value as unresolved;
it does not identify a grantor or establish why the value was unavailable.

**Interpretation:** The records describe a failed authentication check in this
controlled incorrect-password test. Effective UID `0` on the sudo process is
not evidence that authentication succeeded or a root session opened. Outside this
controlled test, a failure record alone would not establish malicious intent or
the exact cause of failure.

## 6. Journald versus Linux Audit comparison

| Aspect | Journald in these observations | Linux Audit in these observations |
|---|---|---|
| Activity context | Successful command request, working directory, original and target users | Separate authentication/account/credential/session events |
| Failed attempt | PAM failure, process context and command line | Explicit failed `USER_AUTH`, account and audit login/session context |
| Linking evidence | Sudo PID and terminal | PID, serial, audit login UID and session information |
| Limit | Complete structured entries were not supplied | Complete records, timestamps and capture window were not supplied |

**Interpretation:** The sources are complementary: journal observations explain
application context while Audit observations expose distinct authentication and
session steps. Neither substitutes for a complete execution history. Matching
records across sources can represent the same underlying check; do not count them
as independent authentication attempts or independent corroboration by default.
PID alone is insufficient for durable correlation because it can be reused.
Host/boot context, source event identity, timestamps, and session context need
investigation before a correlation strategy is finalized.

**Identity distinctions:** UID describes an identity associated with the record's
subject/process under that source's semantics; effective UID describes process
privileges. Audit login UID is login attribution carried in Audit context and
must remain distinct from current/effective credentials. The target account is
the account being authenticated or acted upon, depending on the particular step.
In the failed record the account is `test-user`; in the successful sequence some
steps concern root. Do not assign one target account to every step automatically.
UID and audit login UID both being `1000` in the failed event does not make their
meanings interchangeable. No numerical UID for the successful target account was
provided. These records attribute activity to accounts; authentication success
does not prove the physical user's identity, authorization of every later action,
or legitimate intent.

## 7. Candidate ECS 9.5.0 mappings

All mappings below are **proposals**, pending complete source fixtures and semantic
validation. Prefer Core and relevant Extended fields over custom fields. No custom
namespace is selected; `hids.*` remains provisional.

Field names and types were checked against the pinned ECS 9.5.0
[user](https://github.com/elastic/ecs/blob/v9.5.0/schemas/user.yml),
[process](https://github.com/elastic/ecs/blob/v9.5.0/schemas/process.yml), and
[event](https://github.com/elastic/ecs/blob/v9.5.0/schemas/event.yml) definitions.
The source-to-field interpretation remains research work.

| Observed information | Candidate representation | Constraint / unresolved detail |
|---|---|---|
| Sudo PID | `process.pid` (integer) | Refers to sudo, not an inferred child command PID |
| Executable, command line | `process.executable`, `process.command_line` | Failed journal observation supplies these; do not substitute `/usr/bin/id` as sudo's executable |
| Original actor / authenticated account | `user.id`, `user.name` | Choose actor semantics per event; IDs are strings; do not conflate all identity roles |
| Effective UID | `process.user.id` | Only where source semantics establish effective process identity |
| Real UID | `process.real_user.id` | Only after verifying that the source UID means real UID |
| Target account | `user.target.name` | Candidate for an action's target; the account field's role varies by Audit step |
| Audit type | `event.code` (Extended) | Preserve `USER_AUTH`, `USER_ACCT`, etc.; action naming still needs design |
| Authentication result | `event.outcome` | Candidate `success` / `failure` for the corresponding check; no verdict on intent or whole-command completion |
| Authentication check | `event.category: [authentication]` | Candidate for `USER_AUTH`; do not apply blindly to all session/credential events |
| Source text | `event.original` | Only actual retained text; summaries here are not original records |

Audit login UID, Audit session ID, terminal, and working-directory mappings remain
unresolved pending broader pinned-field review. Preserve their source meanings;
do not invent an ECS field such as `user.audit.id` or assume a numeric Audit
session is a POSIX process session ID. The earlier proposed schema's login-UID path
has been withdrawn pending a justified ECS mapping; its native information remains
a catalog candidate. A serial alone is not yet an approved `event.id` scheme.
Source timestamps were not supplied, so no `@timestamp` example can be populated. Missing/unreliable activity-time handling is an unresolved schema decision; do not invent activity time or silently substitute collection time. Keep collection and processing/storage times distinct; no fallback policy is finalized.
A future normalized event would declare `ecs.version: "9.5.0"`; that is schema
metadata, not a field observed in the original Ubuntu records. Exact `event.type`,
`event.action`, provider/dataset, and higher-level activity representation remain
undecided.

## 7a. SSH journald follow-up

**Evidence scope — owner-reported observations:** Ubuntu 26.04.1 LTS,
systemd 259.9, OpenSSH 10.2p1. The SSH session process was
`/usr/lib/openssh/sshd-session`, PID `5855`. Do not carry the sudo experiment's
kernel, architecture, Audit status or configuration into this follow-up without
confirmation. The experiment date, full capture commands, time window, and
complete structured exports were not supplied.

The reported journal selectors were `_COMM=sshd-session`,
`_EXE=/usr/lib/openssh/sshd-session`, and `_PID=5855`. They returned overlapping
records, not three independent sets of events. The earlier `_COMM=sshd` query
missed these records because the actual process name was `sshd-session`.
This is a demonstrated query-selection limitation in this environment, not proof
that all SSH processes or versions use this name. No full command transcript or
exhaustive collection filter has been established.

**Observed message excerpts — sanitized, not complete records or fixtures:**

| Record | Reported content |
|---|---|
| PAM authentication failure | `pam_unix(sshd:auth): authentication failure`; `uid=0`, `euid=0`, `tty=ssh`, `rhost=127.0.0.1`, `user=test-user` |
| SSH authentication failure | `Failed password for test-user from 127.0.0.1 port 60018 ssh2` |
| SSH authentication success | `Accepted password for test-user from 127.0.0.1 port 60018 ssh2` |
| PAM session opening | `session opened for user test-user(uid=1000) by test-user(uid=0)` |
| Logout-related error | `syslogin_perform_logout: logout() returned an error`; associated with systemd session `5` and Audit session `5` |

The personal username is replaced consistently with `test-user`. Loopback address,
client port, process and local session/UID numbers are retained for source semantics
and local linkage; no cursor, boot or invocation identifier values are committed.
The session-opening excerpt preserves the reported name/UID pairing; its identity
roles require investigation rather than correction or inferred equivalence.

Native journal metadata reported present in these records included `_PID`, `_EXE`,
`_COMM`, `_SYSTEMD_UNIT`, `_SYSTEMD_INVOCATION_ID`, `_BOOT_ID`, `__CURSOR`,
`__REALTIME_TIMESTAMP`, `__MONOTONIC_TIMESTAMP`, `_UID`, and `_GID`. This list
establishes observed key presence across the inspected records, not that every
record contained every key. Values other than the process selectors were not
supplied. The native keys for the reported systemd/Audit session associations
were not supplied. Message `uid`, `euid`, `user`, `rhost` and `tty` are distinct
from emitter metadata such as `_UID` and `_GID`.

**Interpretation and record boundaries:** The PAM failure and SSH Failed password
messages appear to describe the same failed authentication attempt. Preserve both
original records and their provenance; do not automatically count them as two
attempts. This is different from retrieving the same journal entry through multiple
selectors, which requires source-record deduplication. A correlated authentication
activity may reference several distinct records; neither their grouping nor
attempt identity is a finalized contract. The accepted-password and session-open
messages describe different steps, and shared PID/peer/port alone does not finalize
correlation or attempt counting. Journald supplies authentication method (`password`)
and client source port in the SSH messages. The `ssh2` token is not a transport
or cipher field by itself. The loopback observation does not establish external
remote-login coverage.

The logout error's meaning remains unresolved. Do not classify it as failed session
closure, infer that the session stayed open, or assign a session-close failure
outcome from this text alone. Systemd and Audit session IDs remain distinct even
though both were reported as `5`. Journald and Linux Audit are complementary;
this follow-up supplies no complete corresponding SSH Audit record set and does
not establish cross-source equivalence or independent corroboration.

### Additional candidate ECS mappings

These are research candidates, not changes to the normalized contract. The pinned
[ECS 9.5.0 source definitions](https://github.com/elastic/ecs/blob/v9.5.0/schemas/source.yml)
and [process definitions](https://github.com/elastic/ecs/blob/v9.5.0/schemas/process.yml)
support the field names and types below; source interpretation still needs fixtures.

| SSH information | Candidate representation | Constraint / unresolved detail |
|---|---|---|
| `_PID`, `_EXE`, `_COMM` | `process.pid` (long), `process.executable` (keyword), `process.name` (keyword) | Emitting SSH session process; not the authenticated user's shell |
| `rhost` / SSH client address | `source.ip` (ip); `source.address` (keyword) for original address | Validate address and client role; observed address is loopback |
| SSH client port | `source.port` (long, Core) | Parse `60018` from message; not a server listening port |
| Failed / Accepted password | `event.outcome` for the authentication check | Candidate failure/success; preserve method separately with mapping unresolved |
| Account named in SSH message | `user.name`, with `user.id` only where justified | Distinguish authenticated account, opener and emitter credentials |
| `_UID`, `_GID`; message UID/effective UID | Identity mappings unresolved per source role | Do not assign emitter credentials to the authenticated account |
| Unit, invocation, boot, cursor and session context | Preserve native provenance; normalized mappings unresolved | No automatic `event.id`, process-session or service identity mapping |
| Journal realtime / monotonic timestamps | Preserve native clocks and representations; mapping unresolved | No numeric times supplied; receipt timestamps are not automatically activity time; scope monotonic time by boot |
| Logout error | Retained message; classification unresolved | No inferred failed session closure |

Authentication-method, PAM service/module, `tty=ssh`, session identifiers and unit
mappings need further pinned-field review. No custom namespace or field is approved.

## 8. Missing information and limitations

- No complete raw journal entries, Audit records, timestamps, cursors, boot/host
  identifier values, full query transcripts, or sanitized machine-readable fixtures
  accompany these observations. SSH native key names and message content are now
  distinguished, but complete per-record layout/types and sudo field origins remain
  unverified. The tables cannot validate a parser.
- Successful-record values and field presence were summarized, not enumerated per
  event. Parent PID, child execution details, command result/output, and exit
  status are not established by the supplied evidence.
- One successful sequence and one incorrect password entry do not characterize
  retries, cached credentials, alternative PAM configurations, or general logins.
- Audit events were observed with Audit enabled and no explicit rules in this VM;
  this does not establish that Audit is active by default elsewhere, that syscall
  execution auditing exists, or that all authentication paths emit these events.
- Capture permissions, rotation/restart behavior, ordering, duplicates, timestamp
  accuracy, and sustained event-loss behavior have not been tested.
- There is no finalized schema, validation suite, detection rule, or collector
  resulting from this document. Evidence gaps must be exposed to the user rather
  than filled by assumptions or confidence scores/labels.

## 9. Questions requiring further research

1. Which exact raw fields carry each UID/account and which are journal metadata?
2. Which records share an Audit event identifier, and how should distinct events
   be linked into a sudo activity across sources without double counting?
3. How should audit login UID, session, terminal, and working directory map to
   ECS 9.5.0? Is any custom field actually necessary?
4. What differs with a cached sudo credential, repeated failures, cancellation,
   noninteractive attempts, or a different target account?
5. What differs across SSH methods, invalid users, retries, disconnects and normal
   closure? What causes the logout error, and which session records establish
   closure? Console, graphical login and `su` remain uninvestigated.
6. What minimum read permissions and existing interfaces can HIDS use without
   modifying logging configuration or competing with auditd?
7. How do source availability, rotation, reboot, and log loss affect visibility?

## 10. Conclusions and next experiments

**Supported conclusion:** This VM produced useful sudo authentication evidence in
both journald and Linux Audit without explicitly configured Audit rules. The
successful sequence spans five distinct Audit events; the failed check has an
explicit failure result. These are account/activity observations, not proof of
legitimate intent or a complete command execution trace. The SSH follow-up adds
journal password outcomes, method, client port and session-opening context, with
an unresolved logout diagnostic and important selection/deduplication limits.

**Next experiments (proposed, not executed here):** Repeat both cases while recording
exact commands, observation windows, complete sanitized structured source records,
source timestamps and identifiers, and per-record field availability. Record
Audit status before and after each run without changing rules. Compare cached
credentials, one failure followed by success, cancellation, and alternate targets
in the test VM. Capture complete SSH entries with cursor/boot/time context, compare
overlapping selectors and paired PAM/SSH failures without double counting, and
investigate logout semantics and corresponding existing Audit records. Investigate
other login paths and source access permissions.

Use those fixtures to review identity semantics, correlation boundaries and ECS
mappings before finalizing contracts or implementing normalization. Keep any
experiment requiring changed logging configuration separate from initial-release
coverage research. This document does not authorize configuration changes.
