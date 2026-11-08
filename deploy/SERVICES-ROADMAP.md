# Services roadmap

Decision date: 5 November 2026.

Use this plan to extend the existing Oracle Cloud Swarm. Implement one phase at a time through local changes, review, and the V2-to-main deployment workflow. This document records direction; it does not deploy services or authorize every future production operation.

## Agreed direction

- Keep AMD node 1 as manager, ingress, and host for the existing portfolio data.
- Use Ampere A1 as the compute worker with `workload.compute=true`.
- Use Authelia for individual accounts, MFA, and native OpenID Connect login where applications support it. Keep application permissions inside each application.
- Add monitoring and recovery coverage before expanding persistent services.
- Plan Rakazo for family and friends, with separate accounts/workspaces and isolated agent execution.
- Plan Outline for personal notes and selectively shared documents. Keep Fieldnotes for portfolio publishing.
- Remove IT-Tools and general formatting/conversion utilities from the roadmap.
- Leave the personal investment/trading app until last. Its new direction is Oracle Database plus Authelia, implemented in its own repository.

Use the owner console to manage access to the deployed Outline workspace and Vaultwarden web vault. See [account onboarding, permissions, and recovery](FAMILY-SERVICES.md). A developer secrets platform remains optional.

## Current topology and boundaries

| Node | Role | Current responsibility | Planned additions |
| --- | --- | --- | --- |
| AMD node 1 | Swarm manager; `portfolio.data=true` | Caddy, portfolio/Fieldnotes, Authelia, ntfy, Portainer, existing data | Keep core services here; move builds off the host |
| AMD node 2 | Worker; `portfolio.worker=true` | Uptime Kuma, Portainer agent | Keep monitoring data pinned to this worker |
| Ampere A1 | Worker; `workload.compute=true` | Portainer agent, service login proxies, Outline, PostgreSQL, Redis, and Vaultwarden | New application services, approved persistent workloads, later trading app |

### Capacity budget

Use these owner-reported provisioned capacities for planning:

| Node | Physical RAM | Provisioned storage | Swap |
| --- | --- | --- | --- |
| AMD node 1 | 1 GB | Approximately 47 GB | Configured |
| AMD node 2 | 1 GB | Approximately 47 GB | Configured |
| Ampere A1 | 24 GB | Approximately 95 GB | Not included in the application memory budget |

Swap helps the AMD nodes survive memory pressure, but it uses disk and is much slower than RAM. Budget services against physical RAM and leave headroom for Linux, Docker, and the Swarm agent. Do not count swap as additional capacity for databases, agents, or concurrent application workloads. Swapping can delay health checks and cluster communication.

Provisioned disk size is not the same as filesystem size or free space. Earlier inspections showed an approximately 30 GB root filesystem on these hosts. Recheck `lsblk`, `df -h`, and `swapon --show` before allocating storage; determine whether remaining capacity is already mounted or needs partition/filesystem expansion. Do not assume the full provisioned disk is available to Docker, or resize anything without checking the actual layout and backup coverage.

The cluster has approximately 26 GB of physical RAM and 189 GB of provisioned storage, but neither is a pooled resource for an individual container. Keep the small AMD nodes focused on existing core services and lightweight monitoring. Put heavier applications on Ampere, with explicit limits and per-node disk monitoring. Retained images, databases, attachments, agent workspaces, swap, and local backup staging all consume storage.

Swarm membership and labels live on the manager. Git controls service specifications. All three nodes run the global Portainer agent. Storage guards permit core data on node 1 and explicitly approved, exactly pinned worker bind directories. See [worker storage](STORAGE.md) and run the private cluster backup before adding application data. See [the Swarm runbook](SWARM.md).

One manager and node-local disks do not provide automatic control-plane, ingress, or data failover. Keep availability work separate from adding worker capacity. Do not promote Ampere or move existing portfolio data as part of this plan.

## Phase 1: deployment foundations

1. Make documentation-only changes skip application builds and rollouts. Test path classification so executable/configuration changes still deploy.
2. Build application images in GitHub Actions and publish versioned AMD64/ARM64 images to GHCR. Verify every target platform and deploy immutable registry digests.
3. Retain previous-release images, checks, and configuration for rollback. Preserve the bounded Docker-cancellation workaround until an upstream fix is tested.
4. Give each independently developed application a clear deployment owner and release boundary. Keep the trading app's code and release lifecycle in its own repository; do not place unrelated services in a stack managed by another repository's `--prune` deployment.

Done when a docs-only PR causes no rollout, an application release deploys by digest, and a controlled rollback succeeds. The phase-1 change adds the CI build/digest-pull path and keeps manual local builds as a fallback. Confirm the first merged workflow and recovery behavior before marking this phase complete.

## Phase 2: persistent storage and recovery

