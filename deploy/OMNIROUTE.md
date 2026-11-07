# Model gateway

Open **OmniRoute** in the administrator dashboard, or use [the model gateway shortcut](https://rithvik.ddns.net/models). The shortcut opens `https://models.144.24.135.201.sslip.io/` on its own browser origin. Sign in through Authelia with MFA, then select OmniRoute's OIDC sign-in button if prompted. Reuse your existing Authelia session; do not create a separate OmniRoute password.

Only the infrastructure administrator can open this gateway. Family service grants do not give anyone access to provider credentials. Applications will receive separate inference keys, not your dashboard login or upstream provider keys.

## Add provider keys privately

1. Open **Providers** in OmniRoute. Select the provider and add an API-key connection.
2. Enter the key directly into that HTTPS form. Give the connection a descriptive name, such as `groq-personal-01` or `openrouter-free-01`.
3. Repeat for your other providers. Add another connection under the same provider when you have another legitimate key/account; do not concatenate keys into one field.
4. Use only providers and accounts you own or have permission to use. Multiple keys may share the same account quota; they do not multiply a provider's allowance.
5. Review each provider's account plan, allowed models and billing controls before running a connection test. A test can make an upstream inference request. Keep auto top-up and paid fallback disabled in the provider account.

Do not paste keys into chat, GitHub issues, repository `.env` files, screenshots or PRs. Provider connections live in OmniRoute's private data directory. Back up that directory and `server.env` together; losing encryption material can make stored credentials unusable. Treat downloaded configuration exports as secrets.

Start with your four or five providers, then share **only their names and the routing order you want**. Keep app keys and harness connections unconfigured until we test the models and limits. You do not need to send the key values.

## Choose the hierarchy and application limits

Use named **Combos** for the model pools, for example `chat-free` and `agent-free`. Choose ordered fallback and add only approved provider/model connections. Validate tool calls, streaming, context length and structured output for the agent pool before connecting Rakazo.

The initial policy hides paid models and automatic combos, exposes only configured combos, enables the strict free-access policy and excludes providers marked as incompatible with proxy use. No provider connections, combos or inference keys are created by bootstrap. These controls are an initial guard, not a guarantee that every provider account is unbillable: free-access filtering is route-dependent and can reject a provider whose quota guarantee it cannot verify. Do not weaken it just to make a test pass. Check provider-side billing restrictions and the actual dispatch path before enabling a consumer.

Create one inference-only API key per app, restrict its models/combos, and set request/token/concurrency limits. Dollar budgets alone do not constrain free traffic. Test exhaustion, revocation and fallback before distributing a key. This single-replica deployment uses in-memory rate limiting; restarts reset those counters. Add shared durable quota enforcement before promising restart-resistant limits or scaling replicas.

Use the usage dashboard for traffic, model, latency and failure information. Detailed request-body logging and stream capture are disabled. Do not turn on prompt/response capture for shared apps without deciding retention and access first.

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
