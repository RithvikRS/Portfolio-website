# Verify the Rakazo workspace in isolation

Use `scripts/verify-rakazo-workspace.py` to run the PostgreSQL/OIDC fixture without live credentials or application data. This runner does not build or deploy the application. Keep the candidate image out of production until all gates pass.

## Requirements

- Use a disposable **native ARM64 Linux Docker engine**, outside the production Swarm, with at least 4 GiB RAM and two CPUs. A local Unix socket or Docker Desktop named pipe is required. By default the runner rejects remote endpoints, every active Swarm node, Windows containers and emulated/nonmatching image platforms. The explicitly authorized Ampere pilot below permits only the existing compute worker.
- Cache the derived workspace image built from this checkout and the pinned PostgreSQL image below. The runner never pulls an image. Transfer images to this engine separately when authorized; preserve current and rollback images on production hosts.
- Supply an immutable application image ID (`sha256:...`) or registry digest. Tags are rejected. The application must carry the exact build-input fingerprint for the current helper and patches, plus the expected non-root command, platform and disabled-feature defaults.
- Install Python 3 and the Docker CLI. Do not supply an environment file, database URL, SSH key, provider key or production recovery set.

PostgreSQL image:

```text
postgres:18-alpine@sha256:123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395
```

## Run the checks

From the repository root, replace the placeholder with the actual derived image ID:

```text
python scripts/verify-rakazo-workspace.py --image sha256:<actual-image-id> --check-only
python scripts/verify-rakazo-workspace.py --image sha256:<actual-image-id>
```

The preflight inspects the engine and cached images without creating resources. The full run creates a uniquely named internal network, PostgreSQL with RAM-backed temporary storage, a migration container and a fixture container. After the fixture passes, a networkless web container serves its HTML with a read-only root, the proposed writable tmpfs paths and the 512 MiB limit. This startup check does not exercise browser interactions or the Swarm secret-file entrypoint. There are no published ports, host directory/socket mounts, provider keys or production networks. Each container has memory, CPU, process and capability limits. Database passwords are generated for this run only and are not written to repository files or printed. As with other Docker environments, the Docker administrator can inspect container environment variables while the test runs.

The migration uses a separate owner login and provisions the restricted runtime login. The fixture exercises signed OIDC tokens with PKCE, rejects anonymous/outsider/unverified-owner access, checks workspace/profile/note persistence through a second login, denies execution routes and job publishing, and checks for zero durable jobs, provider credentials and outbound fetch calls. The OIDC HTTP boundary is emulated: this does not verify real Authelia claims or browser MFA.

The runner removes only the container IDs and network it created, including on migration, test or copy failure. PostgreSQL data disappears with its tmpfs. Cleanup failures are reported with resource IDs; inspect those exact resources on the disposable engine. Never use a broad prune operation. An interrupted Python process or Docker outage can prevent cleanup; inspect resources prefixed `rakazo-verify-` before retrying. Use a production engine only through the exact-worker opt-in described below and only when authorized.

Failures report the phase without dumping container logs or URLs. Optionally pass `--diagnostics-dir` pointing outside Git; the runner writes owner-only failure logs and redacts the generated database passwords. These logs may contain other disposable authentication material, so keep the entire directory private. Reproduce detailed fixture failures only in the disposable environment; treat any diagnostic output as private because test failures can include generated database URLs. A successful helper unit-test run mocks Docker and does not mean the real integration fixture passed.

## Remaining release gates

The following still need separate evidence:

1. Repeat native ARM image assembly and provenance checks whenever build inputs change; the 15 November candidate passed.
2. Repeat the database fixture after relevant changes; it passed on Ampere on 15 November.
3. Repeat browser tests after UI changes; the isolated compiled-app browser checks passed on 15 November.
4. Repeat compiled API/web file-backed entrypoint checks after startup changes; read-only startup, missing-secret denial and hostile-override checks passed on 15 November.
5. Repeat coordinated encrypted backup/restore after schema/key changes; fresh-database and fresh-volume restoration passed on 15 November.
6. Real Authelia MFA, owner denial checks and dashboard/desktop navigation after an explicitly authorized rollout.

