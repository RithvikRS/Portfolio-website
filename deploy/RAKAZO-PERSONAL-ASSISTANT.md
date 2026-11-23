# Personal assistant capabilities

Use Rakazo's existing chat. The browser requires Authelia MFA and a current Rakazo access grant. The infrastructure owner retains access; other accounts need the Rakazo grant in Service access. Auto still routes only through the restricted free-only pool. The offline gVisor computer remains separate from the networked connector service.

## Ask in chat

- Research: “Find the current Docker Swarm documentation and explain service placement. Cite the sources.” Public HTTPS search and page reading use a bounded reader; private addresses, cloud metadata, the three cluster addresses and local services are denied. Sources are untrusted data.
- Memory: “Remember that I prefer TypeScript examples.” Review the proposed memory and approve it. “Show my memories” and “Forget this preference” use the same chat; deletion also needs approval.
- Documents: attach a text, Markdown, CSV or JSON file up to 32 KB using native chat attachments. Uploads are explicit user actions and are indexed for the assistant. PDF, office documents, images and executable uploads are not supported in this release. Ask to list or read imported documents. Changes need approval.
- Outline: ask to search or read your notes, then propose a document change. New notes remain drafts. A changed document invalidates an older approval. Updates include Outline's `lastRevision` precondition; a concurrent edit prevents replacement. Deletion uses the trash, not permanent deletion, and rechecks the latest content before submitting.
- Reminders: ask for a reminder with an explicit date/time, or an hourly-or-slower recurring schedule. Review the absolute time, text and repeat interval before approval. Ask to list, pause, resume or delete schedules in chat.
- Research digests: schedules can include a search query. Delivery includes source titles, links and excerpts. This version does not run unattended model inference or produce an AI-generated scheduled briefing.

## Approve a change

Rakazo appends one numbered review with the exact changes. Reply in the same chat:

- `approve all` or `I approve all 3` to accept the displayed batch.
- `approve 1 and 3` to accept selected proposals, or `reject 2` to decline one.
- `I approve` when the review contains just one proposal.
- `reject all` to decline the batch.

Approvals go directly to the server without another model call or repeated drafting. Numbers refer only to the latest displayed review in that chat. A vague approval with several proposals asks you to choose; it does not guess. Existing `approve <id>` commands still work, including several commands in one message. Identical pending proposals reuse the same stored change.

A batch executes sequentially and reports each result. If a write fails, later items are not attempted; completed writes are not rolled back. A batch containing an expired or already-handled proposal is rejected before starting new writes. Approve the remaining numbered items individually after checking the result. Models cannot approve their own tool calls. A proposal belongs to one user, space and chat, expires after 15 minutes and executes at most once. Stop cancels pending proposals created by that run.

A failed or uncertain external write is not retried automatically. Check the target service before proposing another write. Stop can abort an in-flight request but cannot undo an external service's already-accepted change. Pausing a reminder prevents future deliveries; it cannot retract one already sent.

Keep one active foreground run and provider-managed usage. Store at most 100 memories and 100 imported documents per user/space. Memory entries are at most 2 KB and documents 32 KB. List memories in pages of 20. Reminder delivery has a separate limit of ten attempts/user/UTC day, at most ten active schedules, and no automatic catch-up or retries. Restarts pause interrupted deliveries for review.

## Private configuration and backups

`rakazo_assistant` runs as UID 1000 on Ampere with 256 MB RAM, half a CPU, a read-only root, no capabilities, no host socket and no published ports. Only the native API shares its tools network. Every internal request also requires a separate service secret, so connector peers cannot impersonate chat requests. A separate connector network reaches Outline and the owner directory check; a separate outbound network supports public HTTPS and the existing authenticated ntfy API exception.

Keep the configuration in `.secrets/rakazo/assistant_config` on the manager and the matching private recovery folder on your PC. It contains the exact owner ID/email, scoped Outline key and existing private ntfy publisher authorization. Never commit this file. No credentials enter the model or computer. Schedules recheck the recipient's current Rakazo access before notification delivery.

Back up `/srv/swarm/rakazo_assistant/assistant.sqlite` with the service stopped, alongside the API/database state and private configuration. The cluster backup's dynamic writer discovery must include `portfolio_rakazo_assistant`; test that before declaring backup coverage complete. Memory, documents, proposals and schedule text are private plaintext within the protected server volume, so encrypt transferred archives.

## Google and multiple accounts — deferred

Google connections remain disabled at the owner's request. Add them after this release, with account-specific consent:

1. Store each connection under `(user_id, provider, provider_account_id)` with encrypted tokens, granted scopes and revocation state. Keep multiple Google accounts separate, even when they belong to one user.
2. Start with Gmail read access and calendar read access. Let users choose which connected account supplies each request; never infer a sending account from a model guess.
3. Keep message/event drafts local. Sending, recipient changes, calendar writes and deletion need a stored proposal bound to the exact account, target, content and current user.
4. Use OAuth state, PKCE and exact callback validation. Verify the account identity after consent. Support disconnect/revoke and reject pending approvals when a connection changes.
5. Test cross-account and cross-user isolation, expired consent, uncertain sends and Stop before enabling writes. Keep Google tokens away from the model and computer.

