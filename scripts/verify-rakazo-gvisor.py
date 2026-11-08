#!/usr/bin/env python3
"""Run the offline Rakazo computer compatibility/isolation gate on Ampere.

Requires the separately staged, verified runtime and computer rootfs. Never starts
Docker, changes its configuration, opens a port, or accepts arbitrary workloads.
Run as root to create a bounded systemd unit whose workload runs as rakazo-pilot.
"""
import json
import os
from pathlib import Path
import platform
import pwd
import shlex
import subprocess
import time
import uuid

BASE = Path("/var/lib/rakazo-pilot")
RUNSC = Path("/opt/rakazo-runtime/release-20261102.0/runsc")
ROOTFS = BASE / "computer/rootfs"
IMAGE = "ghcr.io/elie222/rakazo/computer@sha256:2f1d4f4e00aa2a055ec129bd525477be2e6e0a2614945ae19ab7ae9a52a29baa"

GUEST = r'''import os,socket,urllib.request,time,subprocess
assert os.getuid() == 1000
assert "gvisor" in os.uname().release
status = open("/proc/self/status").read()
assert "NoNewPrivs:\t1" in status
assert "CapEff:\t0000000000000000" in status
for path in ["/srv/swarm", "/opt/portfolio", "/run/docker.sock", "/run/incus/unix.socket", "/var/lib/rakazo-pilot/HOST_ONLY_PROBE"]:
    assert not os.path.exists(path), path
try:
    open("/etc/pilot-write", "w").close()
except OSError:
    pass
else:
    raise RuntimeError("Root filesystem is writable")
os.makedirs("/tmp/mount-probe", exist_ok=True)
assert subprocess.run(["mount", "-t", "tmpfs", "tmpfs", "/tmp/mount-probe"], capture_output=True).returncode != 0
for host in ["169.254.169.254", "144.24.135.201", "129.154.45.198", "129.225.69.240", "10.0.0.1", "1.1.1.1", "::ffff:169.254.169.254", "fd00::1"]:
    try:
        c = socket.create_connection((host, 80), 1)
        c.close()
    except OSError:
        continue
    raise RuntimeError("Unexpected network access: " + host)
for attempt in range(50):
    try:
        with urllib.request.urlopen("http://127.0.0.1:6080/embed.html", timeout=1) as response:
            assert response.status == 200
        break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError("Desktop HTTP did not become ready")
result = subprocess.run(["chromium", "--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--no-first-run", "--dump-dom", "data:text/html,<title>RAKAZO_OFFLINE_PROBE</title>"], capture_output=True, text=True, timeout=30)
assert result.returncode == 0 and "RAKAZO_OFFLINE_PROBE" in result.stdout, (result.returncode, result.stderr[-1500:])
print("GUEST_CHECKS_PASS", flush=True)
time.sleep(5)
'''


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs)