Do not replace these gates with unit tests, enable model connections to get past failures, or deploy the placeholder image from the checkpoint catalog.

## Authorized Ampere pilot

The owner authorized using the existing Ampere worker for isolated build and integration tests on 15 November 2026. This permits temporary testing, not a production deployment, registry publication, PR merge or model activation.

Stage only the public helper and fixture files in a separate directory on Ampere. Keep the relative `scripts/` and `deploy/rakazo/` structure. Use the local Docker Unix socket through `--sudo`; do not copy SSH keys, private recovery archives or production environment files into the stage or containers.

```text
python3 scripts/build-rakazo-app.py --sudo --check-only
python3 scripts/build-rakazo-app.py --sudo
python3 scripts/verify-rakazo-workspace.py --sudo --ampere-pilot --image sha256:<derived-image-id> --check-only
python3 scripts/verify-rakazo-workspace.py --sudo --ampere-pilot --image sha256:<derived-image-id> --diagnostics-dir /home/opc/.config/rakazo-workspace-test-logs
```

`--ampere-pilot` accepts only worker `tzqsl1t88r3l1i8zcqvcmredo`, with an active Swarm state and no manager control. It requires at least 6 GiB available host RAM and 3 GiB free Docker disk before tests. Other nodes and managers remain rejected. The database is capped at 1 GiB/0.5 CPU; migration and fixture containers run sequentially at 2 GiB/1.5 CPUs. The final web smoke check uses 512 MiB/0.5 CPU. The separate compiler runs networkless at 3 GiB/two CPUs.

Check live task identities, health and disk space before, during and after execution. Do not restart Docker, change host firewall rules, attach tests to production overlays, mount production data, or prune images to make a test pass. Keep the rootless desktop engine untouched. Preserve current and previous release images.

The successful run used cached image `portfolio-rakazo:workspace-03536e98fda038d5`, image ID `sha256:6424db1aa85a72863979517a9ba284739bad544d10e92abae8ae552699dda029`. This is a local image ID, **not a published registry digest**. Do not substitute it into the production catalog's pending registry reference.

## Compiled API, browser and encrypted restore rehearsal

Use `scripts/verify-rakazo-release.py` only on the approved Ampere worker. It applies the same image, node and headroom preflight, creates uniquely labelled test resources, and saves generated credentials beneath a private `/home/opc/.config/rakazo-release-*` directory. Its cleanup refuses containers, networks or volumes without the exact session label. It mounts only fresh named volumes and bounded tmpfs; it never mounts production paths or the Docker socket.

Stage the helper, `verify-rakazo-workspace.py`, build helper/patches, `deploy/swarm-services.json`, `deploy/rakazo/entrypoint.mjs` and `deploy/rakazo/verify-edge.mjs` together. Start with the cached candidate image:

```text
python3 scripts/verify-rakazo-release.py start --image sha256:<candidate-image-id>
```

Keep the printed private state-file path. Inspect only that session's edge container to find its current internal IP. No test container publishes a port. From the PC, bind an SSH tunnel to `127.0.0.1:18443`, forwarding to `<test-edge-IP>:18443` through Ampere. Close the tunnel after testing; keep ordinary SSH host verification enabled.

The test edge presents a disposable certificate for `rakazo.verify.test` and an explicit test-identity chooser. The API trusts only that additional test CA through `NODE_EXTRA_CA_CERTS`; it does not disable TLS verification. The browser ignores the disposable certificate error only in its dedicated context and maps that test hostname to the loopback tunnel. The fixture is not Authelia, cannot demonstrate MFA and must never be deployed as a real identity provider.

