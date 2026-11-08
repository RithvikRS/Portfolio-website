#!/usr/bin/env python3
"""Fail-closed launcher for the dedicated rootless Rakazo engine only.

The pinned runsc cannot use the rootless user-systemd D-Bus connection. Enforce
resources in a predelegated cgroup and join it BEFORE execing runsc. Never grant
write access to ancestor cgroups or fall back to unconstrained execution.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASE = Path("/var/lib/rakazo-pilot/engine")
CGROUP = Path("/sys/fs/cgroup/user.slice/user-986.slice/user@986.service/rakazo-computers")
RUNSC = "/opt/rakazo-runtime/release-20261102.0/runsc"
HOME_ROOT = Path("/var/lib/rakazo-pilot/workspaces/homes")
MAX_MEMORY = 2 * 1024**3
MAX_PIDS = 512


def limits(spec):
    resources = spec["linux"]["resources"]
    memory = int(resources["memory"]["limit"])
    quota = int(resources["cpu"]["quota"])
    period = int(resources["cpu"]["period"])
    pids = int(resources["pids"]["limit"])
    if not (6 * 1024**2 <= memory <= MAX_MEMORY and 0 < quota <= period <= 1000000 and 1 <= pids <= MAX_PIDS):
        raise ValueError("Missing or excessive computer resource limits")
    process = spec["process"]
    if process["user"]["uid"] != 1000 or process["user"]["gid"] != 1000:
        raise ValueError("Computer must use UID/GID 1000")
    if process.get("noNewPrivileges") is not True:
        raise ValueError("Computer must forbid privilege escalation")
    if any(process.get("capabilities", {}).values()):
        raise ValueError("Computer capabilities must be empty")
    return {"memory.max": str(memory), "memory.swap.max": "0", "memory.oom.group": "1", "cpu.max": f"{quota} {period}", "pids.max": str(pids)}


def validate_mounts(spec, cid):
    container_files = BASE / "cache/containers" / cid
    for mount in spec.get("mounts", []):
        if mount.get("type") != "bind" and not any(x in ("bind", "rbind") for x in mount.get("options", [])):
            continue
        source = Path(mount["source"]).resolve()
        destination = mount["destination"]
        if destination == "/home/rakazo" and source.is_relative_to(HOME_ROOT.resolve()) and source != HOME_ROOT.resolve():
            continue
        if destination in ("/etc/hostname", "/etc/hosts", "/etc/resolv.conf") and source.is_relative_to(container_files.resolve()):
            continue
        raise ValueError("Computer requested an unapproved host mount")


def launch(args):
    import fcntl
    # The engine supplies this flag. This adapter owns cgroup enforcement instead.
    args = [a for a in args if not a.startswith(("--systemd-cgroup", "--ignore-cgroups"))]
    if any(command in args for command in ("update", "restore", "checkpoint", "run")):
        raise ValueError("Unsupported computer lifecycle operation")
    identifiers = [a for a in args if re.fullmatch(r"[a-f0-9]{64}", a)]
    cid = identifiers[-1] if identifiers else None
    group = CGROUP / ("docker-" + cid) if cid else None
    if "create" in args:
        if not cid or not CGROUP.is_dir():
            raise ValueError("Missing approved cgroup delegation")
        bundle = os.getcwd()
        for i, value in enumerate(args):
            if value in ("--bundle", "-b"):
                bundle = args[i + 1]
            elif value.startswith("--bundle="):
                bundle = value.split("=", 1)[1]
        config = Path(bundle).resolve() / "config.json"
        if not config.is_relative_to((BASE / "exec/containerd").resolve()):
            raise ValueError("Unexpected OCI bundle")
        spec = json.loads(config.read_text())
        ceilings = limits(spec)
        validate_mounts(spec, cid)
        spec["root"]["readonly"] = True
        if not any(m["destination"] == "/tmp" for m in spec.get("mounts", [])):
            spec["mounts"].append({"destination": "/tmp", "type": "tmpfs", "source": "tmpfs", "options": ["rw", "nosuid", "nodev", "mode=1777", "size=128m"]})
        # A process joins its cgroup while still holding the admission lock. The
        # populated marker therefore closes the gap before runsc forks Sentry.
        with (BASE / "admission.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            for existing in CGROUP.glob("docker-*"):
                if "populated 1" in (existing / "cgroup.events").read_text():
                    raise ValueError("One-computer pilot limit reached")
            group.mkdir(exist_ok=True)
            for name, value in ceilings.items():
                (group / name).write_text(value)
                if (group / name).read_text().strip() != value:
                    raise ValueError("Resource limit did not apply")
            (group / "cgroup.procs").write_text(str(os.getpid()))
            config.write_text(json.dumps(spec))
    elif any(command in args for command in ("start", "exec")):
        if not group or not group.is_dir():
            raise ValueError("Computer has no enforced cgroup")
        (group / "cgroup.procs").write_text(str(os.getpid()))
    command = [RUNSC, "--systemd-cgroup=false", "--ignore-cgroups=true"] + args
    if "delete" in args and group:
        result = subprocess.run(command)
        if group.exists():
            report_dir = BASE / "resource-events"
            report_dir.mkdir(exist_ok=True)
            fields = ["memory.max", "memory.events", "cpu.max", "cpu.stat", "pids.max", "pids.events"]
            report = {name: (group / name).read_text().strip() for name in fields}
            (report_dir / (cid + ".json")).write_text(json.dumps(report))
            try:
                group.rmdir()
            except OSError:
                pass  # Never force removal of a populated group.
        return result.returncode
    os.execv(RUNSC, command)


if __name__ == "__main__":
    try:
        raise SystemExit(launch(sys.argv[1:]))
    except (KeyError, ValueError, OSError, IndexError) as error:
        # Never include the OCI environment, command, token or complete spec.
        record = {"container": next((a for a in reversed(sys.argv) if re.fullmatch(r"[a-f0-9]{64}", a)), None), "reason": str(error)}
        try:
            with (BASE / "policy-denials.jsonl").open("a") as audit:
                audit.write(json.dumps(record) + "\n")
        except OSError:
            pass
        print("Rakazo runtime refused startup: " + str(error), file=sys.stderr)
        raise SystemExit(1)
