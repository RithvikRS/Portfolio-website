# Handoff: Rakazo workspace integration

Updated: 15 November 2026. Branch: `codex/rakazo-workspace-integration`.

The owner authorized image publication, conventional commits, one PR, merge and production deployment on 15 November. The isolated verification gates passed. Publish the tested image, replace the catalog placeholders with its registry manifest digest, reuse the existing private recovery set, and verify live login/routing. Keep exact-owner Authelia MFA, workspace-only mode and disabled model connections throughout the release. The earlier no-merge/no-deploy checkpoint restriction is superseded by this authorization.

## Current result

- Build candidate `portfolio-rakazo:workspace-03536e98fda038d5` remains cached on Ampere. Its local image ID is `sha256:6424db1aa85a72863979517a9ba284739bad544d10e92abae8ae552699dda029`. All 56 API/UI policy tests, API/web compilation, incremental image assembly and image provenance/runtime checks passed.
- The real PostgreSQL/OIDC fixture passed owner admission, outsider/unverified-owner denial, workspace/profile/note persistence, logout, blocked execution and zero provider/job activity.
- The compiled API and web passed read-only startup through the actual file-backed secret entrypoint. Missing files fail closed even with an environment fallback. Conflicting workspace/provider/password service overrides are reset by the entrypoint; authenticated execution endpoints remain forbidden.
- Chromium browser checks passed verified-owner sign-in, denied identities, workspace/profile/note creation and editing, desktop/mobile layout, navigation links and logout. After restoring, a fresh login recovered the exact instructions, title and note text; rename/delete checks also passed. No browser page errors or external requests occurred.
- The coordinated database, data and secret snapshot was encrypted with AES-256-GCM. Wrong-key and tampered-archive checks failed as expected. The original test database and volumes were removed before restoring new ones; the browser then confirmed recovery.
- Every labelled test container, network and volume was removed. Existing Ampere task IDs and health states stayed unchanged. No production Docker restart, firewall change, production-data mount, model connection, registry publication, Git push, merge or deployment occurred.

The browser identity provider was a disposable HTTPS/OIDC fixture, **not live Authelia MFA**. The dashboard/desktop endpoints were test destinations; production routing and the actual desktop integration still need final release checks.

## Storage and recovery limits

Rakazo v0.8.0's `CONTENT_ENCRYPTION=on` covers selected message/event/memory fields. It does not encrypt scratchpad note text or profile instructions. Treat database access and backups as sensitive; do not describe these notes as end-to-end encrypted or individually encrypted at rest. The rehearsal encrypted the complete backup archive.

The pilot desktop remains disposable. Its home is not covered by the application database rehearsal. Keep provider credentials, agent execution, schedules and native workspace computers disabled.

The completed synthetic rehearsal copy is on the PC under:

`Documents/Portfolio-private-backups/rakazo-workspace/rehearsal-2026-11-15-2ca629b2ea6a/`

Keep `archive.aesgcm` and its separate `recovery/backup.key` private. The archive checksum matches Ampere. This is test data, not a new production or whole-cluster backup. The earlier complete cluster snapshot remains the 10 November set until a separate live refresh runs.

The production recovery set under the manager's `.secrets/rakazo` and `.auth/secrets` remains unchanged. Reuse it; do not regenerate or commit credentials.

## Reproduce the checks

Read [the verification runbook](deploy/RAKAZO-WORKSPACE-VERIFY.md). Use `verify-rakazo-workspace.py` for the disposable database fixture and `verify-rakazo-release.py` plus `verify-rakazo-browser.mjs` for compiled entrypoints, browser checks and encrypted restoration. Run destructive rehearsal actions only against resources carrying that session's exact test label.

Public source stage: `/home/opc/.config/rakazo-workspace-source-20261115`. Earlier stages contain older helpers; refresh from the local branch before reuse. Private generated test files and diagnostics live in separate `/home/opc/.config/rakazo-release-*` directories, outside production and Git.

The PC browser tooling and screenshots are under `Documents/Codex/rakazo-browser-tools/`. Browser checks use a dedicated headless Chromium and an SSH tunnel bound to `127.0.0.1`, forwarded directly to the test edge's current container IP. No test service publishes a host port. The tunnel must be closed after use. Reconnect after network resets; do not change production routing to work around a PC connection failure.