- Inventory each new service's database, files, encryption keys, image platforms, and recovery credentials.
- Extend placement validation to explicitly approved data nodes and service-specific storage. Keep one writer for local writable data, with stop-first updates.
- Extend the private PC backup kit for ARM images, worker configuration, and additional service state. The backup implementation lives outside Git; changes here alone cannot extend it.
- Consider encrypted Oracle Object Storage archives within the tenancy's verified free allowance. Retain an independent PC copy.
- Test recovery into a disposable environment, including credentials and encryption keys. Keep recovery material accessible if Authelia or the secrets service is unavailable.

Done when a new stateful service can be restored from the documented backup without relying on its original container. See [backup coverage](BACKUPS.md).

## Phase 3: monitoring

Uptime Kuma runs on AMD node 2 with worker-local storage and backup coverage. Open it from the admin dashboard to reuse your existing MFA session.

Keep Portainer for infrastructure operations and Kuma for availability history and alerts. Monitor public HTTPS, API readiness, certificate expiry, and eventually application-provided worker heartbeats and data-freshness checks. A successful HTTP response does not establish that imports are current.

Use consecutive failures, an outage notification, and a recovery notification to keep ntfy quiet. Add a check outside this cluster with an independent delivery path: node 1 hosts both ingress and ntfy. Require Authelia for the whole Kuma hostname, including status pages and WebSockets; retain its native administrator login. Keep ntfy protocol endpoints on native authentication for iPhone delivery, while gating its browser interface with Authelia. Do not assume Authelia creates per-user monitoring permissions inside Kuma. See [monitoring operations](MONITORING.md).

Done when a controlled outage and recovery produce the expected notifications without repeated alert noise.

## Phase 4: identity and access

- Create individual Authelia users and explicit application groups, with MFA and tested account recovery.
- Register a separate OIDC client and exact callback URLs for each compatible application. Use authorization code flow with PKCE and stable issuer/subject bindings.
- Use app-native authorization for workspace, document, and financial-data permissions. A reverse-proxy login gate alone does not create those permissions.
- Keep Portainer administration limited. Give collaborators only explicitly required resource access, accounting for Community Edition limitations.
- Test onboarding, cross-user isolation, logout, and offboarding. Revoke downstream sessions and scheduled jobs where needed; removing an identity-provider group may not invalidate existing application sessions.

Done when two test users can reach only their intended resources and offboarding removes continuing access.

## Phase 5: password and application secrets

Use different mechanisms for different consumers:

| Need | Direction |
| --- | --- |
| Service runtime credentials | Expand Docker Swarm secrets usage; version and rotate secrets deliberately |
| Family passwords and secure notes | Use the Vaultwarden web vault with Authelia OIDC and per-user service grants. Rehearse encrypted exports before storing important passwords. |
| Developer/CI environment secrets | Consider Infisical only if project/environment workflows justify another service |

Vaultwarden SSO authenticates the user; a master password still unlocks the vault. Verify clients, recovery, and two-user isolation before storing important credentials. Do not store passwords in Outline or Fieldnotes.

Infisical's generic OIDC on self-hosted instances currently requires an enterprise license. Do not assume a free Authelia integration or enable paid services without a separate decision.

## Shared model gateway before Rakazo

Run a shared OpenAI-compatible inference gateway on Ampere before adding Rakazo. Use OmniRoute, pinned to a tested ARM64 release, with its graphical provider, combo-routing and usage screens. Give applications stable model aliases and separate gateway credentials.

- Start with OpenRouter and Groq. Use the owner's provider accounts and enter keys privately into OmniRoute. Keep its persistent database and encryption material outside Git; give each application its own limited gateway key.
- Route chat and tool-using agents through separate approved model pools. Validate streaming, tool calls, context length and structured output with each candidate. Add vision only when a provider/model passes the image-input test.
- Use explicitly free OpenRouter model variants. Treat Groq access as an account-plan allowance and check its actual limits. Restrict destinations and model IDs. Keep paid routes and paid add-ons disabled.
- Prefer a tested primary model for an agent run. Fall back on eligible failures to another model with the required capabilities, with bounded retries and provider cooldowns. Respect retry/reset guidance. Stop with a clear quota error when all eligible routes are exhausted.
- Enforce request, token and concurrency limits per application, plus shared provider-account limits. A dollar budget alone cannot control zero-price traffic. Avoid retrying a partially delivered stream automatically.
- Keep the server API on a private overlay and authenticate applications with gateway keys. Protect the browser administration UI with Authelia MFA. Decide remote harness access separately because API clients cannot complete interactive browser login.
- Record provider, model, usage, latency and errors without retaining prompt or response contents by default. Add persistent gateway state to worker backups and rehearse restoring keys and policy.
- Connect Rakazo only after testing its custom model endpoint, authentication, streaming and tools against the gateway. Use a separate Rakazo key, and add future UIs with separate keys.
- Validate cross-application isolation, key revocation, quota exhaustion, upstream failures and free-only routing before production promotion.

Deploy the empty, administrator-only gateway first; see [OmniRoute](OMNIROUTE.md). The owner will enter the provider keys privately. Keep inference consumers disconnected until the approved models, ordered fallbacks and per-app limits pass real-provider tests.