Install Playwright in a tooling directory outside the repository (the rehearsal used 1.56.1 and its Chromium headless shell). Set `RAKAZO_PLAYWRIGHT_ROOT` to that tooling directory, `PLAYWRIGHT_BROWSERS_PATH` to its browser cache and `RAKAZO_TEST_ARTIFACTS` to a private output directory. Run from the repository:

```text
node scripts/verify-rakazo-browser.mjs seed
```

This phase checks denied identities, real owner OIDC, workspace/profile/note writes, execution denial, desktop/mobile layout and logout. It records synthetic recovery expectations and screenshots outside Git. It aborts requests to other origins; it does not use live provider keys or personal browser sessions.

Then run on Ampere:

```text
python3 scripts/verify-rakazo-release.py restore --state <private-state-file>
```

The helper stops test writers and snapshots PostgreSQL plus the matching secret/data volumes. It encrypts the complete archive with AES-256-GCM, rejects a wrong key and tampered ciphertext, removes the original test database/volumes, and restores newly created ones. Snapshot and extraction use the application UID for its private files. Keep `backup/archive.aesgcm` and `recovery/backup.key` private and separate from Git. The supplied host already has the Python cryptography dependency; do not install or upgrade production packages merely to run this helper.

Reconnect the loopback tunnel to the restored edge's current IP if needed, then run:

```text
node scripts/verify-rakazo-browser.mjs restore
```

A fresh login must recover the exact profile instructions, note title and text. The phase then checks rename/delete controls and logout, deliberately deleting only the synthetic records. It does not refresh the backup after those deletions.

Finally:

```text
python3 scripts/verify-rakazo-release.py stop --state <private-state-file>
```

Confirm no resources with `portfolio.rakazo.release-test` remain, compare production task IDs/health and free disk with the starting state, and close the PC tunnel. Retain the encrypted rehearsal archive and private diagnostics if useful; do not call this a production backup. A failed rehearsal is not a valid restore checkpoint.

## Encryption scope

The pinned upstream `ENCRYPTED_MODELS` set covers selected message, event and memory fields. Scratchpad notes and profile instructions remain database plaintext even with `CONTENT_ENCRYPTION=on`. Keep database files, exports and backups private; the rehearsal encrypts the complete archive. Authelia access control and server-side encryption do not make content end-to-end encrypted against the server operator.

## Publish a verified image

Build and verify the ARM image on the approved worker first. Export that exact cached image to the worker data disk; do not rebuild on the AMD manager. Record the archive SHA-256, containerd OCI manifest ID, configuration ID, input fingerprint and local tag in `deploy/rakazo/publication.json`.

Transfer the secret-free archive through a temporary unpublished release asset. Supply its short-lived HTTPS download URL as the encrypted Actions secret `RAKAZO_IMAGE_DOWNLOAD_URL`, then manually run **Publish tested Rakazo image**. The job has repository read and package write permissions; it cannot connect to production. It checks the archive, image identities, ARM64 platform, provenance and disabled-runtime settings before publishing with its job token.

Read `PUBLISHED_IMAGE` from the successful job and pin that registry digest for both Rakazo services. Docker's classic image store and containerd expose different image IDs; do not substitute either local ID for the published registry result. Remove the temporary Actions secret, draft asset and worker export after successful publication. The recorded transfer asset is historical and cannot be reused once removed; create a fresh transfer for another release.

Bootstrap the new database with `scripts/setup-rakazo-app.py worker --image <registry-reference>` on Ampere, passing the manager's existing private recovery JSON through stdin. Never place it in a command argument or Git. Run this only before the production Rakazo database/API exists. After deployment, use a separately reviewed migration for schema updates.

Move the existing pilot bridge to `BASE_PATH=/computer` and restart only `rakazo-bridge`. Preserve the isolated engine and controller. Restore its previous unit/source if rolling back to the earlier root-path pilot. Complete live owner MFA and desktop screen checks separately from the disposable identity-provider tests.

## Check the actual Swarm scratch mounts

Before promotion, run this on the approved manager with the candidate already cached on Ampere:

