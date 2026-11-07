# Rakazo restricted pilot

## Current status

Use gVisor `runsc release-20261102.0` with the `systrap` platform for the next pilot stage. The offline ARM64 runtime and Rakazo v0.8.0 computer image passed the checks below on Ampere. No KVM, Docker daemon restart, firewall reload or host SELinux change was needed.

**Runtime compatibility passed; Rakazo application integration remains pending.** No Rakazo browser endpoint or runtime-control API is exposed. Keep the future browser app owner-only behind Authelia MFA. Do not connect models, enable scheduled runs or admit additional users yet.

### Passed on Ampere

- Start Rakazo's actual desktop and load its local noVNC page.
- Launch Chromium and render a local HTML document without network access.
- Run the guest as UID 1000 with no capabilities and `no_new_privileges`.
- Run the host Sentry as the dedicated unprivileged `rakazo-pilot` account, with host seccomp filters and `no_new_privileges` active.
- Read actual host cgroup ceilings: 2 GiB RAM, no swap, one CPU and 512 host tasks. Limit each probe to 100 seconds.
- Deny writes to the guest root filesystem and deny guest mounts. Hide production paths and sockets.
- Deny cloud metadata, cluster public addresses, private addresses, public internet and tested IPv6 destinations; confirm that sandbox-local HTTP still works.
- Stop all pilot processes after the test. Keep all three Swarm nodes Ready and all 18 existing services at their expected replicas.

These checks establish a bounded offline compatibility baseline, not a proof against every escape. gVisor provides a userspace kernel boundary; its host processes do not gain an Incus-style SELinux container domain. Keep host SELinux Enforcing. The `--no-sandbox` Chromium test relies on the outer gVisor sandbox; do not reuse that browser command outside it.

### Repeat the offline gate

Run `sudo python3 scripts/verify-rakazo-gvisor.py` on Ampere after copying the script there privately. It starts only the fixed offline probe and checks both guest behavior and live host confinement. It creates a private report under `/var/lib/rakazo-pilot/verify-*/result.json`. The successful report is also saved on the PC at `Documents/Portfolio-private-backups/rakazo-pilot/gvisor-verification.json`.

For a fresh staging area, use `scripts/stage-rakazo-gvisor.py`. It checks the Ampere node ID and free space, downloads the checksum-pinned official runtime, and exports the pinned computer image without starting it in Docker. It refuses an existing rootfs; preserve the current installation and rerun verification instead. The individual staging operations ran successfully on Ampere; the combined fresh-install helper has not been rerun against an empty host.

Runtime: `/opt/rakazo-runtime/release-20261102.0/`. Offline image rootfs: `/var/lib/rakazo-pilot/computer/rootfs`. These are reproducible test artifacts, not application state. Keep them out of Git and normal state backups. The staging-only Docker image and disposable Alpine probe were removed; the retained rootfs uses about 1.6 GiB of file data. No permanent pilot service starts at boot.

### Remaining integration gate

Rakazo v0.8.0 has no direct `runsc` provider. Do not point its Incus adapter at gVisor, mount the production Docker socket into its supervisor, or deploy Kubernetes alongside Swarm merely to select a runtime class. A separate rootless Docker engine passed create/exec/stop/remove checks using gVisor, guest UID 1000 and metadata denial. Its Unix socket stayed private; it skipped firewalld management and used a separate data directory. The engine is stopped, with no boot service. The dedicated account has the non-overlapping subordinate UID/GID range `2000000:65536`. Its test configuration remains under `/var/lib/rakazo-pilot/engine/`.

The engine probe used an enclosing 3 GiB, one-CPU, 768-host-task unit with a five-minute lifetime. Docker reported that per-container cgroups were unavailable in this configuration; do not claim separate per-computer limits. The successful engine report is `Documents/Portfolio-private-backups/rakazo-pilot/rootless-engine-verification.json` on the PC.

The next step is to validate Rakazo's supervisor against that dedicated engine, add enforced admission limits and verify the screen/control path while preserving denied egress. Use gVisor for every computer; a default runtime alone does not prevent a Docker API caller from selecting another runtime. Keep its API, filesystem access and networking separate from the production engine. Verify create/exec/stop, screen access, workspace recovery, resource limits and denied network destinations through that integration before exposing the app. If that integration cannot preserve the tested boundary, leave execution disabled.

Authelia protects browser access; it does not constrain commands executed by an agent. Keep provider keys and model-connection writes disabled independently of computer-provider selection.

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
