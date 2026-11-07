#!/usr/bin/env python3
"""Prepare private OmniRoute state. Run manager, then worker (private JSON on stdin)."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

IMAGE = "ghcr.io/cheaper-inference/omniroute:3.8.53@sha256:b52a17661a1aff42ffb78f349f423e986dfc55b57274f28559f8387622ef8ee4"
NODE = "tzqsl1t88r3l1i8zcqvcmredo"
DATA = Path("/srv/swarm/omniroute")

def docker(*args, data=None):
    result = subprocess.run(["sudo", "-n", "docker", *args], input=data, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("Docker operation failed: " + args[0] + "; inspect the private bootstrap container locally.")
    return result.stdout.strip()

def manager():
    spec = importlib.util.spec_from_file_location("family", Path(__file__).with_name("setup-family-services.py"))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    private = Path("/opt/portfolio/.secrets/omniroute")
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    recovery = private / "recovery.json"
    if not recovery.exists():
        if any(private.iterdir()):
            raise RuntimeError("Restore the existing OmniRoute recovery set first.")
        tasks = docker("ps", "-q", "--filter", "label=com.docker.swarm.service.name=portfolio_auth").split()
        if len(tasks) != 1:
            raise RuntimeError("Expected one local Authelia task.")
        keys = {name: helper.new_client(tasks[0]) for name in ["omniroute", "omniroute-edge"]}
        keys["omniroute-edge"]["cookie"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        keys["bootstrap_password"] = secrets.token_urlsafe(48)
        helper.install(recovery, json.dumps(keys) + "\n")
    keys = json.loads(recovery.read_text())
    for name in ["omniroute", "omniroute-edge"]:
        helper.install(helper.AUTH / (name + "-client-hash"), keys[name]["digest"] + "\n")
    edge = keys["omniroute-edge"]
    helper.install(private / "edge.cfg", 'client_secret = ' + json.dumps(edge["password"]) + '\ncookie_secret = ' + json.dumps(edge["cookie"]) + '\n')
    print("Manager private credentials ready; values were not printed.")

def worker():
    if docker("info", "--format", "{{.Swarm.NodeID}}") != NODE or not os.path.ismount("/srv/swarm"):
        raise RuntimeError("Run on Ampere with its /srv/swarm filesystem mounted.")
    keys = json.load(sys.stdin)
    subprocess.run(["sudo", "-n", "install", "-d", "-m", "700", "-o", "1000", "-g", "1000", str(DATA)], check=True)
    marker = DATA / ".portfolio-bootstrap-complete"
    if marker.exists():
        print("OmniRoute is already initialized; preserved existing settings and provider keys.")
        return
    if docker("ps", "-q", "--filter", "label=com.docker.swarm.service.name=portfolio_omniroute"):
        raise RuntimeError("Initialize before deploying the production service.")
    private = DATA / ".portfolio-bootstrap.json"
    env = DATA / ".portfolio-bootstrap.env"
    private.write_text(json.dumps(keys), encoding="utf-8")
    env.write_text("INITIAL_PASSWORD=" + keys["bootstrap_password"] + "\nREQUIRE_API_KEY=true\nAUTH_COOKIE_SECURE=true\nHOSTNAME=0.0.0.0\nENABLE_REQUEST_LOGS=false\nAPP_LOG_LEVEL=warn\nNODE_OPTIONS=--max-old-space-size=1024\n", encoding="utf-8")
    name = "portfolio-omniroute-bootstrap"
    started = False
    try:
        docker("pull", IMAGE)
        docker("run", "-d", "--name", name, "--memory", "1536m", "--cpus", "2", "--cap-drop", "ALL", "--env-file", str(env), "-v", str(DATA) + ":/app/data", IMAGE)
        started = True
        for attempt in range(60):
            status = docker("inspect", name, "--format", "{{.State.Health.Status}}")
            if status == "healthy": break
            time.sleep(3)
        else: raise RuntimeError("Bootstrap failed to become healthy.")
        source = Path(__file__).with_name("bootstrap-omniroute.mjs").read_text(encoding="utf-8")
        print(docker("exec", "-i", name, "node", "--input-type=module", data=source))
    finally:
        if started: docker("rm", "-f", name)
        private.unlink(missing_ok=True)
        env.unlink(missing_ok=True)
    print("Worker initialized; data and generated server.env remain in /srv/swarm/omniroute.")

if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["manager", "worker"])
    args = parser.parse_args()
    manager() if args.role == "manager" else worker()
