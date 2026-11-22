# Model gateway

> Current policy: Rakazo uses provider-managed usage with no local token allowances, context windows, daily run/call caps, minute pacing, cumulative tool/model-call limits or overall task deadline. Keep Stop, owner-only access, approvals, free-only routing and resource/individual-operation protections. Older quota values below describe the prior rollout. See [current policy](RAKAZO-PERSONAL-ASSISTANT.md#provider-managed-usage).

Open **OmniRoute** in the administrator dashboard, or use [the model gateway shortcut](https://rithvik.ddns.net/models). The shortcut opens `https://models.144.24.135.201.sslip.io/` on its own browser origin. Sign in through Authelia with MFA, then select OmniRoute's OIDC sign-in button if prompted. Reuse your existing Authelia session; do not create a separate OmniRoute password.

Only the infrastructure administrator can open this gateway. Family service grants do not give anyone access to provider credentials. Applications will receive separate inference keys, not your dashboard login or upstream provider keys.

## Add provider keys privately

1. Open **Providers** in OmniRoute. Select the provider and add an API-key connection.
2. Enter the key directly into that HTTPS form. Give the connection a descriptive name, such as `groq-personal-01` or `openrouter-free-01`.
3. Repeat for your other providers. Add another connection under the same provider when you have another legitimate key/account; do not concatenate keys into one field.
4. Use only providers and accounts you own or have permission to use. Multiple keys may share the same account quota; they do not multiply a provider's allowance.
5. Review each provider's account plan, allowed models and billing controls before running a connection test. A test can make an upstream inference request. Keep auto top-up and paid fallback disabled in the provider account.

Do not paste keys into chat, GitHub issues, repository `.env` files, screenshots or PRs. Provider connections live in OmniRoute's private data directory. Back up that directory and `server.env` together; losing encryption material can make stored credentials unusable. Treat downloaded configuration exports as secrets.

Add more providers through this screen, then test each candidate before adding it to an approved pool. Share provider names and routing preferences only; never send key values. Keep Rakazo disconnected until its controlled pilot.

## Choose the hierarchy and application limits

Use named **Combos** for the model pools, for example `chat-free` and `agent-free`. Choose ordered fallback and add only approved provider/model connections. Validate tool calls, streaming, context length and structured output for the agent pool before connecting Rakazo.

The initial policy hides paid models and automatic combos, exposes only configured combos, enables the strict free-access policy and enables the catalogue filter for providers marked as incompatible with proxy use. Do not treat that catalogue preference as a universal dispatch denial; the explicit consumer pool defines the admitted connections. No provider connections, combos or inference keys are created by bootstrap. These controls are an initial guard, not a guarantee that every provider account is unbillable: free-access filtering is route-dependent and can reject a provider whose quota guarantee it cannot verify. Do not weaken it just to make a test pass. Check provider-side billing restrictions and the actual dispatch path before enabling a consumer.

Create one inference-only API key per app, restrict its models/combos, and set request/token/concurrency limits. Dollar budgets alone do not constrain free traffic. Test exhaustion, revocation and fallback before distributing a key. This single-replica deployment uses in-memory rate limiting; restarts reset those counters. Add shared durable quota enforcement before promising restart-resistant limits or scaling replicas.

Use the usage dashboard for traffic, model, latency and failure information. Detailed request-body logging and stream capture are disabled. Do not turn on prompt/response capture for shared apps without deciding retention and access first.

## Agent pool (22 November 2026)

Open **Combos > agent-free** to inspect the saved priority order:

| Priority | Provider | Model |
| --- | --- | --- |
| 1 | Groq | `openai/gpt-oss-120b` |
| 2 | NVIDIA | `nvidia/nemotron-3.5-super-vl-120b-a12b` |
| 3 | Gemini | `gemini-3.1-flash-lite` |
| 4 | Kiro | `claude-haiku-4.5` |
| 5 | OpenRouter | `inclusionai/ling-3.2-flash:free` (quota-aware standby) |

Each target uses its selected existing provider connection. Keep retries at zero, global attempts at five, target timeout at 25 seconds and total combo timeout at 55 seconds. Limit each model to one concurrent request, with no queued requests or hedging. These are per-model ceilings, not a global one-agent concurrency guarantee. Keep strict free access, paid-model hiding, combo-only exposure, automatic-combo hiding and the proxy-compatibility filter enabled. Your provider accounts have no paid billing or automatic top-up.

The original Groq and NVIDIA candidates passed a synthetic function call with exact integer arguments, continuation after the tool result, streamed output and schema-constrained JSON. A separate temporary combo fell back from an unavailable model to Groq successfully. These small checks establish basic compatibility; they do not establish long-task reliability or maximum context capacity.

Leave Gemini 2.5 Flash out: the account returned HTTP 404 because that model is no longer available to new users. Leave the tested OpenRouter Nemotron free target out: the pre-dispatch filters skipped it. Test other candidates individually without relaxing the free-only policy.

The private **rakazo-pilot-disabled** key starts inactive; enable it only for the separately bounded [Rakazo pilot](RAKAZO.md#native-chat-limits-and-stop). Its historical name does not indicate its live active state. It has:

- Access to `agent-free`, plus the two exact canonical/resolved identifiers for its zero-priced OpenRouter target. Rakazo itself always requests `agent-free`; arbitrary direct models and automatic combos stay denied.
- Access to the five selected provider connections only; no management scope.
- Limits of 4 requests per minute, 600 requests per day and 500,000 tokens per day.
- Request-body logging disabled.

The disposable test key received 403 for direct-model, automatic-routing and management requests, 429 for request/token exhaustion, and 401 after revocation. The inactive Rakazo key also received 401. Temporary test routes and credentials are removed or revoked. SQLite stores token-limit definitions and counters; restart-resistant enforcement has not been exercised. Treat the daily token ceiling as a usage guard, not an exact per-request output reservation. Test overshoot and parallel requests before relying on it for shared users.

Keep ordinary Rakazo workspace model connections and jobs disabled. Only the separate bounded pilot may use this key and pool. Its controller enforces the output/context/call/deadline limits independently of gateway usage counters. Do not attach the sandbox desktop to the model network or give it provider keys.

Provider credentials, combo state and inference keys live in OmniRoute's private database; this repository records the operating policy, not a secret-bearing configuration export. On the PC, keep `Documents/Portfolio-private-backups/omniroute-routing-2026-11-21` alongside the full cluster backup. It contains integrity-checked before/after SQLite snapshots, matching encryption environment, the disabled pilot key, checksums and restore instructions. Use the full cluster backup for the service definitions and SSO recovery material. Never commit either backup.

## Deferred option: Gemini Web model-filter exception

Keep this option deferred. Do not change the live free-only policy or disable `hidePaidModels` globally.

OmniRoute 3.8.53 labels Gemini Web as free in its provider UI, but omits `gemini-web` from the shipped free-model catalog. Its connection-test filter therefore reports “Paid model blocked while hidePaidModels is enabled.” The global setting has no per-provider override in the connection edit dialog.

If we choose to support an exception later:

- Allow only the canonical `gemini-web` provider to use models that OmniRoute classifies as paid or does not recognize as free. Resolve its `gweb` alias to the same provider; do not extend the exception to the Gemini API or other Google providers.
- Keep every other provider subject to the free-only policy. Do not turn off the global filter to enable one connection.
- Apply and test the rule consistently across listings, connection/model tests, direct inference, combos, automatic routing and fallbacks. Audit the separate strict free-access policy too; a `hidePaidModels` exception alone may not permit dispatch.
- Keep MFA, current administrator checks, native owner restrictions and per-app inference-key limits unchanged.
- Test that Gemini Web is the only exception, including requests through aliases and fallback paths, before enabling it in production. Make the exception explicit and disabled by default so it can be removed easily.

This would require an upstream feature or a maintained OmniRoute customization, not just a change to the portfolio's provider settings. Allowing a model through the router does not grant a paid Gemini subscription, unlock restricted features, or bypass Google account quotas. Check the account's actual entitlement before adding models to an approved combo.

## Architecture

```text
Browser -> AMD1 Caddy -> Ampere oauth2-proxy -> OmniRoute dashboard
                              |                    |
                              +---- Authelia ------+

Future approved app -> private swarm_models_app -> OmniRoute /v1 -> providers
                       separate inference key
```

- Pin OmniRoute 3.8.53 by immutable multi-architecture image digest. Run one replica on Ampere's exact node ID with `workload.compute=true`.
- Store SQLite and generated encryption/session keys under `/srv/swarm/omniroute`, owned by UID/GID 1000 with private permissions. Do not move this task to another node without restoring its data.
- Cap the app at 1.5 GiB RAM and 2 CPUs; reserve 384 MiB. The SSO proxy has a separate 96 MiB limit.
- Keep host ports unpublished. Only the SSO proxy joins both `swarm_models_edge` and `swarm_models_app`; Caddy joins the edge network only. Do not attach unrelated services to the application network.
- Protect every public host route with the administrator-only Authelia OIDC proxy, including `/v1/*`. Native OmniRoute also requires OIDC and allows only the owner's email. Password login is disabled. Its native OIDC client uses the `omniroute_identity` claims policy to include `email` and `email_verified` in the ID token. OmniRoute checks those claims directly rather than fetching userinfo; omitting them rejects the owner and returns to login.
- Use `http://omniroute:20128/v1` for a future explicitly approved internal consumer, after attaching it to the private overlay and configuring its inference key. Browser-host URLs are not a remote harness API: external API access needs a separate design.
- Keep optional MCP, A2A, cloud sync and Radar off. Do not mount the host Docker socket or production SSH credentials.

## Bootstrap and deployment

Prepare secrets before merging the service catalog. `scripts/setup-omniroute.py manager` runs as `opc` on AMD1 and writes `.secrets/omniroute/recovery.json`, the proxy configuration and Authelia client hashes. Keep this recovery set private. The manager helper also needs `scripts/setup-family-services.py` alongside it.

Transfer the recovery JSON over SSH into `scripts/setup-omniroute.py worker` on Ampere's stdin. Keep `scripts/bootstrap-omniroute.mjs` alongside the worker helper. The worker verifies its node and storage mount, starts an unpublished temporary container, configures native OIDC through its authenticated settings API, and removes temporary credential files. The persistent completion marker prevents overwriting later provider settings. Do not delete it to repair a running installation; investigate or restore a matching backup instead.

Push the catalog, Caddy, Authelia and dashboard changes through the normal PR deployment. Never commit recovery JSON, provider credentials or the worker data. On a new installation validate HTTPS, rejection of anonymous management/inference calls, OIDC admission and persistent restart before adding keys.

## Back up and recover

Refresh the private PC cluster backup after entering providers or changing routing. `Backup-Cluster.ps1` in `Documents/Portfolio-private-backups` discovers the new worker writer automatically. Run its `-CheckOnly` mode first and confirm `/srv/swarm/omniroute` is included. The full backup also includes manager `.secrets`, Authelia state and current/previous service images.

Restore the entire OmniRoute directory, including `server.env`, SQLite files and the completion marker, while the service is stopped. Restore the matching manager OIDC secrets. Preserve UID/GID 1000 and private permissions. Start the exact saved image first, verify login and key decryption, then test one approved free model before reconnecting consumers. A service-spec rollback does not roll back database migrations; retain a pre-upgrade data snapshot.

See [cluster backup and restore](BACKUPS.md) and [Swarm operations](SWARM.md). Keep a local private copy of the bootstrap recovery set; its random management password is needed for sensitive settings changes even though interactive password login is disabled.

## Brief login errors

The edge renews its session in the background every two minutes on an incoming request. The browser ticket and refresh token expire after 30 minutes without renewal; access and ID tokens last five minutes. MFA is required for a new login grant. An active session renews without another MFA prompt. Parallel tabs or requests can also start more than one login. Keep `--cookie-csrf-per-request=true` on the OmniRoute SSO proxy so each flow retains its own CSRF/PKCE cookie; set the existing-cookie limit to eight (the proxy may retain those plus the newest flow) to bound request-header size. Do not disable PKCE or extend access indefinitely to hide callback failures.

If a login started before a proxy update fails, open `/models` again to start a fresh flow. For recurring errors, compare the proxy callback timestamp with Authelia's token-exchange log. A PKCE mismatch followed by an authentication-method error can be the OAuth library retrying a failed exchange; do not change the registered client authentication method just because that secondary error appears.

## Background session renewal

Use the dedicated `omniroute_sessions` Redis service for encrypted proxy sessions and renewal locks. Only the OmniRoute proxy joins its private overlay. Redis has no published port, disk persistence or provider credentials; losing this cache requires a fresh login and does not affect OmniRoute data. Do not reuse the Outline database/cache network for authentication sessions.

The edge OIDC client requests `offline_access` and the refresh-token grant. Authelia may ask you to approve this scope once. Its dedicated claims policy supplies administrator groups at login, and the proxy checks the signed `admins` claim. Authelia 4.39 can retain original ID-token group claims during refresh, so Caddy also checks the current enabled account and `admins` membership through the private access console on every application request. Caddy discards browser-supplied identity headers and uses only the verified proxy response. The check fails closed for missing, disabled, deleted, ambiguous or non-admin accounts. Keep the native OmniRoute owner allowlist and password-login prohibition unchanged. Do not remove the MFA authorization policy, expose health endpoints, or lengthen token validity to mask renewal failures.

Sign out through `/oauth2/sign_out` on the models host to remove the proxy session. Logging out of Authelia alone is not a guarantee that an already-issued application refresh grant is revoked. For emergency offboarding, disable the account/remove its administrator membership and verify denial on the next application request; revoke the grant or clear the affected Redis session if immediate invalidation is required. Current directory changes apply on the next application request, independently of token renewal. A long-running WebSocket is not reauthorized until it reconnects.

When testing, use a disposable MFA-enrolled identity, poll `/api/health/ping` for longer than five minutes with redirects disabled, confirm renewal in proxy logs, then remove its administrator group and confirm access is denied immediately. Also try a forged identity header without a session and confirm rejection. Delete the disposable identity and session afterward. Do not use provider API keys for this check.

The daily token allowance is shared across the approved providers and resets at 00:00 UTC (05:30 Asia/Kolkata). Provider quota/rate-limit failures should fall through the ordered free-only pool; exhausting the shared app allowance stops requests until reset. Never bypass it by rotating keys or using paid models.

## Expanded Rakazo pool (22 November 2026)

Use this order: Groq `openai/gpt-oss-120b`, NVIDIA `nvidia/nemotron-3.5-super-vl-120b-a12b`, Gemini `gemini-3.1-flash-lite`, Kiro `claude-haiku-4.5`, then OpenRouter `inclusionai/ling-3.2-flash:free`. Keep the 55-second total combo deadline, 25-second target deadline, zero retries and five maximum target attempts. Quota failures can fall through immediately; slow targets may consume the total deadline before every target is attempted.

Gemini and Kiro passed tool calls, tool-result continuation and streaming. Groq and NVIDIA retain their earlier successful checks. OpenRouter's current public catalogue reports zero input/output pricing and tool support for the selected `:free` model, but its upstream returned 429 during these checks. Keep it as a quota-aware last fallback; do not claim a successful end-to-end tool test for it yet. Its canonical and resolved identifiers need narrow model grants on the private app key; no wildcard or paid-model grants are allowed.

A temporary route with quota-exhausted OpenCode first and Groq second returned a successful streamed Groq reply. Do not rotate keys to evade a provider's account-wide quota. If every eligible provider is unavailable, report the failure instead of selecting a paid route.

Leave these linked connections out of the active agent pool until a bounded retest passes:

| Provider | Current blocker |
| --- | --- |
| SambaNova | Llama 3.3 70B returned unavailable; GPT-OSS 120B required a payment method. |
| Ollama Cloud | Kimi K2.6 requested usage credits or a subscription. |
| HuggingChat | The endpoint returned HTML where the connector expected JSON. |
| OpenCode Zen | Big Pickle reported its free usage quota exhausted. |
| Vercel AI Gateway | Its public catalogue listed zero-priced models, but the tested Nemotron Lightning free target was skipped by the existing pre-dispatch filters. |

Keep paid-model hiding and strict free access enabled. Do not relax these settings to make a failing test pass. Provider availability and free entitlements can change; recheck them before adding or replacing a target.


## Free-pool fallback order and Groq 413

Use this priority order for `agent-free`: Groq GPT-OSS 120B, Gemini 3.1 Flash Lite, Kiro Claude Haiku 4.5, NVIDIA Nemotron 3.5 Super VL, then OpenRouter Ling 3.2 Flash `:free`. Keep strict free-only access and the existing pinned provider connections. This order lives in OmniRoute's private database; changing a repository file alone does not update it. Back up the combo before changing its model order through the management API.

Groq can reject a single large request with HTTP 413 when it exceeds the account's model-specific tokens-per-minute allowance. On 23 November 2026 IST, the recent error reported an 8,000-token allowance and a 40,647-token request. Retrying that same oversized request on Groq will not help. Let the priority combo advance to another free provider; do not trim history or introduce a local token budget. See [Groq rate limits](https://console.groq.com/docs/rate-limits).

Matching synthetic 600-word explanation probes took 4.8 seconds on Groq, 5.2 on Gemini, 7.0 on Kiro and 11.2 on NVIDIA. Small tool-call probes were different: NVIDIA took 0.7-1.0 seconds, Groq about 0.75, Gemini 1.9-2.7 and Kiro 1.3-2.4. These small samples guide the order; they are not a performance guarantee. OpenRouter's isolated probe encountered a key/model authorization rejection, so do not treat its probe as a provider speed measurement or a verified working fallback. Keep it last pending a separate authorization review.

A synthetic oversized streaming request through Rakazo's production inference key produced Groq 413, followed by Gemini 200 with 76,319 reported input tokens and a valid tool call. The client received a complete successful stream in about four seconds without a stream error. No tool was executed and no user documents were used. Preserve all five candidates, no same-provider retries, no token quotas, Stop and free-only access.

Fallback can hide a provider rejection before output reaches the client. It cannot promise uninterrupted execution when every free provider rejects the request or after a partially delivered response; report that failure accurately rather than silently enabling paid routes or replaying actions.
