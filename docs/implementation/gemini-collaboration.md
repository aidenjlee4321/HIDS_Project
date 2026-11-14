# External Gemini development reviewer

Superseded as the active setup by the owner's November 14 request to use
[GitHub Copilot](copilot-collaboration.md). Gemini authorization was not completed.

The owner requested Gemini collaboration after the first installable development
checkpoint. This is a development aid, not a HIDS runtime cloud feature or a new
source, rule, detector, credential-sharing, commit or push approval.

## Current status — November 14, 2026

Gemini CLI 0.68.0 is installed in Linux 2 at `/opt/hids-gemini`, using a verified
official npm archive and the existing verified Node 26.13.1 ARM64 distribution.
Version/help checks passed. Google browser sign-in is complete; CLI authorization
is pending. The real CLI displayed its Google authorization URL and code prompt
in the VM terminal. No successful model response has been observed yet.

The owner should review Google consent and enter its authorization code directly
in that terminal, never in chat or the repository. The CLI code prompt expires
after five minutes; rerun `sudo hgl` (a VM-only shortcut for
`sudo /usr/local/bin/hids-gemini-login`) if needed. Credentials belong only in the
dedicated VM account's private home. No API key, billing or Cloud project has been
configured. Account/provider restrictions remain unverified until a live request.

## Boundaries

`scripts/gemini_review.py` builds explicit, checksummed source packets. Only named
source files in its allowlist are read; symlinks, hard links, traversal, hidden
paths, unknown fields, invalid hashes, oversized input and private-key markers are
refused. A packet has at most 32 files, 64 KiB per file and 256 KiB total. These
checks are not a complete secret scanner: the caller must select and inspect
development context before sending it to Google. Never send native HIDS records,
private logs, database files, keys, VM credentials or unrelated personal files.

The reviewer runs as a dedicated account with no supplementary groups, sudo or
HIDS data access. The transient service has no capabilities, cannot gain new
privileges, hides HIDS state/configuration/runtime and other `/opt` installs,
protects the host filesystem and writes only its private home. An administrator
policy denies every Gemini tool, including shell, file, web and agent tools.
Extensions, hooks, MCP configuration and automatic updates are disabled. Network
access is needed for Google; this is not a network destination allowlist.

Each request is bounded to two model turns, three service minutes, 1 GiB memory,
64 tasks and 200% CPU. The controller bounds output to 1 MiB and cleans up after
timeout, failure or keyboard interruption. It does not retry automatically or
execute the response. Private request/response diagnostics remain under
`/var/lib/hids-gemini/jobs`, accessible only to root. Keep outputs scoped to
development review and preserve the owner's approval rules.

## Invocation and checks

Local packet preparation (does not send a request):

```sh
python3 -B scripts/gemini_review.py packet \
  --task 'Review this selected source for concrete defects.' \
  --file api/example.py
```

Use actual existing reviewed source paths, store packets privately, and pass JSON
through a private input pipe to `sudo /usr/local/bin/hids-gemini-review` in Linux 2.
`sudo /usr/local/bin/hids-gemini-status` reports cached-auth availability, not
successful provider access. The first live probe should contain no files and ask
only for `Hi.`. A successful request returns `status: done`, response, usage and a
private job identifier. Treat model advice as untrusted review input and verify it
before applying a change.

Seven unit checks passed for packet validation, safe source selection, no-auth
refusal, fixed isolation arguments and interruption cleanup. Actual VM kernel
checks confirmed nonroot execution, zero capability sets, NoNewPrivs, hidden HIDS
paths and read-only policy. The installed Gemini policy engine, tested offline,
denied file read/write, shell, web search/fetch, skill, agent and fake MCP calls;
the administrator deny rule was loaded at priority 5.999. These checks establish
local isolation, not provider authentication or useful review quality.

No Mac software/settings/credentials were changed. No HIDS source units were
started by this setup, and no commit or push was made.
