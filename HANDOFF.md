# Handoff: Rakazo workspace integration

Updated: 15 November 2026. Branch: `codex/rakazo-workspace-integration`.

The owner authorized this release, including publication, a conventional commit, one PR, merge and deployment. Use [PR #52](https://github.com/RithvikRS/Portfolio-website/pull/52) for the corrective rollout and production-login evidence. PR #51 rolled back after the web scratch mount inherited restrictive upstream permissions. The previous no-merge/no-deploy checkpoint boundary no longer applies.

## Release configuration

Both API and web use `ghcr.io/rithvikrs/portfolio-website@sha256:bb0de4ba6ce886bbd7993cf5521ce44a82c5fb64e6d76dd4c10f6efe17ca3f3f`. [Publication](https://github.com/RithvikRS/Portfolio-website/actions/runs/43747163988) passed checksum, image identity, ARM64, provenance and runtime checks. Temporary transfer assets and Actions credentials were removed.

Use the owner-only workspace at `/rakazo` and its separate offline desktop at `/computer/` on the Rakazo hostname. Keep Authelia MFA, the exact-owner API allowlist and disabled model connections. The dedicated production database bootstrap passed with the existing private recovery set and a restricted runtime role. Follow [the service guide](deploy/RAKAZO.md) and [verification runbook](deploy/RAKAZO-WORKSPACE-VERIFY.md).

## Isolated verification evidence before promotion

- Build candidate `portfolio-rakazo:workspace-03536e98fda038d5` remains cached on Ampere. Its local image ID is `sha256:6424db1aa85a72863979517a9ba284739bad544d10e92abae8ae552699dda029`. All 56 API/UI policy tests, API/web compilation, incremental image assembly and image provenance/runtime checks passed.
- The real PostgreSQL/OIDC fixture passed owner admission, outsider/unverified-owner denial, workspace/profile/note persistence, logout, blocked execution and zero provider/job activity.
- The compiled API and web passed read-only startup through the actual file-backed secret entrypoint. Missing files fail closed even with an environment fallback. Conflicting workspace/provider/password service overrides are reset by the entrypoint; authenticated execution endpoints remain forbidden.
- Chromium browser checks passed verified-owner sign-in, denied identities, workspace/profile/note creation and editing, desktop/mobile layout, navigation links and logout. After restoring, a fresh login recovered the exact instructions, title and note text; rename/delete checks also passed. No browser page errors or external requests occurred.
- The coordinated database, data and secret snapshot was encrypted with AES-256-GCM. Wrong-key and tampered-archive checks failed as expected. The original test database and volumes were removed before restoring new ones; the browser then confirmed recovery.
- Every labelled test container, network and volume was removed. Existing Ampere task IDs and health states stayed unchanged. No production Docker restart, firewall change, production-data mount, model connection, registry publication, Git push, merge or deployment occurred.

The browser identity provider was a disposable HTTPS/OIDC fixture, **not live Authelia MFA**. The dashboard/desktop endpoints in those tests were test destinations. Record production routing and actual desktop integration separately in the release PR.

## Storage and recovery limits

Rakazo v0.8.0's `CONTENT_ENCRYPTION=on` covers selected message/event/memory fields. It does not encrypt scratchpad note text or profile instructions. Treat database access and backups as sensitive; do not describe these notes as end-to-end encrypted or individually encrypted at rest. The rehearsal encrypted the complete backup archive.

The pilot desktop remains disposable. Its home is not covered by the application database rehearsal. Keep provider credentials, agent execution, schedules and native workspace computers disabled.

The completed synthetic rehearsal copy is on the PC under:

`Documents/Portfolio-private-backups/rakazo-workspace/rehearsal-2026-11-15-2ca629b2ea6a/`

Keep `archive.aesgcm` and its separate `recovery/backup.key` private. The archive checksum matches Ampere. This is test data, not a new production or whole-cluster backup. Use the private backup folder’s `latest-cluster.json` and `SUCCESS.json` records to identify the latest complete production backup. The 15 November pre-release refresh runs before the PR merge; it does not replace a backup of later workspace changes.

The production recovery set under the manager's `.secrets/rakazo` and `.auth/secrets` remains unchanged. Reuse it; do not regenerate or commit credentials.

## Reproduce the checks

Read [the verification runbook](deploy/RAKAZO-WORKSPACE-VERIFY.md). Use `verify-rakazo-workspace.py` for the disposable database fixture and `verify-rakazo-release.py` plus `verify-rakazo-browser.mjs` for compiled entrypoints, browser checks and encrypted restoration. Run destructive rehearsal actions only against resources carrying that session's exact test label.

Public source stage: `/home/opc/.config/rakazo-workspace-source-20261115`. Earlier stages contain older helpers; refresh from the local branch before reuse. Private generated test files and diagnostics live in separate `/home/opc/.config/rakazo-release-*` directories, outside production and Git.

The PC browser tooling and screenshots are under `Documents/Codex/rakazo-browser-tools/`. Browser checks use a dedicated headless Chromium and an SSH tunnel bound to `127.0.0.1`, forwarded directly to the test edge's current container IP. No test service publishes a host port. The tunnel must be closed after use. Reconnect after network resets; do not change production routing to work around a PC connection failure.

Local Python discovery ran 136 tests: 122 passed and 14 skipped. The crypto-dependent release test also passed on Ampere with its existing cryptography package (all four release safety tests passed there). Earlier Node regression tests passed all 27 cases. JavaScript syntax and portfolio page/link checks pass. The actual browser and restore runs are separate evidence from mocked helper tests.

## Complete or inspect the release

1. Check PR #51 and its main-branch deployment run before repeating a rollout. Publication and database bootstrap are complete; do not regenerate keys or rerun bootstrap against an active database.
2. Preserve current/previous images, manager roles and the isolated rootless engine. Move only the bridge assets and `BASE_PATH` to `/computer/` for this release; restore its previous unit/source if rolling back to the old root-path pilot.
3. Verify live owner MFA, workspace controls, dashboard/logout navigation and the actual desktop route. Disposable identity-provider tests do not replace these checks.
4. Run the private backup toolkit after production state changes. Confirm database/data/keys and immutable images appear in its inventory before relying on the new service for durable notes.

## Open on another laptop

Clone the checkpoint branch, then transfer any later uncommitted work separately or publish it only when asked. Install Git, Python 3, Node.js >=22.9 and pnpm; use `pnpm install --frozen-lockfile`. Git does not transfer this chat, private backups or credentials.

Transfer `Desktop/Oracle Cloud` and `Documents/Portfolio-private-backups` securely and separately from Git. Update Windows paths and restrict SSH private-key permissions. Keep the iPhone authenticator for live MFA checks. Optional upstream source: Rakazo v0.8.0 at `747ece9641dcc60c95467ffae8ab2311fb1f3f81`, outside this repository.

## Pending work across the project

Use this as a backlog, not a statement that every listed service needs redeployment. The roadmap mixes implemented features with acceptance checks; verify evidence before marking a phase complete.

| Area | Next work | Boundary / dependency |
| --- | --- | --- |
| Rakazo workspace | Immutable ARM image published; API/browser/restore tests and database bootstrap passed; inspect PR #51 for live rollout evidence | Keep owner-only admission and execution disabled |
| Shared model gateway | Finish private provider setup; select free-only models and ordered fallbacks; test streaming/tools, quotas, revocation and application isolation | Owner supplies providers/routing choices; keep all consumers disconnected |
| Family identity | Rehearse two-user onboarding, grants, offboarding and downstream session revocation; record results | Use disposable identities; live account changes require authorization under the current boundary |
| Outline notes | Rehearse private/shared documents, search, attachments, revocation, exports and restore | Existing owner login is recorded; do not equate it with two-user isolation or restore evidence |
| Vaultwarden | Rehearse two-user isolation, encrypted export/import and recovery with disposable items | Do not request or export real vault secrets to Git |
| Monitoring | Confirm outage/recovery alert behavior and an external monitor with independent delivery | ntfy and ingress share a failure domain; selecting an external provider is a separate decision |
| Recovery | Refresh the private backup after any future live state change; restore new Rakazo state and matching keys in isolation | Toolkit stays outside Git; use the private latest-successful pointers |
| Deployment foundations | Confirm digest-based deployment and previous-release recovery evidence for the next authorized release | Use the authorized release pipeline; retain rollback evidence |
| Trading app | Audit `docs/oracle-authelia-decisions.md` in the separate repo, then implement a synthetic-data Oracle/OIDC vertical slice | Last phase; do not mix its code into this repository |
| Optional / deferred | Gemini Web paid-model exception, developer secrets platform, data failover, multi-user agent execution | Not enabled or approved by resuming local work |

Keep the service roadmap and this checklist aligned as each gate acquires actual test evidence. Do not mark a phase complete solely because its configuration exists.
