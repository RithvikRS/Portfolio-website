# Rakazo owner workspace and offline desktop

Open **Rakazo** from your admin dashboard, or use `/rakazo` on the portfolio domain. Sign in through Authelia with your owner account and authenticator, then use Rakazo's Authelia sign-in button if shown. Other users, including other administrators, cannot access this service.

Create workspaces, profiles and scratchpad notes in the workspace app. General workspace chat, provider configuration, schedules and integrations stay disabled. Use the separate note assistant for summaries that you review before saving. The app does not connect profiles to the offline computer. Use **Your dashboard** to return without signing out; **Log out** ends the Rakazo session and returns to your dashboard.

API, web and PostgreSQL run on the approved Ampere worker with private internal networks, read-only container roots, explicit resource limits and file-backed secrets. The runtime database account cannot bypass row-level security. Keep database/data directories and their matching private recovery keys in your backups. Scratchpad notes and profile instructions are database plaintext, so protect database access and encrypt complete backup archives.

The immutable image lives in `deploy/swarm-services.json`. Follow [the verification and publication runbook](RAKAZO-WORKSPACE-VERIFY.md) for updates, and [PR #51](https://github.com/RithvikRS/Portfolio-website/pull/51) for the initial rollout's execution results. The [checkpoint](RAKAZO-WORKSPACE-CHECKPOINT.md) records the earlier development gates.

## Owner-only offline desktop

Use the pinned Rakazo v0.8.0 supervisor with a separate rootless Docker engine and gVisor on Ampere. The controller can start/resume/stop the real desktop, execute its internal commands and establish a noVNC framebuffer connection. Keep model connections and agent jobs disabled.

Choose **Offline desktop pilot** inside Rakazo to open `/computer/`. The dedicated engine, controller and bridge run on Ampere under their own bounded user services. The browser edge runs in Swarm. Keep the existing production Docker engine and its services separate from the pilot.

The desktop-control page wraps Rakazo's supervisor and stays separate from the workspace API/database. The page exposes only the fixed owner's start, stop, view and control actions. Model/provider endpoints and agent-run endpoints return 404. No provider keys are installed.

## Isolation and limits

| Boundary | Pilot setting |
| --- | --- |
| Host identity | `rakazo-pilot`, UID 986/GID 984; subordinate range `2000000:65536` |
| Guest identity | UID/GID 1000, no capabilities, no privilege escalation |
| Runtime | `runsc release-20261102.0`, systrap; no KVM or privileged container |
| Admission | One running computer across the entire dedicated engine |
| Computer resources | 2 GiB RAM, no swap, one CPU, 512 host tasks |
| Whole pilot user slice | 4 GiB RAM, no swap, 1.5 CPUs, 1,536 host tasks |
| Storage | 8 GiB loop filesystem for images, writable layers and the disposable desktop home |
| Guest mounts | Read-only root, bounded temporary memory, its own home and Docker-generated hosts/DNS files |
| Networking | RootlessKit `net=none`, detached-network bypass disabled; no external route |
| Controller | Loopback inside the isolated namespace, bearer authentication |
| Browser bridge | Mode-0600 Unix socket; no host TCP listener or Docker socket in the edge service |

The pinned runtime cannot use the rootless user manager's systemd connection. `runtime_launcher.py` validates the OCI limits and home mounts, joins an enforced cgroup **before** starting gVisor, and refuses unbounded computers. It handles the cgroup itself instead of granting access to host ancestors. Whole-cgroup OOM termination prevents a partially killed desktop from lingering.

Keep the controller trusted and its Docker socket private. A default Docker runtime alone cannot constrain arbitrary Docker API callers. The browser bridge exposes no Docker API or arbitrary command endpoint. Do not mount either Docker socket into a computer or the browser edge.

The upstream supervisor uses `SANDBOX_COMPUTER_EGRESS=open` because its firewall helper does not support this rootless topology. Actual egress remains blocked by the enclosing network namespace. Do not copy that setting to a normal networked engine. Keep host SELinux Enforcing and leave production Docker/firewalld configuration unchanged.

## Checks completed on Ampere

- Resume the desktop and execute an authenticated supervisor command as guest UID 1000.
- Reject unauthenticated supervisor creation requests.
- Establish both a WebSocket upgrade and an actual RFB framebuffer handshake through the private bridge.
- Reject a second computer and reject a computer with missing resource limits.
- Read the live cgroup limits rather than relying on Docker's reported configuration.
- Exceed the memory ceiling: terminate the whole computer with exit 137, record `oom_group_kill=1`, and resume it through the controller. CPU throttling counters also increase.
- Deny cloud metadata, all three nodes' private/public addresses, and a public internet destination.
- Keep production paths and sockets absent from the guest; keep the guest root read-only.
- Serve the bridge to an unprivileged, networkless edge-container probe through the Unix socket.
- Pass 114 Linux Python tests, the owner/CSRF edge tests, and 10 private backup-tool tests.

Run `sudo python3 scripts/verify-rakazo-controller.py` on Ampere after starting the pilot desktop. It checks real framebuffer traffic, model-route denial, live ceilings, denied egress and bounded home storage. It saves non-secret evidence in `/var/lib/rakazo-pilot/controller-verification.json`. Admission evidence comes from the separate negative startup probes; the verifier checks that saved result rather than creating extra computers itself.

The earlier standalone runtime probe remains available as `scripts/verify-rakazo-gvisor.py`. Do not confuse its results with browser sign-in verification.

## Browser access

The entry point is `/rakazo` from the admin dashboard, redirecting to `https://rakazo.144.24.135.201.sslip.io/`. Keep the desktop on its own browser origin, separate from the public portfolio and password vault.

Caddy clears supplied identity headers and asks Authelia for MFA authorization. The dedicated Authelia rule admits only `rithvik`; the edge additionally requires that exact username and the `admins` group. State-changing requests and WebSocket upgrades require the expected browser Origin. The edge lives on a private, non-attachable, internal Swarm overlay with Caddy, has no published ports, and mounts only the bridge socket directory read-only.

This pilot uses Authelia's login directly on the dedicated hostname, with its own cookie. Expect a separate MFA sign-in there; it has no additional native application password. Screen connections expire after four minutes and the pilot page reconnects through authorization. After each release, check browser login, reconnect and non-owner denial before enabling further capabilities.

## Install or update

1. Review the changes and the private recovery checkpoint on the PC under `Documents/Portfolio-private-backups/rakazo-pilot/`.
2. Copy the current `deploy/rakazo/` files and `scripts/install-rakazo-controller.py` to the staged source tree on Ampere. Run the installer there as root. It checks the node ID, dedicated identity, existing 8 GiB mounted cache and staged prerequisites. It installs/enables only the dedicated pilot user services.
3. Start the fixed desktop through the local Unix bridge, then run `verify-rakazo-controller.py`. Rerun negative admission tests after changing runtime policy. Keep model and worker services absent.
4. Validate the candidate Caddy/Authelia configuration, backup inventory and edge service. Review the separate-origin screen and reconnect behavior. The dedicated user-manager restart test recreates the cgroups and recovers the controller without restarting production Docker. A whole-host reboot remains outside that rehearsal.
5. Batch the change into one PR and merge through the existing deployment pipeline. Confirm all existing services and the new edge converge, anonymous requests redirect to Authelia, non-owners fail, and the owner can view/control/stop the desktop.
6. Keep the full Rakazo application, model connections, scheduled runs and multi-user admission for a later phase.

For maintenance, run the user service commands as `rakazo-pilot` with `XDG_RUNTIME_DIR=/run/user/986` and `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/986/bus`. The units are `rakazo-engine`, `rakazo-controller` and `rakazo-bridge`. Stop the desktop first, then stop bridge/controller/engine. Never restart production Docker to operate this pilot.

## Staged prerequisites and recovery

The upstream source is Rakazo v0.8.0, commit `747ece9641dcc60c95467ffae8ab2311fb1f3f81`, under `/var/lib/rakazo-pilot/controller-src`. Install its supervisor production dependencies from the frozen pnpm lockfile. The staged Node binary comes from the upstream pinned `node:24.22.1-bookworm-slim` image (the same digest appears in the service catalog). The installer expects these prerequisites; it is not a complete fresh-host bootstrap.

Use `scripts/stage-rakazo-gvisor.py` for the earlier checksum-pinned runtime/computer staging step. The computer source is the pinned ARM64 v0.8.0 image described by that helper. The isolated engine imports its verified rootfs as `rakazo/computer:pilot-v0.8.0`; preserve the original image metadata used during staging. Keep the engine on VFS: overlay2 was incompatible with this rootless SELinux configuration. Cold desktop creation therefore takes several minutes.

The private backup refresh kit archives the controller environment, engine configuration, user service definitions and custom runtime helpers. It exempts only the exact read-only bridge socket mount and excludes `/srv/swarm/.rakazo-runtime-cache.img`. That file contains disposable images **and the disposable pilot home**. Do not store important files in this desktop. Before durable use, add coordinated workspace snapshots and a restore rehearsal; existing production application backups retain their coverage.

Keep the private checkpoint archive and verification reports on the PC outside Git. Refresh the full cluster recovery kit with `Backup-Cluster.ps1`; Ampere stages temporary archives on its data filesystem as described in [worker backup staging](BACKUPS.md#worker-backup-staging). Keep tokens and private environment files outside Git. Rebuild disposable images/cache during recovery; do not treat the cache exclusion as durable workspace backup.

## Previous Incus attempt

Keep Rakazo agent execution and model connections disabled. Do not expose the application until the isolation checks below pass.

The Ampere preflight on 8 November 2026 found a confinement blocker with the available Oracle Linux packages:

- Oracle Linux 9.8, ARM64, UEK 6.12; SELinux Enforcing, no AppArmor, no `/dev/kvm`.
- Incus 7.0.0-2.el9 with LXC 4.0.12 and crun 1.27.
- A disposable Alpine OCI container used an isolated UID map, no network interface, no host bind mounts, no nesting, one CPU and 256 MiB RAM.
- Commands launched through `incus exec` ran under `spc_t`; the init wrapper retained `container_runtime_t`. Seccomp was active, but `NoNewPrivs` was zero.
- Enabling `INCUS_SECURITY_SELINUX=true` and testing a raw LXC container label did not change those observed OCI process labels. The installed release rejected `security.selinux.domain` and `security.selinux.label_rootfs` as unknown keys.

Do not treat these results as proof that Incus containers are unrestricted in every respect. UID namespaces and seccomp worked, but this build did not meet the additional mandatory-access-control boundary required for agents beside production secrets.

The probe, image, storage pool, temporary systemd override and added root UID/GID mappings were removed. Incus services and its socket were stopped and disabled; installed packages remain. No managed Incus network, HTTPS API listener, Rakazo service, public route or model connection was created. Docker and firewalld remained active, and the existing Ampere containers remained running.

The private pre-change host archive is under `Documents/Portfolio-private-backups/rakazo-pilot/` on the owner's PC. Keep it outside Git.

## Incus requirements if revisited

1. Select a maintained ARM64 Incus/runtime package combination that can apply and preserve suitable SELinux process and filesystem labels on Oracle Linux. Validate the actual release rather than relying on the rolling documentation. Alternatively, reassess an AppArmor-capable host/runtime separately; do not replace the production OS or disable SELinux as a workaround.
2. Repeat a networkless disposable OCI probe, including its application child processes and `incus exec` processes. Confirm confinement, distinct user mappings, seccomp, resource limits and privilege-escalation restrictions. Confirm forbidden mounts and namespace operations fail.
3. Create a restricted project and project-scoped client certificate. Test that the client cannot access other projects, create privileged/nested instances, attach host paths/devices, modify host networks or change restrictions. Never mount the production Docker or Incus administration socket into Rakazo.
4. Use bounded storage on the application disk with explicit backup treatment. Keep disposable computer images/workspaces out of persistent-state archives; back up the application database, encryption keys and required workspace archives together. Rehearse recovery.
5. Add a dedicated bridge with default-deny traffic. Test denial of host services, other sandboxes, production networks, all three nodes' public/private addresses, cloud metadata, IPv6 link-local and private ranges. Allow only the required authenticated control channel. Confirm Docker/Swarm networking still works without globally reloading or flushing firewall rules.
6. Deploy a pinned ARM64 Rakazo release in a separate deployment boundary. Use owner-only Authelia MFA, native OIDC, an explicit owner allowlist and current-account checks. Test anonymous and non-owner denial before publishing its dashboard link.
7. Keep provider keys, gateway credentials, model-connection writes, chat execution and scheduled agent runs disabled until the owner finishes provider setup and the gateway tests pass. `SANDBOX_PROVIDER=none` alone does not disable model calls: Rakazo's agent loop also runs in its API/worker.
8. Start with one owner and one bounded sandbox. Verify stop/delete cleanup, backup coverage, resource exhaustion and service health before admitting any other users.

## References

- [Incus installation](https://linuxcontainers.org/incus/docs/main/installing/)
- [Incus initial SELinux support](https://discuss.linuxcontainers.org/t/incus-6-19-has-been-released/25405)
- [Incus instance options](https://linuxcontainers.org/incus/docs/main/reference/instance_options/) (rolling documentation; compare with the installed release)
- [Rakazo v0.8.0 sandbox providers](https://github.com/elie222/rakazo/blob/v0.8.0/docs/self-host-sandbox-providers.md)
- [Rakazo v0.8.0 computer runtime](https://github.com/elie222/rakazo/blob/v0.8.0/docs/computer-runtime.md)

- [gVisor ARM64 installation](https://gvisor.dev/docs/user_guide/install/)
- [gVisor systrap platform](https://gvisor.dev/docs/architecture_guide/platforms/)
- [gVisor rootless execution](https://gvisor.dev/docs/user_guide/rootless/)

## Full-app checkpoint and recovery checks

The owner authorized the full-app release on 15 November after the isolated verification gates passed. The isolated ARM build, compiled API/web secret entrypoints, browser workspace controls and encrypted backup/restore rehearsal passed on 15 November 2026. Use [the handoff](../HANDOFF.md) for the candidate image and remaining gates, and [the verification runbook](RAKAZO-WORKSPACE-VERIFY.md) to reproduce the checks. Real Authelia MFA, the production dashboard/desktop routes and a post-deployment cluster backup remain separate gates.

Treat scratchpad notes and profile instructions as database plaintext. The pinned upstream content-encryption setting does not cover those fields. Encrypt complete backups and keep their recovery keys outside Git; do not describe workspace notes as end-to-end encrypted. The existing desktop home remains disposable and is not made durable by the application database restore test.


## Sign in through your dashboard

Open `/rakazo` from your admin dashboard. The outer OIDC gate and Rakazo's native login both use `https://rithvik.ddns.net/auth`, so they reuse your existing central Authelia MFA session. If Rakazo shows its Authelia sign-in button, click it; you should not need to enter your password and authenticator again while that central session remains valid. With no central session, complete MFA once. On first use, Authelia may ask you to approve Rakazo-edge access to your identity, email, groups and offline session renewal. This consent is separate from entering your password and authenticator; it does not enable model access. The root URL opens `/app` instead of the upstream marketing page.

Keep the edge cookie scoped to the Rakazo host. Do not share cookies across `sslip.io` tenants or disable the outer gate. The gate requires the owner email and `admins` claim; Caddy also checks the current directory on every app and desktop request, rejecting a disabled owner, removed admin membership, duplicate email, or another admin. Native workspace login retains its own owner allowlist. Model connections and agent jobs remain disabled.

The two-minute edge refresh renews the secure browser ticket during requests. Store OIDC tokens in the isolated, memory-only `rakazo_sessions` service; restarting it signs the edge session out without deleting workspace data. Both session services run on Ampere with limits and no published ports. The five-minute ID-token lifetime uses the existing `omniroute_edge` Authelia lifespan policy; it does not reuse OmniRoute credentials or session storage.

Before the first deployment, run `python3 scripts/setup-rakazo-sso.py` on the manager as the checkout owner. It creates `.secrets/rakazo-edge/recovery.json`, `.secrets/rakazo-edge/edge.cfg`, and `.auth/secrets/rakazo-edge-client-hash` privately and refuses to overwrite mismatched keys. Include these paths in the normal private server backup. Do not commit them. Roll back through the previous Swarm release if sign-in fails; retain the old Rakazo Authelia host-cookie configuration for rollback compatibility.

Verify a fresh session prompts for MFA once, an existing dashboard session reaches Rakazo without another credential prompt, and logout returns to `/admin/`. Anonymous or forged identity headers must never reach workspace or desktop data. Recheck navigation after more than five minutes to exercise ticket renewal.

## Note assistant with approval

Open **Note assistant** in your admin dashboard, or visit [the note assistant](https://rakazo.144.24.135.201.sslip.io/agent-pilot/). Sign in to the Rakazo workspace first if the assistant asks for a native session. It reuses your owner-only Authelia gate and native Rakazo session; no provider key belongs in the browser.

1. Choose a workspace, profile and source note. The assistant remembers the workspace selected in Rakazo.
2. Choose **Draft summary**. Only the selected note is sent to the free-only `agent-free` pool. Its contents are untrusted data, not instructions to execute.
3. Review the exact title and draft. Choose **Approve and save as a new note**, then confirm. The source stays unchanged. The model has no write tool.
4. Choose **Stop task** during generation or **Discard draft** before approval to prevent saving that result.

The API rechecks your native session and selected workspace before model calls and before approval. It rejects expired approval, a changed/deleted source note, a mismatched draft version and repeated submissions. Once a save is submitted, Stop cannot undo that write. If its outcome is uncertain, check your workspace: the assistant will not retry that save automatically. Drafts expire after 24 hours.

### Durable limits and recovery

The private SQLite ledger at `/srv/swarm/rakazo_agent/notes.sqlite` stores task states, draft versions, approval outcomes and charged calls. It uses synchronous commits and an exclusive database lock; a second controller sharing that file fails closed. Keep one replica, exact Ampere placement and stop-first updates. Separate copies of the file are not a distributed quota system.

- At most one active run, 10 new tasks per UTC day, 4 model requests in a rolling minute and 40 per UTC day. Each dispatch is charged before it is sent; cancellation or failure does not refund it.
- Each run lasts at most 60 seconds and sends at most 3 gateway requests, with 256 output tokens per request and at most 2 selected-note tool calls.
- Accept notes up to 4,000 characters / 8 KiB, requests up to 24 KiB, gateway responses up to 64 KiB and visible output up to 4 KiB.
- The existing gateway additionally restricts the key to the selected combo/connections and applies its 12,000-total-token daily quota. The assistant's persistent counters count requests and tasks, not exact provider tokens. Fallback can attempt two providers per gateway request; token limits apply per attempt.

After a restart, running jobs become interrupted and never resume automatically. Completed drafts survive for review. An approval interrupted during saving becomes uncertain and cannot silently replay. Stop persists the stopped state, aborts requests, prevents further calls and kills an unresponsive worker after one second. An upstream provider may still finish a request it already accepted. Stop remains available through the owner gate even if the native Rakazo session expires.

The separate service has a read-only root, 768 MiB memory and 0.5 CPU limits. Its internal, non-attachable overlays connect to Caddy, OmniRoute and the native Rakazo API. It has no database credentials, production data mounts other than its own ledger, Docker socket, desktop bridge, upstream provider keys or direct internet route. The gateway key remains a file-backed Swarm secret. General workspace execution, schedules, delegation and desktop model access remain disabled.

### Backup and verification

Draft text and note titles are sensitive plaintext in the private ledger, like native scratchpad notes. The normal worker backup must include `/srv/swarm/rakazo_agent` and stop its writer before archiving. Keep manager `.secrets/rakazo-agent/model_key`, the matching OmniRoute data/encryption environment, native Rakazo database/keys and service image with that backup. Never copy a live SQLite file while this service is writing. Stop the assistant before restoring; retain the current state first. On startup, restored active/approving jobs become interrupted/uncertain, not executable work.

Run the Node note tests for approval, source-change rejection, quota persistence, restart recovery and uncertain-save duplicate prevention. `deploy/rakazo/verify-agent.mjs` exercises the actual native runtime in a bounded networkless container with synthetic gateway responses. `scripts/verify-rakazo-notes.mjs` uses the disposable PostgreSQL/OIDC fixture and a loopback SSH tunnel to check the real note API, browser preview, approval after restart, one new note and an unchanged source. Its model response is synthetic; it never uses production data or keys. Keep screenshots and generated fixture state outside Git.

After deployment, verify public anonymous/forged-owner denial, workspace execution denial, private gateway/API connectivity, blocked metadata/internet access and all service health. Use a synthetic note for the final live workflow; never approve saving into an existing personal note merely to test a release.
