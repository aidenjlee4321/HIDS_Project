# M3 real native execution forms

## Purpose and safeguards

The explicit `--experiment native --live-audit` VM workflow exercises real
AArch64 kernel execution records through the installed canonical Audit plugin,
independent Python validation and durable SQLite. It adds neither a new source
architecture nor general failed-execution semantics. Production HIDS still never
changes Audit policy. The root-only lab harness temporarily adds one exact
child-PID execution rule at a time and a RAW-format plugin, then independently
attempts all cleanup steps and verifies the exact original policy, source inodes
and byte prefixes. It performs no source rotations, raw-log copying or deletion.

The nine-case matrix uses plain execution, an empty argument, whitespace/newline/
non-UTF-8 argument bytes, a fragmented 10,000-byte argument, a non-UTF-8 executable
filename, a shebang script, descriptor-based `execveat(AT_EMPTY_PATH)`, an existing
unprivileged identity and a failed nonexistent-path exec. Child setup and syscall
outcomes are checked. Root source access derives only event identity from the exact
child PID; no raw records/arguments are copied into reports. Protected reports
retain case labels, identities, disposition and small metadata only.

Positive cases must each have exactly one known durable execution plus EOE,
matching syscall, PID/parent, real/effective/saved/filesystem IDs, login/session
sentinels, executable/comm bytes and successful result. The failed exec must remain
unaccepted with durable `execve_missing_argc`, preserving the existing requirement
for a complete EXECVE group. No arguments/CWD/PATH/PROCTITLE contents enter the
normalized execution contract. File-prefix and policy checks are additional to
the normal workflow's installed hashes, state permissions and cleanup checks.

## Gap found and narrow correction

The first run failed on the plain one-argument execution. It is an intermediate
failure, not acceptance: job `hids-m3-lab-a9f7fe83dd8d`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-a9f7fe83dd8d/run-20261111T190805Z-747415b6f870/report.json`.
Its protected case report is `/root/hids-m3-native-workload.uwau6nkv/report.json`.
Cleanup and original source preservation succeeded.

Inspection of native encoding metadata established that the real single-argument
PROCTITLE was quoted printable text (six wire bytes), while M3 permitted only hex
for that record. The group had a real durable EOE and was correctly rejected by
the old validator as `invalid_context_record`; this was not a missing-EOE timeout.
The new validator accepts bounded, syntactically valid quoted PROCTITLE **only in
the native auditd-string profile**. Existing structural fixtures keep their strict
hex-only rule. Normalized storage still retains only the presence flag; this fix
does not begin retaining command arguments or treating PROCTITLE as completion.

Native contract tests change the former false negative into a positive presence
case and add malformed quote/spacing/odd-hex/lowercase-hex negatives. Libauparse
validation and independent backend contract checks remain intact.

## Intermediate rerun and harness correction

The rebuilt collector then accepted plain, empty/encoded/fragmented arguments,
byte-path execution and the script case. Descriptor-based execveat also reached
SQLite, but the harness expected pathname-style `comm`. On this Ubuntu host,
`/usr/bin/true` resolves to `/usr/bin/gnutrue`: pathname execution reports `true`,
while the tested descriptor execution reports `gnutrue`. The harness now derives
that exact expectation from the resolved descriptor target; the collector's native
values were correct and were not changed to satisfy the test.

That partial run is retained as failed job `hids-m3-lab-88909f8983de`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-88909f8983de/run-20261111T191113Z-ac0c08e60671/report.json`,
protected case report `/root/hids-m3-native-workload.ox_9f_n_/report.json`.
All six matched binaries were rebuilt; sanitizer/linked native contracts passed
before the live phase. Cleanup verified exact policy and source preservation.
This partial run alone is not acceptance of the complete matrix.

## Test-environment issue

During local validation, the Mac's available disk crossed the existing 1 GiB
warning threshold. Two unit tests incorrectly assumed the real host would always
have normal free space after a WAL checkpoint/restart. Storage unit fixtures now
provide a fixed synthetic free-space value; explicit warning/critical/exhausted
and inspection-failure tests override it. Production thresholds/guards and real
installed VM disk tests are unchanged. No Mac cleanup, installation, settings or
credential changes were performed; native builds run on the VM. The final report
must distinguish this host free-space condition from product acceptance.

## Shared-stream native-family gap

