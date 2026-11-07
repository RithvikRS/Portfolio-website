#!/usr/bin/env python3
"""Enter only the dedicated engine's existing unprivileged namespaces."""
import os
from pathlib import Path
import sys
import time
base = Path("/var/lib/rakazo-pilot")
for _ in range(60):
    try:
        pid = int((base / "engine/dockerd.pid").read_text())
        if Path(f"/proc/{pid}").stat().st_uid != os.getuid() or b"dockerd" not in Path(f"/proc/{pid}/cmdline").read_bytes():
            raise RuntimeError("Unexpected engine process")
        if os.readlink(f"/proc/{pid}/ns/net") == os.readlink("/proc/self/ns/net"):
            raise RuntimeError("Engine network isolation missing")
        break
    except (FileNotFoundError, ValueError):
        time.sleep(1)
else:
    raise SystemExit("Isolated engine not ready")
commands = {
 "controller": ["/opt/rakazo-runtime/node", str(base / "controller-src/infra/sandboxes/supervisor/node_modules/tsx/dist/cli.mjs"), str(base / "controller-src/infra/sandboxes/supervisor/src/index.ts")],
 "bridge": ["/opt/rakazo-runtime/node", "/opt/rakazo-runtime/pilot/bridge.mjs"],
}
os.execvp("nsenter", ["nsenter", "-t", str(pid), "--user", "--mount", "--net", *commands[sys.argv[1]]])
