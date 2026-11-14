# External Copilot development reviewer — setup checkpoint

On November 14, 2026 the owner requested a pivot from Gemini to GitHub Copilot
after encountering student-account restrictions. Gemini authorization never
completed; no Gemini model response was verified. Its inactive installation is
retained rather than deleted without approval. This pivot changes development
assistance only, not HIDS architecture or Git approval requirements.

## Connected and integrated

Official `github/copilot-cli` release v1.0.112, Linux ARM64, is installed under
`/opt/hids-copilot`. The downloaded archive's SHA-256 matches the release asset's
GitHub digest:
`491d18303505935675dc20987ef0c5f3ae899f81e66c53d567ad97a8b03e504e`.
Version and installed CLI help checks passed. The archive contains one executable;
no npm/root installation scripts or Mac installation were used.

`scripts/copilot_review.py` provides isolated device-code login, a fixed greeting
probe, local source-packet preparation and bounded source review. Owner device
authorization completed, its login persisted,
and the actual restricted greeting returned `Hi.` with exit code zero. Codes are
temporary; keep them and authentication tokens out of repository documentation.
The first GitHub
authorization succeeded but its token was discarded because no keychain or
interactive fallback consent was available. The owner explicitly approved a
private, unencrypted VM credential file after automatic approval review required
specific consent. The replacement authorization completed; the terminal driver
accepted only the official CLI's exact plaintext-storage prompt. Credential
configuration files are owned by UID 990 with mode 0600 in its private home.

Verified probe session: `70b68fd3-6644-4d90-b5b2-04220015afa3`, November 14,
2026 at 00:34 Pacific. One model request used 1,656 input and six output tokens;
the CLI reported one premium request, no changed files and no tool executions.
Auto routing advertised only `mai-code-1.1-flash` for this account and selected
it. This does not establish access to Gemini, Claude or other models, nor does
it establish review quality or the exact account subscription/remaining quota.

Copilot CLI supports GitHub OAuth instead of a separate model API key. Verified
GitHub Education students may activate Copilot Student; education verification
and Copilot activation are separate. Organization policies and account limits can
still block use. Do not purchase a subscription, enable paid overages, create a
token or expand repository permissions without the owner's specific approval.

## Isolation and continuation

The separate `hids-copilot` system account has a nologin shell and private home.
Transient services have no capabilities or supplementary groups, cannot gain
privileges, hide HIDS paths and other `/opt` installations, protect the host
filesystem and permit writes only in the dedicated home. Device authorization
logs remain root-private under `/var/lib/hids-copilot/jobs`. The CLI may store its
OAuth credential in a private config file if no system credential store exists;
do not print, export or include it in any model request.

Actual running-login checks confirmed UID 990, all five capability sets zero,
NoNewPrivs enabled and denied reads of `/etc/hids`, `/var/lib/hids` and the Gemini
runtime. HIDS preservation matched the existing baseline across 396 files, Audit
rules/source prefixes/installed hashes and stopped M3 units; Audit stayed active.

The greeting probe disables built-in MCP servers, custom instructions, automatic
updates, session sync, experimental features and client telemetry. It supplies
a non-matching tool allowlist plus explicit shell/read/write/url/memory denies,
a three-minute runtime and resource limits. The live probe reported every
registered model tool disabled, all listed MCP servers disabled and no tool
execution events. It warned that the deliberately non-matching allowlist name
was unknown. Offline inspection
of the installed CLI parser found that an empty tool list becomes null/default,
so an empty list must not be used as a no-tools boundary. Provider requests
and provider-side logging are not disabled by client telemetry settings.

The integrated source review passed a synthetic bug test and a real review of
`api/development_install.py`, `api/dashboard_launch.py`, `api/dashboard_tls.py`
and `packaging/DEVELOPMENT.md`. The actual source review used auto-selected
`gpt-6-luna`; model availability/routing changed after the earlier greeting, so
that greeting's single-model catalog is historical rather than a current limit.
Review quality remains subject to independent verification.

## Routine review workflow

Prepare a private packet locally using `scripts/copilot_review.py packet --task
'A focused review question' --file api/example.py`. Choose actual inspected files;
redirect output to a private file or pipe. The existing validator in
`scripts/gemini_review.py` is reused locally and deployed beside the Copilot
controller. The packet retains its legacy `hids.gemini-review/1` format identifier;
that label does not invoke Google or require a Gemini runtime/login.

Transfer only that inspected packet to Linux 2 and pipe it to
`sudo /usr/local/bin/hids-copilot-review`. Never put source or tokens into shell
arguments, transcripts or public artifacts. The root controller validates input
before making a private job, uses Copilot's piped-prompt mode, bounds output/time,
stops the unit after failure/interruption and rejects failed/incomplete responses,
reported file changes or tool-execution events. It never executes model advice.
Private per-job request, JSONL output, stderr and result stay in
`/var/lib/hids-copilot/jobs`. A failed provider call is an intermediate result;
diagnose it without expanding access or automatically looping requests.

Twelve shared-packet/Copilot unit checks passed locally and on Ubuntu. The first
integration attempt with `-p` silently ignored piped source, returning that no
packet was supplied; this was rejected as integration evidence. The corrected
piped-prompt invocation exposed the exact synthetic source/task in the CLI's
user-message event and correctly identified `api/example.py:2`'s out-of-range
index. It omitted the requested arbitrary reply marker, so receipt was verified
against the actual submitted-message event rather than response formatting.

Synthetic passing job: `hids-copilot-review-08756e8b6ba54c17a4b62ae0e5c214c8`.
Real source review: `hids-copilot-review-943cc0071b28471bbfb5527db72f290a`,
normalized packet SHA-256
`f3d60483b5d634d8369b15cb27e319101a64ebc3bc2fc7e07135b8dc27dacc30`.
Both returned zero tool executions/file changes; the real review used one request
and about 29.7 seconds of provider time. Copilot identified account creation
preceding configuration preflight; independent inspection confirmed the retry
path and the fix was tested and packaged. See
[build follow-up evidence](../validation/copilot-build-followup.md).

Installed controller SHA-256:
`9bc99284c377cc9ae9a6b5b9c9ed22a39933992e2cde8dad809936ddf81764c2`.
Preserve the verified tool restrictions when extending the invocation.
Never send real HIDS records, private logs, databases, keys, VM credentials or
unrelated personal information. Do not reuse the owner's Git publishing tokens.

References: [CLI authentication](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli),
[installation](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli),
[programmatic controls](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference),
[student access](https://docs.github.com/en/copilot/how-tos/copilot-on-github/set-up-copilot/enable-copilot/set-up-for-students).
