# M4 production storage and first Ubuntu trial: review packet

Status: accepted by the owner with “yes, now continue.” The bounded real-data
entry point and trial are now implemented/passed; [evidence](../validation/m4-real-data-trial.md)
records exact results and restoration. This packet is the approved first-trial
scope, not unattended production/release acceptance. Existing architecture and
synthetic approvals remain intact.
The [passing synthetic evidence](../validation/m4-handoff-implementation-validation.md)
is the basis for this concrete D-07/D-09 review.

## Accepted decision in plain language

Accept the tested five-record storage layout and transaction order for the first
bounded real-data integration, with the operating limits below. This means a new
protected local copy of selected M3 events; exe/comm and user/process metadata have
the same sensitivity as the originals. Keep both histories; no automatic deletion
or retention duration is introduced. Enable no real security rules and produce no
threat alerts in the first import trial.

The approved first-trial destination is `/var/lib/hids/m4/store`, owner `hids-ingest`, directory
0700 and files 0600. Source is the fixed `/var/lib/hids/m3` directory with explicitly
root-selected source/activation/generation. The source is read-only in the worker's
namespace; M3 writer ownership and ACK path remain unchanged. The worker must not
accept arbitrary source/destination paths or an all-history wildcard.

## Exact schema and transaction semantics

The SQL below is the tested handoff layout, exported directly from
[the implementation](../../engine/detection/m4_handoff.py). It defines:

| Record | Meaning |
|---|---|
| Binding | Selected source/activation/generation, directory and durable sweep state/fingerprints. No lease token. |
| Event | Immutable normalized event/provenance/metadata snapshot and content hash, scoped identity and first position, separate import time. |
| Rule | Immutable rule id/revision, exact definition and hash. No rule is enabled for the first real-data trial. |
| Evaluation | One event/rule/revision and pending/matched/no_match/unable/error. Unchecked events remain explicitly unevaluated. |
| Alert | One triggering event/rule/evaluation, exact explanation/values and creation time. Only the informational lab-demo form is implemented; real security rules remain separately gated. |

For the first import-only trial, rule/evaluation/alert tables remain empty. Approving
the table layout does not accept a general production severity taxonomy or make
the informational demo a supported real-world security rule.

Import transaction: immutable event + any approved rule work + sweep progress.
Evaluation transaction: result + optional alert. No progress advances on failed
import, and evaluation failure cannot discard the committed event. Duplicate
content is idempotent; conflicting identities/metadata/revisions reject. M3 never
waits for either destination transaction. The frontier-safe sweep preserves late A
after B as proven by the separate design and durable/sandbox tests.

Use a new real-data application identity (approved `0x48344c31`, version 1), distinct
from the tested synthetic handoff identity `0x48344831` and fixture pilot. Use a
separate live event/content hash domain and explicitly verified Audit provenance;
never relabel real input as `synthetic_lab`. Unknown observation metadata stays
unknown; activity, source observation, receipt/persistence-start and import clocks
retain their distinct meanings. These remain adapter-internal fields, not a
finalized global ECS/custom namespace or universal clock policy.

```sql
CREATE TABLE m4h_bindings(binding_key TEXT PRIMARY KEY, scope TEXT NOT NULL, directory TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE m4h_events(event_key TEXT PRIMARY KEY, binding_key TEXT NOT NULL REFERENCES m4h_bindings,
 identity TEXT NOT NULL, first_offset INTEGER NOT NULL, envelope TEXT NOT NULL, content_hash TEXT NOT NULL,
 imported_at TEXT NOT NULL, UNIQUE(binding_key,identity), UNIQUE(binding_key,first_offset));
CREATE TABLE m4h_rules(rule_id TEXT NOT NULL,revision TEXT NOT NULL,definition TEXT NOT NULL,content_hash TEXT NOT NULL,
 PRIMARY KEY(rule_id,revision));
CREATE TABLE m4h_evaluations(event_key TEXT NOT NULL REFERENCES m4h_events,rule_id TEXT NOT NULL,revision TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','matched','no_match','unable','error')),reason TEXT,evaluated_at TEXT,
 PRIMARY KEY(event_key,rule_id,revision),FOREIGN KEY(rule_id,revision) REFERENCES m4h_rules);
CREATE TABLE m4h_alerts(alert_id TEXT PRIMARY KEY,event_key TEXT NOT NULL,rule_id TEXT NOT NULL,revision TEXT NOT NULL,
 explanation TEXT NOT NULL,matched_values TEXT NOT NULL,demo INTEGER NOT NULL CHECK(demo=1),
 severity TEXT NOT NULL CHECK(severity='informational'),created_at TEXT NOT NULL,
 UNIQUE(event_key,rule_id,revision),FOREIGN KEY(event_key,rule_id,revision) REFERENCES m4h_evaluations);
```

