# Personal assistant capabilities

Use Rakazo's existing chat. The browser still requires the exact owner's Authelia MFA session. Auto still routes only through the restricted free-only pool. The offline gVisor computer remains separate from the networked connector service.

## Ask in chat

- Research: “Find the current Docker Swarm documentation and explain service placement. Cite the sources.” Public HTTPS search and page reading use a bounded reader; private addresses, cloud metadata, the three cluster addresses and local services are denied. Sources are untrusted data.
- Memory: “Remember that I prefer TypeScript examples.” Review the proposed memory and approve it. “Show my memories” and “Forget this preference” use the same chat; deletion also needs approval.
- Documents: attach a text, Markdown, CSV or JSON file up to 32 KB using native chat attachments. Uploads are explicit user actions and are indexed for the assistant. PDF, office documents, images and executable uploads are not supported in this release. Ask to list or read imported documents. Changes need approval.
- Outline: ask to search or read your notes, then propose a document change. New notes remain drafts. A changed document invalidates an older approval. Updates include Outline's `lastRevision` precondition; a concurrent edit prevents replacement. Deletion uses the trash, not permanent deletion, and rechecks the latest content before submitting.
- Reminders: ask for a reminder with an explicit date/time, or an hourly-or-slower recurring schedule. Review the absolute time, text and repeat interval before approval. Ask to list, pause, resume or delete schedules in chat.
- Research digests: schedules can include a search query. Delivery includes source titles, links and excerpts. This version does not run unattended model inference or produce an AI-generated scheduled briefing.

## Approve a change

Rakazo appends the exact stored proposal to the reply. Send `approve <id>` or `reject <id>` as a new message in the same chat. Approval is handled by the server before model inference; models cannot approve their own tool calls. A proposal belongs to one user, space and chat, expires after 15 minutes and executes at most once. Stop cancels pending proposals created by that run.

A failed or uncertain external write is not retried automatically. Check the target service before proposing another write. Stop can abort an in-flight request but cannot undo an external service's already-accepted change. Pausing a reminder prevents future deliveries; it cannot retract one already sent.

Keep 200 chat runs/day, 600 gateway calls/day, 12 calls/run, 32 tools/run, a ten-minute run deadline and one active foreground run. Store at most 100 memories and 100 imported documents per user/space. Memory entries are at most 2 KB and documents 32 KB. List memories in pages of 20. Reminder delivery has a separate limit of ten attempts/user/UTC day, at most ten active schedules, and no automatic catch-up or retries. Restarts pause interrupted deliveries for review.

## Private configuration and backups

`rakazo_assistant` runs as UID 1000 on Ampere with 256 MB RAM, half a CPU, a read-only root, no capabilities, no host socket and no published ports. Only the native API shares its tools network. Every internal request also requires a separate service secret, so connector peers cannot impersonate chat requests. A separate connector network reaches Outline and the owner directory check; a separate outbound network supports public HTTPS and the existing authenticated ntfy API exception.

Keep the configuration in `.secrets/rakazo/assistant_config` on the manager and the matching private recovery folder on your PC. It contains the exact owner ID/email, scoped Outline key and existing private ntfy publisher authorization. Never commit this file. No credentials enter the model or computer. Schedules recheck current owner access before notification delivery.

Back up `/srv/swarm/rakazo_assistant/assistant.sqlite` with the service stopped, alongside the API/database state and private configuration. The cluster backup's dynamic writer discovery must include `portfolio_rakazo_assistant`; test that before declaring backup coverage complete. Memory, documents, proposals and schedule text are private plaintext within the protected server volume, so encrypt transferred archives.

## Google and multiple accounts — deferred

Google connections remain disabled at the owner's request. Add them after this release, with account-specific consent:

1. Store each connection under `(user_id, provider, provider_account_id)` with encrypted tokens, granted scopes and revocation state. Keep multiple Google accounts separate, even when they belong to one user.
2. Start with Gmail read access and calendar read access. Let users choose which connected account supplies each request; never infer a sending account from a model guess.
3. Keep message/event drafts local. Sending, recipient changes, calendar writes and deletion need a stored proposal bound to the exact account, target, content and current user.
4. Use OAuth state, PKCE and exact callback validation. Verify the account identity after consent. Support disconnect/revoke and reject pending approvals when a connection changes.
5. Test cross-account and cross-user isolation, expired consent, uncertain sends and Stop before enabling writes. Keep Google tokens away from the model and computer.

References: [Outline API scopes](https://docs.getoutline.com/s/guide/doc/api-1rEIXDfLF6), [Google server-side OAuth](https://developers.google.com/identity/protocols/oauth2/web-server).

## Quotas and fallback

The shared router allowance is 500,000 tokens/day across the approved providers. It resets at 05:30 Asia/Kolkata. Keep the existing 200 runs/day, 600 model calls/day, four calls/minute, per-run output limits and Stop controls. Input history and tool results also consume tokens; raising the token allowance does not remove the other caps.

Individual provider quota failures fall through the approved free-only pool. The shared app allowance is a total cap and cannot be bypassed by changing provider. Quota failures show the sanitized token counts and reset time in the native error details. The adapter preserves the router error instead of turning it into a network connection failure; SDK retries are disabled because the router handles bounded fallback. Never display raw upstream credentials or headers.

## Longer tasks

Each run can use up to 12 model calls and 32 tools over ten minutes, with up to 4,096 output tokens per model response and 64 KiB of total displayed model text. The shared 500,000-token daily allowance still applies. Keep one active run, four calls/minute, existing resource limits and the offline computer boundary. Each shell command still has a 20-second deadline.

Rakazo waits for the next minute window before another model call instead of failing a fast multi-step task. The wait counts toward the ten-minute deadline, uses persistent call history and cancels when you press Stop. Stop also cancels model and connector requests and stops the isolated computer. No automatic continuation runs after Stop or a restart. Approvals for persistent changes remain required. Individual router requests retain their 55-second deadline.

The isolated controller bridge also enforces ten minutes and 32 shell tools. Deploy its `native-agent-bridge.mjs` module on Ampere and restart only the owner bridge while no run is active; the image rollout alone does not update this host module. Keep a private copy of the previous module for rollback.

The API entrypoint pins the internal runtime to 32 tools and 4,096 output tokens too. Its 120-second transport window accommodates up to 61 seconds of local rate-limit waiting plus the separate 55-second router deadline. Keep these startup values aligned with the native adapter; deployment environment variables cannot override them. The browser regression must execute more than eight tools to catch a stale startup cap.

When a run exhausts its 12 model calls, chat shows “Run model-call limit reached (12/12)” and asks for a new message. Local admission and call quotas keep their specific reason through the model SDK instead of appearing as connection failures. The adapter checks the run allowance before waiting for the next minute window and before sending a provider request. Rejected calls do not consume an extra ledger entry or provider request. A new message receives a new per-run allowance; daily counters remain shared.