References: [OmniRoute](https://github.com/cheaper-inference/OmniRoute), [OpenRouter free router](https://openrouter.ai/openrouter/free), [Groq limits](https://console.groq.com/docs/rate-limits), and [Rakazo model endpoints](https://github.com/elie222/rakazo/blob/main/docs/self-host-models.md).

## Phase 6: Rakazo pilot and shared use

Start with the [restricted runtime pilot and its isolation gates](RAKAZO.md). Rootless gVisor passed the offline ARM64 computer-image checks after the Incus confinement probe failed. Complete the application/controller integration before exposing Rakazo; keep model connections and agent execution disabled.

Run Rakazo application services on Ampere after validating its selected release, ARM images, Swarm adaptation, PostgreSQL persistence, and backup coverage. Its supported PostgreSQL dependency remains separate from the trading app's Oracle decision.

Use native Authelia OIDC and an explicit admitted-user group/registration policy. Test SSO-only login and email/identity claims with the actual versions. Give each family member or friend an individual account and workspace. Start with two users before expanding.

Separate agent execution from production administration. Do not give general-purpose agents the production Docker socket, manager SSH keys, or financial database credentials. Choose a dedicated sandbox host or remote provider after assessing isolation, resource limits, and costs; sharing an overlay network is not a security boundary against host Docker access.

Start with read-only research or repository summaries. Decide who supplies model keys, who pays, and how usage, concurrent agents, disk, and runtime are limited. Verify which limits the selected release actually enforces. Test that users cannot access each other's private agents/files/credentials and that account deactivation stops existing sessions and scheduled work.

Done when one useful scheduled workflow works for each of two isolated users with bounded resource use and successful recovery.

## Phase 7: Outline personal and shared notes

Use Personal documents and restricted collections in the deployed Outline workspace. Complete the owner sign-in before granting anyone else access.

- Authenticate each user through Authelia OIDC.
- Give users their own Personal space; use document invitations and restricted collections for selective sharing.
- Offer view/edit access explicitly. Disable public publishing by default if it is unnecessary.
- Test two-user isolation, sharing/revocation, search, exports, attachments, and restore behavior.
- Explain that application-private notes are not end-to-end encrypted against the server/database operator.

Keep Fieldnotes as the existing single-administrator blog and learning-note publisher. It has private drafts and public snapshots, not independent user libraries or shared-workspace permissions. See [Fieldnotes](FIELDNOTES.md).

Done when each user has private notes, can share a chosen document without exposing unrelated notes, and can recover their content.

## Phase 8: personal investment/trading app

Implement this last, in the separate `trading-app` repository. Its handoff document is `docs/oracle-authelia-decisions.md`.

Target Oracle Autonomous Database and native Authelia OIDC. Rework PostgreSQL-specific migrations and ownership isolation while preserving exact financial values, transaction semantics, sessions, MFA, and recovery. Keep React/FastAPI unless implementation evidence warrants a separate decision. Build a small owner-isolated vertical slice against Oracle before porting the full application.

The application runs on Ampere behind existing Caddy ingress. Confirm ARM compatibility, Oracle connectivity, hosted limits, and independent release/rollback boundaries. Start with synthetic data in staging. Do not enable live provider integrations merely because hosting is ready.

Done when hosted identity, cross-owner isolation, migration, backup/restore, and application monitoring tests pass. Database and auth migrations are not complete today.

## References and decisions to revisit

Verify current versions, licensing, free quotas, and tenancy availability before implementation. Free tiers are operating constraints, not guaranteed service availability.

- [Oracle Always Free Autonomous Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-always-free.html): a different engine from PostgreSQL, with resource and inactivity limits.
- [OCI managed PostgreSQL pricing](https://www.oracle.com/cloud/postgresql/pricing/): separate from the free Autonomous Database offer.
- [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm): check storage quotas against the account's status.
- [Authelia OIDC](https://www.authelia.com/integration/openid-connect/introduction/).
- [Rakazo accounts and OIDC](https://github.com/elie222/rakazo/blob/main/docs/self-host-accounts.md) and [production architecture](https://github.com/elie222/rakazo/blob/main/docs/self-host-production.md).
- [Outline Personal documents](https://www.getoutline.com/changelog/personal-documents) and [OIDC](https://www.getoutline.com/integrations/oidc).
- [Vaultwarden OIDC](https://github.com/dani-garcia/vaultwarden/wiki/Enabling-SSO-support-using-OpenId-Connect), [Swarm secrets](https://docs.docker.com/engine/swarm/secrets/), and [Infisical SSO licensing](https://infisical.com/docs/documentation/platform/sso/overview).


## Rakazo offline controller pilot

The offline controller, desktop screen and enforced per-computer limits now pass the private integration checks. Use the owner-only Authelia route and dashboard link for the fixed offline desktop. Check browser access and reconnect behavior after deploying the release. Model connections, full Rakazo agent jobs and additional users remain disabled. See [Rakazo pilot](RAKAZO.md) for the exact resume gate and disposable-storage limits.