Existing M3/fixture/lab databases are not converted or migrated. Unknown schema or
application versions refuse. Rollback stops only the new worker and retains its
protected state; M3 databases need no downgrade or restoration. Later upgrades,
retention/expiry and any broader rule schema require their own concrete review.

## Approved initial trial limits

These are conservative FIRST-TRIAL settings, not accepted release benchmarks or
unattended production defaults. Values reuse existing M3 storage admission rather
than lowering its guards to make a test pass.

| Setting | Approved first-trial value / behavior |
|---|---|
| Database | 512 pages × 4096 bytes = 2,097,152 bytes (2 MiB) SQLite page cap. Full blocks imports without deletion. |
| WAL admission budget | 16,941,696 bytes, the existing guard's value for 512 pages. Admission/checkpoint policy is not a hard filesystem quota. |
| Aggregate state admission budget | 268,435,456 bytes (256 MiB), including sidecars/accounting. This is a ceiling, not an allocation or promised on-disk hard cap. |
| Free-space warning / critical / minimum | 1 GiB / 512 MiB / 256 MiB. Actual reserve checks can block earlier; unknown/read-only storage blocks. |
| Source batch | At most 64 committed events; release read transactions between pages. |
| Source read limits | 50 ms connection busy timeout; 250 ms SQLite statement progress budget. A stuck filesystem syscall is not bounded by that callback. |
| Scheduling | One-second bounded rounds, per-binding retry backoff 2–30 seconds; no work added to M3 accept/ACK. |
| First trial | One explicitly selected newly authorized activation; at most 16 controlled executions and 120 seconds, then stop and report. Quiet/failed delivery is incomplete, not a pass. |
| Rules | Disabled. Report imported, pending and unevaluated counts explicitly; zero alerts does not mean events were judged safe. |

Static validation accepted this exact budget combination using the existing
`m3_storage.validate` rules. Observed Ubuntu free space during packet preparation
was 45,754,605,568 bytes on a writable filesystem; recheck before any trial. This
is an availability observation, not a workload benchmark or approved resource SLA.
The current sandbox used smaller LAB settings (64 pages and 1/2/4 MiB free-space
floors); those synthetic settings must not silently become the real-data defaults.

## Implementation and trial boundary after this decision

First build the separate root-configured entry point and test it against synthetic
M3 ledgers in the actual sandbox. Preserve existing lab-only entry-point gates.
A production-shaped synthetic mount test must prove fixed source/destination paths,
root-only selection, live/fixture store rejection and existing WAL visibility
without reading original production data. Do not install or start it on the Mac.

For the subsequent bounded Ubuntu acceptance, root must select the exact activation
and source scope. Any temporary Audit plugin/rule setup belongs only to the
separately authorized isolated live-Audit lab procedure, with exact baseline
restoration; product code must never perform it. If an existing feed cannot provide
records and that lab procedure cannot run safely, report unavailable/incomplete.
Do not broaden permissions, force a rotation, weaken guards or fabricate coverage.

Pass requires an actual committed M3 execution to appear exactly once in the
separate destination with unchanged scope/payload/metadata, source writes denied,
M3 ACK unaffected, and imported events explicitly unevaluated. Check original
policy/plugins/rules, source inode/prefixes, old databases, installed files and unit
state afterward. Retain new history privately; no old database/source evidence is
removed. If a controlled trial creates a new M3 activation, its database remains
additional history and the count increases rather than being cleaned up.

This decision does not approve unattended operation, meaningful security-rule
semantics/severity, dashboard authentication, release acceptance, commits/pushes,
a Mac system change or production logging configuration changes. Preserve
D-08/D-12/D-13/D-15 and the remaining fault/contention/resource evidence gates.

## Recorded owner decision

The owner accepted the minimal storage/transaction and no-migration policy, bounded
trial settings and additional protected event copy. Synthetic fixed-path checks
passed before real access, and the 16-event real trial passed with policy/history
restoration. The retained procedure above defines that first trial; it is not
permission to discard its destination/history or enable ongoing monitoring/rules.
