#!/usr/bin/env python3
"""Stage the pinned offline pilot on Ampere; never start an agent or daemon.

Download official gVisor artifacts, verify the pinned archive checksum, and
export the pinned computer image without executing it through Docker.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import posixpath
import pwd
import shutil
import subprocess
import tarfile
import urllib.request

NODE = "tzqsl1t88r3l1i8zcqvcmredo"
BASE = Path("/var/lib/rakazo-pilot")
RUNTIME = Path("/opt/rakazo-runtime/release-20261102.0")
ARCHIVE_SHA256 = "909c95f245a46000d3bb0d5285f07dde23597056e7c3a4aab758b218e95bdab0"
URL = "https://github.com/google/gvisor/releases/download/release-20261102.0/gvisor-aarch64.tar.bz2"
IMAGE = "ghcr.io/elie222/rakazo/computer@sha256:2f1d4f4e00aa2a055ec129bd525477be2e6e0a2614945ae19ab7ae9a52a29baa"


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs)


def check_path(path):
    if path.is_symlink() or path.resolve() != path:
        raise RuntimeError("Refuse redirected path: " + str(path))


def main():
    if os.geteuid() != 0 or platform.machine() != "aarch64":
        raise RuntimeError("Run as root on Ampere")
    if run(["docker", "info", "--format", "{{.Swarm.NodeID}}"]).stdout.strip() != NODE:
        raise RuntimeError("Unexpected Swarm node")
    if run(["getenforce"]).stdout.strip() != "Enforcing":
        raise RuntimeError("Keep SELinux enforcing")
    if shutil.disk_usage("/").free < 10 * 1024**3:
        raise RuntimeError("Require 10 GiB free for staging")
    for path in (BASE, RUNTIME):
        check_path(path)
    try:
        account = pwd.getpwnam("rakazo-pilot")
    except KeyError:
        run(["useradd", "--system", "--create-home", "--home-dir", str(BASE), "--shell", "/sbin/nologin", "rakazo-pilot"])
        account = pwd.getpwnam("rakazo-pilot")
    if account.pw_uid == 0 or account.pw_dir != str(BASE):
        raise RuntimeError("Unexpected pilot account")
    groups = run(["id", "-G", "rakazo-pilot"]).stdout.split()
    if groups != [str(account.pw_gid)]:
        raise RuntimeError("Pilot must not have supplementary groups")
    rootfs = BASE / "computer/rootfs"
    check_path(rootfs)
    if rootfs.exists():
        raise RuntimeError("Computer rootfs already exists; preserve it and run verification")
    active = subprocess.run(["pgrep", "-u", "rakazo-pilot"], capture_output=True)
    if active.returncode != 1:
        raise RuntimeError("Pilot account has active processes, or process check failed")
    BASE.chmod(0o700)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    archive = RUNTIME / "download.tar.bz2"
    check_path(archive)
    with urllib.request.urlopen(URL, timeout=60) as response, archive.open("xb") as output:
        total = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > 256 * 1024**2:
                raise RuntimeError("Runtime archive exceeds expected size")
            output.write(block)
    try:
        if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
            raise RuntimeError("Runtime archive checksum mismatch")
        with tarfile.open(archive) as bundle:
            bundle.extractall(RUNTIME, filter="data")
    finally:
        archive.unlink(missing_ok=True)
    existing_image = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0
    run(["docker", "pull", IMAGE], timeout=300)
    cid = None
    export = None
    try:
        cid = run(["docker", "create", "--network=none", IMAGE]).stdout.strip()
        rootfs.mkdir(parents=True)
        export = subprocess.Popen(["docker", "export", cid], stdout=subprocess.PIPE)
        total = 0

        def safe(member, destination):
            nonlocal total
            total += member.size
            if total > 4 * 1024**3:
                raise RuntimeError("Computer rootfs exceeds four GiB")
            if member.issym() and member.linkname.startswith("/"):
                member.linkname = posixpath.relpath(member.linkname.lstrip("/"), posixpath.dirname(member.name))
            return tarfile.data_filter(member, destination)

        with tarfile.open(fileobj=export.stdout, mode="r|") as bundle:
            bundle.extractall(rootfs, filter=safe)
        if export.wait(timeout=30) != 0:
            raise RuntimeError("Image export failed")
        for directory, dirs, files in os.walk(BASE / "computer"):
            os.chown(directory, account.pw_uid, account.pw_gid)
            for name in dirs + files:
                os.lchown(os.path.join(directory, name), account.pw_uid, account.pw_gid)
        manifest = {"image": IMAGE, "runtime_archive_sha256": ARCHIVE_SHA256, "rootfs_bytes": total, "models": "disabled"}
        (BASE / "staging.json").write_text(json.dumps(manifest, indent=2) + "\n")
    finally:
        if export is not None and export.poll() is None:
            export.terminate()
            export.wait(timeout=20)
        if cid:
            run(["docker", "rm", cid])
        if not existing_image:
            # No force: refuse deletion if another container has adopted the image.
            run(["docker", "image", "rm", IMAGE])
    print("Staged offline runtime and rootfs. Run verify-rakazo-gvisor.py before use.")


if __name__ == "__main__":
    main()