def verify():
    if os.geteuid() != 0 or platform.machine() != "aarch64":
        raise RuntimeError("Run as root on the approved ARM64 pilot host")
    node = run(["docker", "info", "--format", "{{.Swarm.NodeID}}"]).stdout.strip()
    if node != "tzqsl1t88r3l1i8zcqvcmredo":
        raise RuntimeError("Unexpected Swarm node")
    account = pwd.getpwnam("rakazo-pilot")
    if account.pw_uid == 0 or account.pw_dir != str(BASE):
        raise RuntimeError("Unexpected pilot account")
    for path in (BASE, RUNSC, ROOTFS):
        if path.is_symlink() or path.resolve() != path or not path.exists():
            raise RuntimeError("Missing or redirected pilot path: " + str(path))
    if run(["getenforce"]).stdout.strip() != "Enforcing":
        raise RuntimeError("Keep host SELinux enforcing")
    version = run([str(RUNSC), "--version"]).stdout.strip()
    if "release-20261102.0" not in version:
        raise RuntimeError("Unexpected runtime version")
    token = uuid.uuid4().hex[:12]
    directory = BASE / ("verify-" + token)
    directory.mkdir(mode=0o700)
    os.chown(directory, account.pw_uid, account.pw_gid)
    (BASE / "HOST_ONLY_PROBE").write_text("Disposable isolation marker; no secret.\n")
    run([str(RUNSC), "spec"], cwd=directory)
    spec_path = directory / "config.json"
    spec = json.loads(spec_path.read_text())
    spec["root"] = {"path": str(ROOTFS), "readonly": True}
    spec["process"].update({
        "terminal": False, "user": {"uid": 1000, "gid": 1000},
        "cwd": "/home/rakazo", "noNewPrivileges": True,
        "capabilities": {k: [] for k in ["bounding", "effective", "inheritable", "permitted", "ambient"]},
        "env": ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "HOME=/home/rakazo", "LANG=C.UTF-8", "DISPLAY=:1", "NSS_WRAPPER_PASSWD=/tmp/rakazo-nss/passwd", "NSS_WRAPPER_GROUP=/tmp/rakazo-nss/group"],
        "args": ["/bin/bash", "-ec", "/usr/bin/env -u LD_PRELOAD /usr/local/bin/rakazo-computer >/tmp/computer-start.log 2>&1 &\npython3 -c " + shlex.quote(GUEST)],
    })
    spec["linux"].pop("resources", None)  # Enforce ceilings in the enclosing host unit.
    spec["mounts"].append({"destination": "/home/rakazo", "type": "tmpfs", "source": "tmpfs", "options": ["nosuid", "nodev", "mode=0700", "uid=1000", "gid=1000", "size=268435456"]})
    spec_path.write_text(json.dumps(spec))
    runner = directory / "entry.py"
    arguments = ["unshare", "--user", "--map-root-user", "--net", str(RUNSC), "--root=" + str(directory / "state"), "--ignore-cgroups=true", "--network=none", "--platform=systrap", "run", "probe"]
    runner.write_text("import os\nos.chdir(" + repr(str(directory)) + ")\nfor fd,name in enumerate(['stdin','stdout','stderr']):\n f=os.open(name,os.O_RDWR|os.O_CREAT|os.O_TRUNC,0o600)\n os.dup2(f,fd)\n if f>2:os.close(f)\nos.execv('/usr/bin/unshare'," + repr(arguments) + ")\n")
    unit = "rakazo-verify-" + token
    properties = ["User=rakazo-pilot", "MemoryMax=2G", "MemorySwapMax=0", "CPUQuota=100%", "TasksMax=512", "RuntimeMaxSec=100", "PrivateNetwork=yes", "NoNewPrivileges=yes", "ProtectHome=yes", "ProtectSystem=strict", "ProtectKernelTunables=yes", "ProtectKernelModules=yes", "ProtectControlGroups=yes", "TemporaryFileSystem=/run:ro", "InaccessiblePaths=-/srv/swarm -/opt/portfolio", "ReadWritePaths=" + str(directory)]
    command = ["systemd-run", "--unit=" + unit, "--wait", "--pipe", "--collect"]
    for prop in properties:
        command += ["-p", prop]
    command += ["/usr/bin/python3", str(runner)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    evidence = {"runtime": version, "image": IMAGE, "model_connections": "disabled", "host_selinux": "Enforcing"}
    try:
        cg = Path("/sys/fs/cgroup/system.slice") / (unit + ".service")
        for _ in range(50):
            if (cg / "memory.max").exists():
                break
            if process.poll() is not None:
                raise RuntimeError("Probe unit exited before host checks")
            time.sleep(0.1)
        evidence["cgroup"] = {name: (cg / name).read_text().strip() for name in ["memory.max", "memory.swap.max", "cpu.max", "pids.max"]}
        assert evidence["cgroup"]["memory.max"] == "2147483648"
        assert evidence["cgroup"]["memory.swap.max"] == "0"
        assert evidence["cgroup"]["pids.max"] == "512"
        quota, period = map(int, evidence["cgroup"]["cpu.max"].split())
        assert quota == period
        sentries = []
        for _ in range(50):
            for pid in (cg / "cgroup.procs").read_text().split():
                try:
                    status = Path("/proc", pid, "status").read_text()
                    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
                    if fields["Name"].strip() != "gvisor_sentry":
                        continue
                    assert set(fields["Uid"].split()) == {str(account.pw_uid)}
                    assert fields["Seccomp"].strip() == "2"
                    assert fields["NoNewPrivs"].strip() == "1"
                    sentries.append({"uid": account.pw_uid, "seccomp": 2, "no_new_privileges": True})
                except FileNotFoundError:
                    continue
            if sentries:
                break
            time.sleep(0.1)
        assert sentries, "No confined Sentry observed in bounded cgroup"
        evidence["sentries"] = sentries
        stdout, stderr = process.communicate(timeout=105)
        guest = (directory / "stdout").read_text()
        if process.returncode != 0 or "GUEST_CHECKS_PASS" not in guest:
            raise RuntimeError("Probe failed; inspect private logs in " + str(directory) + "\n" + stderr[-1000:])
        evidence["guest_checks"] = "passed: UID, kernel, NNP, capabilities, filesystem, mount denial, network denial, desktop HTTP, Chromium"
        evidence["result"] = "PASS"
    finally:
        subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=20)
        if process.poll() is None:
            process.communicate(timeout=20)
        (BASE / "HOST_ONLY_PROBE").unlink(missing_ok=True)
    report = directory / "result.json"
    report.write_text(json.dumps(evidence, indent=2) + "\n")
    report.chmod(0o600)
    print(json.dumps(evidence, indent=2))
    print("Private report: " + str(report))


if __name__ == "__main__":
    verify()