```sh
python3 scripts/verify-rakazo-swarm.py --ampere-pilot --image sha256:<cached-image-id>
```

The probe uses the service catalog's exact long-form tmpfs mounts, an isolated internal overlay, UID 1000, a read-only root and a 512 MiB / 0.5 CPU limit. It publishes no ports, mounts no host data, and uses only a synthetic screen secret with an unreachable API target. Repeated health checks write and remove a test file in both scratch directories and fetch the web page. The probe removes its service and overlay afterward.

The installed legacy `docker stack` parser drops long-form tmpfs `mode` and ignores service-level short-form `tmpfs`. With its zero-mode mount option, Docker inherits the image directory permissions. The upstream Vite scratch and asset archive directories are owned by UID 1000 with mode 0750; the resulting root-owned tmpfs blocks the non-root web process. Normalize those image directories to 01777 as UID 1000 before compilation. Keep them in the committed image rather than mounting temporary compiler storage over them. Production still runs without capabilities and with a read-only root.

Standalone `docker run --tmpfs ...mode=1777` checks do not cover this Swarm translation. Keep this additional probe in the release gates.

## Native assistant acceptance

The native image adds `native-assistant.patch` after the two workspace patches. Keep the image workspace-only by default; the production entrypoint permits only the restricted runtime when `NATIVE_ASSISTANT=true`. The input fingerprint normalizes text line endings so Windows staging and Linux checkouts produce the same provenance.

The disposable release runner now includes an internal synthetic model/executor fixture and a generated inference-key file. It uses no live provider. Run `scripts/verify-rakazo-native.mjs` with the same private Playwright/artifact environment and loopback tunnel described above. It clears only the disposable chat, then checks fresh conversation replies, tool results, native Stop, reload, prohibited routes and mobile layout. Never point this runner at production.

Rehearse encrypted restore of the native PostgreSQL history and API quota ledger with the existing release helper. Separately check real shell execution, network denial and command cancellation through the bounded gVisor bridge. Stop the computer afterward. After publication, retain the registry digest and remove the temporary download secret and draft transfer asset. Verify all live services, retired-note redirects, native mode and owner denial after deployment; an authenticated production conversation remains a distinct check.


## Granted-user release checks

The PostgreSQL fixture signs in two synthetic users with a mocked current-grant directory. OIDC, API handlers, encrypted artifacts and database persistence run against the candidate image. It denies cross-user workspace/profile/thread/file access, forged identity headers and access after revocation. The connector import boundary is mocked explicitly; it records the verified user/email scope without accessing real notes or provider keys.

The image build runs signed OIDC admission/revocation tests, native run/Stop/error tests, rendered Composer tests, and upstream partial-reply persistence/continuation tests. These gates do not replace live Authelia routing checks or a private backup.

Before installing the scoped controller bridge, run `scripts/migrate-rakazo-homes.py` as root on Ampere without arguments. After a successful private backup, run it with `--apply` to move all disposable homes into the existing bounded cache. It stops only the isolated engine/controller/bridge, keeps original data and records old mount definitions and bridge code. The installer refuses unbounded home storage. Test two synthetic user/workspace identities serially, their distinct homes and scoped Stop before admitting members.

If controller migration fails, use `--rollback` with the retained migration record. It restores the old code/mount configuration and retains new bounded data for inspection. Do not remove either copy until recovery is checked. Never restart production Docker for this migration.


### Roll back across the first multi-user release

The scoped bridge changes the internal Stop request contract. Keep the controller migration record with the matching private backup. If you restore an application release from before scoped Stop, also run the staged `migrate-rakazo-homes.py --rollback` on Ampere to restore its bridge and home mount. Do not leave the new bridge paired with an old API. Stop active chat work before this maintenance; verify that no isolated computer remains running afterward. The old application/SSO policy admits only the owner, while saved member data remains on disk.

Later rollbacks between releases using the same scoped contract do not need this initial migration rollback. Preserve the matching controller code and configuration whenever you change that contract again.