A further failed run, `hids-m3-lab-8a9424416c6b`, retained report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-8a9424416c6b/run-20261111T191423Z-b3958d5e9660/report.json`
and protected case report `/root/hids-m3-native-workload.q4r6npid/report.json`.
The execveat execution was durable, but unrelated native traffic interrupted source
readiness with `collector_input_failure`. Policy/source restoration again passed.
Bounded source metadata inspection identified native BPF `prog-id` field names,
which the narrow execution lexer rejected. Ordinary native USER/SERVICE families
also contain single-quoted messages with spaces/nested double-quoted values.
These share the same dispatcher even when execution rules are PID-scoped.

The native record parser now validates that separate non-execution family grammar
without applying execution field rules to it. Record sizes, byte restrictions,
identity/offset checks and EOE rules remain unchanged. Execution families retain
their original strict field lexer and semantic checks. Other record families are
not normalized as executions: they remain ineligible without EXECVE, and mixing
one into an otherwise complete execution group rejects that group. No raw
non-execution payload is persisted and this is not an authentication adapter or
support for accepting unknown execution fields. Malformed headers/identities or
unsupported record syntax still fail honestly; this is not universal Audit grammar.

A new sanitizer regression group checks native BPF and quoted USER_AUTH framing,
malformed negatives, continued independent execution, and rejection of a mixed
unsupported-family execution. The real matrix subsequently passed all nine cases:
job `hids-m3-lab-9e056d00be29`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-9e056d00be29/run-20261111T201647Z-1b574e22077b/report.json`,
protected case report `/root/hids-m3-native-workload.b3qdrgfi/report.json`.
Eight successful executions were accepted and the nonexistent-path attempt was
durably rejected, each with real EOE. Exact cleanup/source preservation passed.
Elapsed 77.162 guest seconds including six matched native artifact builds.

## Final deliberate-background acceptance

The final matrix explicitly emits a sanitized native USER message with spaces and
starts the existing health service while the plugin is active. Thus shared-stream
continuity no longer depends on incidental timer scheduling. Passed job
`hids-m3-lab-bf06114ebf11`:

- Workflow report:
  `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-bf06114ebf11/run-20261111T201840Z-36c4d5ce91ad/report.json`.
- Protected case/source metadata: `/root/hids-m3-native-workload.m6s9o0ye/report.json`.
- Verified source snapshot:
  `5e3f884f54b3d2ebd116e6cc21ad0ff4d16d7278c260552b8082bfd221a649ae`.
- Elapsed 76.245 guest seconds, including six matched builds. Build key:
  `6ad7a4499604db6efcbfe7014dcde0e1829556220e24ab16801b4e5057bf27d4`.
- All eight successes accepted exactly once with EOE and matching native fields;
  the nonexistent-path exec rejected with EOE/`execve_missing_argc`. Script PATH
  count three, other successful cases two. The non-root case uses NSS `nobody`;
  real/effective/saved/filesystem IDs match, and inherited login/session unset
  sentinels remain null rather than invented identities.
- Source readiness and generation remained stable across the cases; daemon PID
  and kernel lost count were unchanged. Final counters: eight observed executions,
  18 rejected groups, zero timeout/late/resource incidents. Other-family and rule
  administration records are not mislabeled as successful executions. These are
  honest scoped counters, not a claim of a lossless census of every host event.
- 79 M3 Python + 40 workflow tests, 26 sanitizer reconstruction groups, 128 linked
  native contract cases, 124 allocation cuts, 11 API faults and 58 actual SIGKILL
  boundaries passed. The new mixed-family execution rejection test was included.
- Exact policy/configuration restoration, source prefix preservation, installed
  hashes, state permissions and stopped M3 units passed. Audit stayed active.

Historical rejections remain immutable; the parser corrections do not replay old
source files, resurrect past groups or change EOE-only completion. Both new live
experiments remain explicit workflow scopes rather than implicit checkpoint work.

## Remaining limits

This matrix improves representative native evidence, not complete Audit grammar or
all Linux execution semantics. Other execveat flag/path variants, deleted-file and
special executable cases, additional source families/encodings, very large and
host-specific workloads, physical power loss/device faults, hard filesystem quotas,
release resource thresholds and packaging/distribution/license review remain open.
Malformed/unsupported framing still stops honestly; unsupported groups are never
accepted by dropping unknown execution fields. Failed executions without EXECVE
remain a rejection, not a new failed-execution event feature. External finite
source retention remains host-administered and unchanged.

## Full checkpoint and final restoration

The final code also passed the full live checkpoint, all 17 phases:
`hids-m3-lab-748c749409b8`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-748c749409b8/run-20261111T202026Z-4869b1d2a633/report.json`.
Elapsed 133.277 guest seconds, verified shared binary cache hit with zero cached
artifact build commands. Fresh sanitizer/native/parser-fault/crash checks still
ran, plus actual transport, installed metadata/storage, runtime/live Audit,
4096-event load, resource pressure, installed faults and health isolation/periodic/
lifecycle tests. Source snapshot:
`dbe1478b7dc81a6cf4268c66a59a5cab0682c911bcec44e7417e163df598971f`.
Host and guest clocks differ; elapsed values compare guest timing only.

A final independent check matched Audit files/rules against the earlier protected
manifest `/root/hids-m3-reboot.xbahp1tb/manifest.json`, reverified the four original
native-run source inode/byte prefixes after all regression work, and matched all
29 installed application/service artifacts. Original HIDS configuration matched
the workflow baseline exactly (512-activation lab budget); state remained ingest
0700 with files 0600 and configuration root 0640. Audit was active, all M3/checker
units inactive, and temporary test plugin/fault/probe executables absent. All 305
SQLite files including control were retained; there was no source/history deletion
or additional rotation. The owner subsequently approved committing and pushing this checkpoint to
`aidenjlee4321/HIDS_Project` on `main`; verify Git for publication status. The previously approved rotation checkpoint was separately
pushed as `19e2bb10cc0d1e6359dd637c07a3e5d98ce2d166`.