References: [Outline API scopes](https://docs.getoutline.com/s/guide/doc/api-1rEIXDfLF6), [Google server-side OAuth](https://developers.google.com/identity/protocols/oauth2/web-server).

## Provider-managed usage

Rakazo has no local daily run/token/call quotas, per-run model/tool counts, minute pacing or overall task deadline. The router key has no local request/token allowance. Provider quotas and free-only availability still apply; keep provider-side cooldowns and bounded fallback.

Stop cancels the active run, outstanding model/tool requests and isolated computer. Keep one active run, granted-user Authelia MFA, explicit approvals, persisted accounting and restart/replay protection. Do not automatically resume stopped or interrupted work.

CPU/RAM/PID and sandbox network limits remain. Rakazo sends no max_tokens/max_completion_tokens/max_output_tokens allowance, applies no local model context window, and streams model output without a byte-size cutoff. Provider context/output ceilings still apply. Shell-command deadlines and transport failure detection remain operational safeguards. These do not impose a cumulative task-duration or usage quota. Reminder delivery and note storage safeguards remain separate from chat usage.

The API entrypoint sets MAX_TOOL_CALLS_PER_TURN=0 (the upstream runtime's unlimited setting). Deploy the matching native-agent-bridge.mjs on Ampere: it has no overall timer or cumulative tool counter. The regression completes 40 tools and 41 model calls, then checks Stop.

Retain the upstream stalled-loop guard: repeated failing or near-identical actions can stop early with an explicit stuck-loop message. This is progress detection, not a cumulative tool quota; a progressing sequence can exceed 32 tools.


## Provider-owned token limits

Do not set a replacement token number. The native gateway omits token-budget fields even if an SDK supplies defaults. The native context policy passes the full prepared history through without token-budget truncation. Remove stale RAKAZO_LOCAL_MAX_TOKENS and RAKAZO_LOCAL_CONTEXT_WINDOW settings at startup.

Run scripts/configure-rakazo-token-policy.mjs using a private, temporary management credential, the Rakazo inference key ID, and a private backup path. It preserves strict free-only access, removes saved token-quota records and request-rate allowances for that key, disables router compression for it, and installs token-field filters for the five providers in agent-free. Gemini and Kiro use provider-default generation settings so translated token defaults do not become local ceilings. Keep the policy backup outside Git and revoke the temporary management token afterward.

When adding a provider, verify its final request translation does not introduce a token budget. Providers requiring an explicit maximum need their documented provider maximum; never substitute an arbitrary local number. Provider quota, context and output errors remain provider failures, not a reason to enable paid models.


## Recover an interrupted task

A provider quota, context, authorization or availability failure explains the category in chat. Keep the partial reply and completed work. Send a new message to continue from the last result; inspect completed actions first. Never automatically replay a failed write or approve stale proposals after a failed run. Stop, provider failure and server interruption have separate recorded outcomes.

The free-only router may try another eligible provider. When it exhausts those routes, report the error and preserve the conversation. Do not enable a paid model, add local token caps or silently restart the task. Revoking Rakazo access aborts an active run at its next tool/model boundary or background access check.

## Members and private connections

Grant **Rakazo** in the existing Service access console. Use a unique verified email per account, and have each member enroll MFA. Existing administrators do not inherit Rakazo access unless they are the infrastructure owner or explicitly granted access. The application checks the live directory during sign-in and subsequent authenticated requests; a cached browser session does not override a revoked grant.

Native workspace membership and database row policies govern conversations and files. Assistant memories, imported documents, approvals and reminders also carry the authenticated user and workspace identity. A member cannot approve or stop another member's run by guessing an ID. The shared free-only pool keeps provider credentials on the server.

Outline and ntfy connections are separate from the Rakazo login grant. New members do not inherit the owner's connections. For now the operator configures these privately; there is no self-service credential-entry screen:

1. Have the member create their own scoped Outline API key and private ntfy topic/account. Give them access only to their own topic and permitted Outline collections.
2. Find their native Rakazo user ID after their first successful sign-in. Verify the email against Service access.
3. Add an entry to the private `assistant_config` secret under `users[<native user ID>]`, with `email`, `outline: { token }` and `ntfy: { topic, authorization }`. Keep the existing owner fields intact. Do not copy another user's credentials.
4. Refresh the Swarm secret through the existing deployment procedure, then test that member's read, proposal, approval and notification flow. Changing the bound email disables that connection until you deliberately update it.
5. Refresh the private backup after changing connections. Never store this configuration or keys in Git, chat, tests or model prompts.

A member without a connector can still chat, research and use personal workspace files/memory. Outline and reminders report that the connection is missing. Removing a login grant does not erase data or revoke an external API key; revoke external credentials separately during offboarding.

Each native computer receives a user-and-workspace-specific home and supervisor identity. The shared maintenance desktop stays owner-only. Computer homes are disposable and share the bounded runtime filesystem; save important results to the backed-up application workspace. One computer can run at a time across this small host. CPU/RAM/PID and network isolation remain active.

## Acceptance checklist

Use disposable notes and files, and inspect the resulting state:

- Research a public topic and check the cited pages; distinguish source facts from inference.
- Propose a memory, workspace document and Outline draft. Approve selected items, reject another, and confirm only approved changes exist.
- Schedule a private reminder, verify its recipient, then pause/delete it through approval.
- Use two granted test identities to check separation of private workspaces, memories, approvals, connector credentials and sandbox homes.
- Stop a streamed reply or computer task. Confirm pending proposals are cancelled and the computer stops; a fresh message can start new work.
- Simulate provider quota/context/unavailability failures. Confirm clear errors, preserved partial output, and no replay of writes.
- Revoke a member's grant during a task. Confirm subsequent requests and tools fail closed.
- Run the full private cluster backup, verify its manifest/checksums, and confirm all services return to their required replica counts.

Google remains the last phase. Each person will connect their own account(s) with OAuth consent; do not configure one shared Google connection for everyone.
