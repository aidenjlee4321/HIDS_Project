# First build: your Linux 2 trial

The tested development build is `0.1.0~dev20261114.15`. It is installed in Linux 2,
and its installer and these instructions are in `~/Desktop/HIDS First Build`.
You do not need to reinstall it to begin. This package is for Ubuntu 26.04 arm64
with Python 3.14; it is not a Mac installer or the complete v0.1 security product.

## Start with the dashboard

1. Open **Linux 2**, sign in as **ivy**, and open Terminal.
2. Run:

   ```sh
   sudo hids-dashboard open --recent-process --retained-audit --temporary-browser-userns
   ```

3. Enter your Linux password when sudo asks. An isolated ordinary-user browser
   opens the protected dashboard. Allow a few seconds for it to load.
4. Check Overview, open a process event, open the informational finding, and use
   its **Triggering event** button. Log out and confirm the details disappear.
5. Close the isolated browser. The viewer stops; no collector is started by opening
   this dashboard.

Before your own collection trial, expect six process records, 19 retained Audit
history records and one informational finding. The first three process records
were retained earlier; three were added by the final owned-child test. The old
16 unevaluated Audit records remain unevaluated. This is frozen history: reopening
loads a new snapshot. “Current monitoring status: not assessed” is intentional.
Observation/receipt times are not a reliable process activity wall clock.

## Optional: collect a short new process interval

The existing records are sufficient for the first UI trial. To try collection too:

```sh
sudo hids-sources status
sudo hids-sources start-process
```

Type `START` at the confirmation. Use another terminal for a few ordinary actions,
then stop promptly:

```sh
sudo hids-sources stop
```

Type `STOP`, then reopen the dashboard using the first command above. Closing the
browser alone does not stop a separately authorized collector. Saved choices never
restart collection after reboot. This build has a finite source-choice revision
history, so avoid repeatedly starting intervals during the initial trial.

If Stop says `stop_unconfirmed`, stop the trial and tell me the status message;
unknown components are deliberately left untouched. If the browser does not open,
report the terminal message. Do not bypass certificate warnings, disable the
browser sandbox, change Audit rules, or remove existing history to work around it.

## What feedback is useful

- Did opening, browsing, logout and closing behave as you expected?
- Were Activity versus the informational finding understandable?
- Were the time labels, missing fields and frozen-history explanation clear?
- What felt confusing or unnecessarily difficult?

Do not expect executable/user enrichment, a supported process threat detector,
automatic monitoring, continuous live updates, broad security alerts or remediation.
This build proves the narrow collection → private storage → protected snapshot flow.
The existing Audit finding is informational and does not establish malicious activity.

## Installer and recovery information

The folder contains `hids-development_0.1.0~dev20261114.15_arm64.deb` and `SHA256SUMS`.
To verify it from that folder:

```sh
sha256sum -c SHA256SUMS
```

Linux 2's prior stopped manual application code/units were archived privately at
`/opt/hids-prepackage.4rl2pqv2`; configuration, keys, source identity and old history
were retained. The normal package preflight still refuses unmanaged installations;
this was an explicit lab transition, not an automatic product migration.
Do not restore that archive over a running package or purge application state.

The installed operator guide is `/usr/share/doc/hids-development/README.md`.
Exact build inputs are in `/usr/share/doc/hids-development/BUILD_INPUTS.json`.
Full checkpoint evidence is in `docs/validation/first-build-ready.md` in the source
checkout.
