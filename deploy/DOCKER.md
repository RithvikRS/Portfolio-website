# Containers and deployment

Production uses Docker Swarm. Start with [the architecture and operations guide](SWARM.md).

| Task | Guide |
| --- | --- |
| Add a service/container | [Service catalog walkthrough](SWARM.md#add-a-stateless-service) |
| Add persistent storage | [Storage and backup requirements](SWARM.md#add-a-service-with-persistent-storage) |
| Target Ampere A1 | [Compute placement and ARM images](SWARM.md#target-ampere-compute-services) |
| Add a worker | [Joining and validating nodes](SWARM.md#add-a-worker-node) |
| Update images, replicas, configs or secrets | [Configuration changes](SWARM.md#update-configuration) |
| Remove a service or maintain a node | [Service removal](SWARM.md#remove-a-service), [node maintenance](SWARM.md#maintain-or-remove-a-node) |
| Check a deployment | [Status and health checks](SWARM.md#deploy-and-check-production) |
| Back up data | [Backup coverage and recovery](BACKUPS.md) |

## Local preview

Run `docker compose up --build -d --wait` from the repository root and open http://localhost:8080. This uses the local preview Compose file; it does not start the production Swarm or its shared sign-in services. Stop the preview with `docker compose down`.

## Roll back an app deployment

Use `python3 scripts/swarm-deploy.py rollback` on node 1 and follow the [Swarm rollback guide](SWARM.md#roll-back). It restores the saved stack specification, including additional services and configuration. It does not restore database contents.

## Legacy setups

The [old Compose runbook](DOCKER-COMPOSE-LEGACY.md) is retained for migration recovery and reference. Its production commands, loopback ntfy port, Caddy bind mounts and fixed container addresses do not describe the live Swarm. Do not start that stack alongside Swarm. The [systemd alternative](README.md) is also separate from production.