Local Python discovery ran 136 tests: 122 passed and 14 skipped. The crypto-dependent release test also passed on Ampere with its existing cryptography package (all four release safety tests passed there). Earlier Node regression tests passed all 27 cases. JavaScript syntax and portfolio page/link checks pass. The actual browser and restore runs are separate evidence from mocked helper tests.

## Next release steps

1. Review the local diff and secrets scan. Keep all test keys, screenshots, private backups and generated state outside Git. Batch this authorized release into one PR.
2. Publish the tested ARM candidate to an approved registry and verify its immutable registry digest and replace both pending catalog image references. The local `sha256:6424...` value is an image configuration ID, not the digest to paste into a registry reference.
3. Recheck live service/disk health and private backup inventory before any production change. Preserve current/previous images, manager roles and the separate rootless desktop engine.
4. For this authorized deployment, use the existing recovery set to bootstrap the dedicated production database, apply the candidate Caddy/Authelia configuration, and move only the pilot bridge assets to `/computer/`. Do not enable inference or agents.
5. Validate actual Authelia MFA and exact-owner admission, workspace browser controls, current-account checks, real dashboard/logout navigation and the existing desktop screen/reconnect path. The disposable IdP/browser tests do not replace this step.
6. Refresh the coordinated private cluster backup after production state changes. Confirm new database/data/keys and immutable images appear in its inventory before relying on the new service.

## Open on another laptop

Clone the checkpoint branch, then transfer any later uncommitted work separately or publish it only when asked. Install Git, Python 3, Node.js >=22.9 and pnpm; use `pnpm install --frozen-lockfile`. Git does not transfer this chat, private backups or credentials.

Transfer `Desktop/Oracle Cloud` and `Documents/Portfolio-private-backups` securely and separately from Git. Update Windows paths and restrict SSH private-key permissions. Keep the iPhone authenticator for live MFA checks. Optional upstream source: Rakazo v0.8.0 at `747ece9641dcc60c95467ffae8ab2311fb1f3f81`, outside this repository.

## Pending work across the project

Use this as a backlog, not a statement that every listed service needs redeployment. The roadmap mixes implemented features with acceptance checks; verify evidence before marking a phase complete.

| Area | Next work | Boundary / dependency |
| --- | --- | --- |
| Rakazo workspace | ARM image, API entrypoint, browser and encrypted restore checks passed; prepare immutable publication and real Authelia/pilot-route validation before an authorized release | Highest priority; full app remains undeployed, owner-only and execution-disabled |
| Shared model gateway | Finish private provider setup; select free-only models and ordered fallbacks; test streaming/tools, quotas, revocation and application isolation | Owner supplies providers/routing choices; keep all consumers disconnected |
| Family identity | Rehearse two-user onboarding, grants, offboarding and downstream session revocation; record results | Use disposable identities; live account changes require authorization under the current boundary |
| Outline notes | Rehearse private/shared documents, search, attachments, revocation, exports and restore | Existing owner login is recorded; do not equate it with two-user isolation or restore evidence |
| Vaultwarden | Rehearse two-user isolation, encrypted export/import and recovery with disposable items | Do not request or export real vault secrets to Git |
| Monitoring | Confirm outage/recovery alert behavior and an external monitor with independent delivery | ntfy and ingress share a failure domain; selecting an external provider is a separate decision |
| Recovery | Refresh the private backup after any future live state change; restore new Rakazo state and matching keys in isolation | Toolkit stays outside Git; latest packaged complete snapshot is from 10 November |
| Deployment foundations | Confirm digest-based deployment and previous-release recovery evidence for the next authorized release | Use the authorized release pipeline; retain rollback evidence |
| Trading app | Audit `docs/oracle-authelia-decisions.md` in the separate repo, then implement a synthetic-data Oracle/OIDC vertical slice | Last phase; do not mix its code into this repository |
| Optional / deferred | Gemini Web paid-model exception, developer secrets platform, data failover, multi-user agent execution | Not enabled or approved by resuming local work |

Keep the service roadmap and this checklist aligned as each gate acquires actual test evidence. Do not mark a phase complete solely because its configuration exists.
