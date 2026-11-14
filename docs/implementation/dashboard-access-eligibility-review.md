# Dashboard access eligibility — owner decision D-12a

Status: **D-12a accepted by the owner, November 12, 2026.** The owner answered
yes to explicit root/sudo authorization for each new dashboard session. D-12b
subsequently accepted the separate synthetic-only mechanism; that bounded pilot
is now implemented and tested. No real-data API or persistent grant is enabled.
[Accepted mechanism](dashboard-session-mechanism-review.md);
[executed evidence](../validation/dashboard-session-pilot.md).

## Existing authority

[Threat model access policy](../threat-model.md#71-access-policy) restricts human
security-data access to root. Before this decision, sudo-administrator eligibility
was explicitly undecided; the accepted amendment is now recorded there. The [readiness decision register](v0.1-implementation-plan.md#decision-register)
D-12 reserves eligibility and mechanism to the owner. [Product experience](../product-experience.md)
requires an ordinary browser without making frontend visibility authorization;
Python remains unprivileged. Full VM automation access is not product-user access.

## Accepted policy

Permit a local administrator to authorize a new dashboard session by explicitly
executing a narrowly scoped HIDS access action as UID 0, including through an
OS-authorized sudo invocation. A normal account, group membership, local HTTP
connection or previous service-account access must not grant dashboard access.
No automatic session on login/boot, permanent administrator-group bypass, separate
HIDS password or privileged browser is proposed by this eligibility decision.

The intended user experience is an explicit root authorization step, then viewing
already stored information in the ordinary local browser. Collection remains
separately root-selected/confirmed; opening a session never starts a source,
changes logging policy, enables a rule or authorizes remediation.

The alternative is direct root-account authorization only, excluding authorization
through sudo for ordinary administrator accounts. Distinguishing human/account
provenance requires its own reviewed mechanism; UID alone cannot distinguish how
a root process was started. No Audit login field, caller-supplied environment,
username, frontend claim or group membership may be guessed into that authority.

## Recorded owner decision

May an administrator authorize each new dashboard session by successfully running
the HIDS access command through sudo, as well as through direct root invocation?
Owner answer: **yes**. Require explicit authorization per new session and grant
no access from group membership alone. This accepts the policy above.

Eligibility alone did not pre-approve that command. The separately accepted
[D-12b packet](dashboard-session-mechanism-review.md) provides the concrete review of the privilege boundary, one-time
bootstrap/session transport and storage, expiry/revocation, Host/Origin/CSRF,
untrusted event rendering, same-account browser risks and failure behavior.
Review the exact endpoints/data view and dependency/build plan before sensitive
HTTP access. No authentication endpoint or persistent grant is authorized merely
by accepting eligibility. Commits/pushes and Mac system changes remain separate.
