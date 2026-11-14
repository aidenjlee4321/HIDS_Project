# Internal process control status

The root-only `/run/hids/process/status.json` control file is separate from
normalized events, native IPC, retained SQLite data and HTTP projections.

Version 2 adds `runtime_pid` (positive integer) and `runtime_invocation`
(systemd's 32-character lowercase hexadecimal InvocationID; null outside systemd)
to the existing version 1 fields. The producer stamps these fields at publication.
Only a systemd-bound version 2 status can authorize signaling an active runtime.
Root status presentation accepts existing version 1 and typed version 2 records;
it does not expose the internal process witness.

Explicit Stop matches source, activation and generation, checks the live systemd
PID and invocation twice around opening a PID descriptor, and signals that exact
process descriptor. The coordinator performs its existing owned-component cleanup.
The adapter never blindly stops active component names from an old status file.
Unknown leftovers leave Stop unconfirmed. An active legacy version 1 runtime cannot
be automatically taken over through this path; stopped-before-upgrade remains
required by the development installer.

Under the same owner lock held by a running coordinator, Stop may revoke only an
exact matching unconsumed one-use authorization, including an expired grant. A
foreign or malformed grant remains intact. Grant revocation alone confirms Stop
only when all process units are inactive; failed or unknown active components
remain unconfirmed. No selection revision, event, history or logging policy is
deleted. A new start still requires fresh explicit root authorization.
