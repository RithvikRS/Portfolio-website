# Rakazo workspace integration checkpoint

Stop date: 10 November 2026. Keep this work local until the remaining gates pass. Do not merge or deploy the placeholder application image in the service catalog.

## Current production

Keep using the existing owner-only offline desktop at `/rakazo`. No full-app API, web service or Rakazo PostgreSQL database has been deployed. Model connections and agent jobs remain disabled. The live bridge still uses its original root path; `/computer/` is a prepared change, not a live route yet.

The new private OIDC/database/encryption recovery set exists on the manager under `.secrets/rakazo`, with its OIDC hash under `.auth/secrets`. Its archive is on the PC under `Documents/Portfolio-private-backups/rakazo-workspace/`. Reuse that set; do not regenerate keys or put it in Git. The running Authelia configuration has not changed.

Ampere has the pinned upstream app and PostgreSQL images cached. No temporary workspace build container remains. Existing images and rollback versions are retained.

## Prepared changes

- Apply `workspace-only.patch` and `workspace-ui.patch` to the pinned Rakazo v0.8.0 app. The restricted screen uses real workspace, bot-profile and scratchpad RPCs, with native OIDC login and logout back to the dashboard.
- Enforce the exact verified owner in the API. Deny model connections, chat execution, schedules, integrations and computer-provider changes. Disable both the runtime and job publisher independently of the UI.
- Run API, web and a separate PostgreSQL 18 database on Ampere. Use internal-only networks, file-backed secrets, explicit resource limits, and separate migration/runtime database roles.
- Resolve the public OIDC issuer through a Caddy alias on the private app network. Keep Authelia MFA and the exact-owner gate in front of the whole hostname.
- Keep the existing disposable desktop separately accessible at `/computer/`. Do not connect workspace profiles to the supervisor or treat desktop files as durable workspace storage.
- Keep the private backup toolkit outside Git. It now measures an actual Docker export without writing it to disk when shared layers make the conservative staging estimate too large; image coverage remains unchanged.

## Checks completed

The ARM build passed 52 API policy tests, four workspace UI tests, and production API/web compilation. Candidate Authelia configuration passed with the production template filter, and the candidate Caddy configuration passed isolated validation. Local deployment, bridge and build-helper tests passed. The private backup toolkit passes 42 tests.

The first final-image assembly used BuildKit, which unpacked the large base again and exhausted root-disk space. Canceling that assembly and removing its unused build cache restored approximately 4.5 GiB free. Existing Ampere services remained healthy. No derived image was promoted or published.

The updated build helper commits only the stopped, bounded compiler's filesystem delta instead of using BuildKit. It records public build provenance, resets runtime settings and requires disk headroom before committing. Its helper tests pass; this revised assembly path still needs a live build check.

## Resume gates

1. Check all nodes, free space and the current Git diff. Refresh staged public source files before running them; the server's staged build helper still predates the final incremental-commit change.
2. Run `python3 scripts/build-rakazo-app.py --sudo --check-only` on Ampere, then run the build. Keep its memory, CPU, network and disk guards. Do not remove rollback images to make room.
3. Run the disposable PostgreSQL/OIDC integration fixture in `deploy/rakazo/verify-workspace.postgres.test.ts`. Use only a fresh database named `rakazo_workspace_verify_*`, separate runtime/owner roles and the explicit disposable flag. Check owner admission, rejection of other identities, workspace/profile/note persistence and zero execution/provider activity. Do not use production credentials or data for the fixture.
4. Check the actual web service with the proposed read-only filesystem, tmpfs paths and resource limits. Inspect the restricted UI and confirm logout/dashboard/desktop navigation.
5. Publish the validated derived ARM image by immutable digest and replace both placeholder catalog references. Bootstrap the dedicated database with `setup-rakazo-app.py`; send private input over stdin and keep migration diagnostics private. Validate runtime row-level-security restrictions.
6. Check current private backup coverage and save the new application state, encryption material and image recovery information. Rehearse restoration into a separate disposable database before relying on stored notes.
7. Finish the operating documentation, review the combined diff and run the required repository tests. Batch one PR through the existing workflow only after the image and staging checks pass.
8. After promotion, update only the pilot bridge to its prefixed assets and `BASE_PATH=/computer`; avoid restarting the isolated engine or production Docker. Check all release services, owner-only access, network/model denial and the desktop connection. Ask the owner to complete real Authelia browser sign-in when available; the staged OIDC fixture does not replace that final browser check.

Keep provider credentials, model connections, agent runs and native per-workspace computers disabled throughout these steps.
