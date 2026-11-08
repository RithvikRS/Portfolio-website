#!/usr/bin/env python3
"""Use only this account's delegated hierarchy; never modify host ancestors."""
import os
from pathlib import Path
root = Path("/sys/fs/cgroup/user.slice/user-986.slice/user@986.service")
if os.getuid() != 986 or root.stat().st_uid != 986:
    raise SystemExit("Expected dedicated delegated user manager")
(root / "cgroup.subtree_control").write_text("+cpu +memory +pids")
group = root / "rakazo-computers"
group.mkdir(exist_ok=True)
for name,value in {"memory.max":"3221225472","memory.swap.max":"0","cpu.max":"100000 100000","pids.max":"1024","cgroup.subtree_control":"+cpu +memory +pids"}.items():
    if name == "cgroup.subtree_control" or (group / name).read_text().strip() != value:
        (group / name).write_text(value)
