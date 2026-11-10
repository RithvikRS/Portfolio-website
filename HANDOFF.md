# Handoff: Rakazo workspace integration

Checkpoint date: 10 November 2026. Branch: `codex/rakazo-workspace-integration`.

**This branch is for transfer and continued work. Do not merge or deploy it yet.** The service catalog deliberately contains an invalid application image digest until a tested image is published. Production still runs the existing owner-only offline desktop pilot.

## Open on another laptop

```powershell
git clone --branch codex/rakazo-workspace-integration https://github.com/RithvikRS/Portfolio-website.git
cd Portfolio-website
```

Install Git, Python 3, Node.js (the portfolio requires at least 22.9; Node 24 matches the container tooling), and pnpm. Run `pnpm install --frozen-lockfile` for local portfolio dependencies. Open this folder in Codex and read this file plus [the detailed checkpoint](deploy/RAKAZO-WORKSPACE-CHECKPOINT.md).

Git does not transfer the prior chat or private recovery files. Transfer `Desktop/Oracle Cloud` and `Documents/Portfolio-private-backups` securely and separately, never through Git. Update Windows paths in connection scripts and private `backup-settings.json` if the new username or location differs. Restrict SSH private-key permissions to the intended account. Keep the iPhone authenticator available for the final browser login check.

The upstream source checkout is optional: the build uses the pinned upstream image. If source inspection is needed, clone `https://github.com/elie222/rakazo.git` at tag `v0.8.0` outside this repository and verify commit `747ece9641dcc60c95467ffae8ab2311fb1f3f81`.

## Keep these boundaries

- Admit only the existing owner through Authelia MFA and native OIDC. Keep verified-owner checks in the API.
- Keep model connections, provider credentials, agent execution, schedules and native per-workspace computers disabled.
- Keep the existing desktop isolated. Its home is disposable; workspace notes use the new database and encryption key.
- Preserve production services, current/previous images and the separate rootless engine. Do not restart production Docker, weaken the firewall or change manager roles to complete this integration.
- Reuse the already-created private recovery set; do not regenerate or publish credentials. Keep the private backup toolkit outside Git.
- The latest instruction authorizes only pushing this checkpoint, not merging or deploying it. Resume testing without treating this handoff as permission to publish a production release.

## What is ready

- API patch with exact request/procedure allowlists, verified-owner checks and independent execution/job-publishing denial.
- Restricted web screen for workspace, inert bot-profile and note management; dashboard/logout navigation and a separate offline-desktop link.
- Three proposed Ampere services: API, web and PostgreSQL 18, with private networks, resource limits and file-backed secrets.
- Candidate Caddy/Authelia configuration, bootstrap helper, build helper and disposable integration-test fixture.
- Private OIDC/database/encryption material on the manager, backed up on the PC under `Portfolio-private-backups/rakazo-workspace/`.

The previous ARM build passed 52 API tests, four UI tests, and API/web compilation. Candidate Caddy and Authelia configurations validated. The final image assembly did not finish: BuildKit duplicated base layers and exhausted root space. Its build was canceled and unused cache removed; existing services passed health checks afterward. Approximately 4.5 GiB root and 35 GiB data space remained at that checkpoint; recheck before doing any work.

The helper now uses an incremental commit of the stopped, bounded compiler container, with production defaults and disk guards. Its unit tests pass, but this new assembly method has not run successfully on Ampere yet. No derived app image has been published, no new app database has been bootstrapped, and no full-app service has been deployed.

## Remaining work, in order

1. **Recheck state.** Inspect Git, node/service health and disk space. Refresh staged public scripts on the servers; their staged build helper is older than the version in this branch. Do not accidentally run the old BuildKit path.
2. **Finish the ARM image.** On Ampere, run the build helper's `--sudo --check-only`, then the bounded build. Verify its image configuration and provenance. Keep the resource and disk guards; do not delete rollback images.
3. **Run real integration tests.** Use `deploy/rakazo/verify-workspace.postgres.test.ts` only with a fresh disposable `rakazo_workspace_verify_*` database and separate runtime/migration roles. Verify native OIDC owner admission, rejection of other identities, CRUD persistence, and no tasks, model credentials, provider calls or queued agent work.
4. **Test the web service and UI.** Exercise the proposed read-only filesystem, writable tmpfs paths, startup limits, workspace/profile/note controls and dashboard/logout links. Check the `/computer/` prefix for the retained pilot. Keep test data separate from production.
5. **Prepare release and recovery.** Publish the tested ARM image by immutable registry digest, replace both placeholder catalog references, and validate the dedicated database bootstrap and runtime row-level-security restrictions. Back up the new state and matching encryption keys, and rehearse restoring them into a separate database.
6. **Complete documentation and review.** Update `deploy/RAKAZO.md`, the service roadmap and recovery instructions to describe the finished behavior. Run repository checks, inspect the staged diff for secrets and review the combined change before any PR merge. Keep CI usage low by batching the integration into one PR when ready.
7. **Only when production deployment is authorized:** follow the detailed checkpoint's promotion steps, move only the pilot bridge assets to `BASE_PATH=/computer`, and verify every service, private route, network/model restriction and desktop connection. Ask the owner to finish the real Authelia browser sign-in; an emulated OIDC test does not replace that check.

The private backup helper now has a bounded, disk-free export-size measurement fallback for shared image layers; its 42 tests passed. Those changes are in the transferred private folder, not this Git branch. A full-cluster snapshot from earlier on 10 November is also there, but it predates the full-app integration. Do not treat it as a backup of application data that has not been deployed yet.

## Suggested prompt for the next chat

> Read HANDOFF.md and deploy/RAKAZO-WORKSPACE-CHECKPOINT.md. Inspect the current branch and live state before continuing. Keep Rakazo owner-only behind Authelia, all model connections and agent execution disabled, and secrets outside Git. Start with the revised bounded ARM build and disposable integration tests. Do not merge or deploy this checkpoint without my instruction.
