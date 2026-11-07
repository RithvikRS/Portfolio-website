# Rakazo restricted pilot

## Current status

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

## Resume safely

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
