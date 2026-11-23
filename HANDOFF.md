# Handoff: Rakazo member-access release checkpoint

## Stop here

The user asked to find a good place to stop. Keep production on the previous release. Do not rerun deployment, reapply the controller migration or merge the pending fix until the user resumes work.

Local branch: `codex/rakazo-sso-rollout`. Main contains merged [PR #78](https://github.com/RithvikRS/Portfolio-website/pull/78), commit `2834ad3125dfcef74d506e77133d65d9b656c11a`, but that release rolled back. Git main and the running release intentionally differ at this checkpoint.

## Production state

- All 26 services reached their desired replicas after rollback, including the Portainer agent at 3/3.
- Rakazo API, web, executor and assistant use the previous image `ghcr.io/rithvikrs/portfolio-website@sha256:ac550bda3a57883860d60bc52b16df6739937c4233b70e39bdae1793a2e34e97`.
- The old run-ID-only controller contract and legacy bounded home mount are restored. API admission is back at one replica. All three isolated runtime services are active; no agent marker or disposable computer remains.
- The new family homes remain preserved in the bounded cache. The original migration record and bridge snapshots remain on Ampere. Do not overwrite or delete them.
- No member accounts/grants were created. Google remains disabled. Keep free-only routing, no local token/usage/task-duration caps, MFA, approvals, Stop and CPU/RAM/PID/network protections.

## Completed work and evidence

PR #78 adds explicit Rakazo grants, live grant/revocation checks, scoped workspace/assistant/connector data and computer homes, plus preserved partial progress and manual continuation after provider errors. Members do not inherit the owner's Outline or notification credentials.

The published candidate is `ghcr.io/rithvikrs/portfolio-website@sha256:9e4f19c5d06883662825d79a4c0eeafff501b5e4594c8500bedfaa4a8ab2eec0`. [Image publication](https://github.com/RithvikRS/Portfolio-website/actions/runs/45246925693) passed. The temporary Actions download secret and draft transfer release were removed. No image rebuild is needed for the pending rollout/migration-helper fix.

Validation before rollback:

- 580 application tests; 63 JavaScript tests; 158 Python tests (14 environment-specific skips).
- Real PostgreSQL two-user isolation/revocation and signed OIDC fixtures passed.
- Browser tests passed streamed replies, approvals/rejection, uploads, partial-output recovery and manual continuation, Stop, reload and mobile layout. Encrypted restore rehearsal passed with wrong-key/tamper rejection. These use disposable identities; do not claim a fresh production MFA browser login.
- Three real controller user/workspace scopes had separate retained homes. Cold creation took 132-157 seconds. Cross-user Stop returned 409; in-flight Stop cancelled execution in 3.25 seconds with no late file. Disposable container deletion reclaimed disk space.
- Resource checks confirmed 1 CPU, 2 GiB RAM, no swap, 512 PIDs, blocked network egress and absent host/Docker paths.
- The candidate's live assistant passed web search/read, Outline draft creation/update/deletion, workspace memory/document save/delete, explicit approval/rejection and reminder pause/delete. Synthetic content was cleaned up; no notification was sent.
- The separate live API-to-executor cold-start probe was interrupted by automatic rollback. Its exact computer was subsequently stopped/deleted. Repeat this probe only after successful promotion.

## Why deployment rolled back

[Deployment run](https://github.com/RithvikRS/Portfolio-website/actions/runs/45247750641) encountered transient OIDC discovery DNS failures while Caddy restarted. Rakazo SSO later reached 1/1, but Swarm retained `UpdateStatus.State=paused`. The strict convergence check correctly refused promotion and restored the previous stack. The controller was then explicitly rolled back to match the previous API contract.

At the user's stop request, the remaining failed deployment validation was cancelled after checking that all service replicas were restored. Before resuming, confirm no remote deployment lock/process remains.

## Pending fix on this branch

- Only the stateless Rakazo SSO update policy uses `failure_action: continue` so a transient dependency failure does not leave a permanently paused update. Keep stop-first, one replica, restart policy, final service convergence, internal `/ready`, protected HTTP checks and whole-release rollback. No database/application policy is relaxed.
- `scripts/migrate-rakazo-homes.py --reapply` supports a deliberate retry after rollback using retained bounded homes and the original recovery record. It checks ownership, mount identity, symlinks, prior configuration and unchanged legacy-home contents. It preserves the original rollback snapshots and restores old state if the retry fails.
- Local focused checks passed: 4 SSO tests, 36 deployment tests (one skip), 10 migration tests, and Python syntax checks. The real `--reapply` path has not yet been exercised on Ampere.

## Resume in this order

1. Read this file and the migration/rollback sections of `deploy/RAKAZO-WORKSPACE-VERIFY.md`. Check Git status, deployment-job completion and all production replicas.
2. Review the pending rollout fix and migration reapply tests. Create one corrective PR, retaining the already published candidate image.
3. Before merging/deploying, briefly stop Rakazo API admission, confirm no active native run/computer, stage the reviewed migration and controller files privately, run `--reapply`, then install the scoped controller. Do not restart production Docker. Keep API admission closed until the matching new application deploys.
4. Merge and follow the normal deployment pipeline. If it rolls back, restore the old controller contract before admitting old API traffic. Do not ignore paused updates or bypass final health checks.
5. After successful promotion, repeat the live API-to-executor cold-start/Stop check, verify current member grants and unauthenticated route denial, all replicas, free-only policy/no local token quotas, and the retained rollback image.
6. Refresh the full private cluster backup, including new image/configuration, Rakazo data and migration recovery record. Confirm checksums and all services online afterward. Keep all secrets and backup archives out of Git.
7. Google is last: each user connects their own account(s) with OAuth consent. Do not create a shared owner Google connection for members.

## Private evidence and backups

The full pre-change backup completed at `C:/Users/Rithvik/Documents/Portfolio-private-backups/cluster-2026-11-23_232454_+0530`, linked manager snapshot `2026-11-23_233703_+0530_084caef1`. Image/config/archive checksums passed and all 26 services recovered. No post-release refresh completed because the candidate rolled back.

Private operator helpers and result logs are under `C:/Users/Rithvik/Documents/Codex`: `family-build.log`, `family-verify.log`, `family-live-result.log`, `family-proxy-live.py`, and `rakazo-browser-tools/results/family-release-final`. Never commit private helper credentials, browser state or recovery material. Use `Documents/Portfolio-private-backups/Backup-Cluster.ps1` for the next full refresh.
