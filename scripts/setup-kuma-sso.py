"""Prepare private credentials for the Kuma OIDC proxy on the Swarm manager."""
import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess


def install(path, content):
    if path.exists():
        if path.read_text() != content:
            raise RuntimeError(f"Restore the matching private file: {path.name}")
        return
    with path.open("x") as stream:
        stream.write(content)


def main():
    os.umask(0o077)
    root = Path("/opt/portfolio")
    private = root / ".secrets"
    private.mkdir(mode=0o700, exist_ok=True)
    source = private / "kuma-oidc-recovery.json"
    config = private / "kuma-oidc.cfg"
    digest = root / ".auth/secrets/kuma-client-hash"
    if not source.exists():
        if config.exists() or digest.exists():
            raise RuntimeError("Restore the matching recovery file before continuing.")
        docker = ["sudo", "-n", "docker"]
        tasks = subprocess.check_output(docker + ["ps", "-q", "--filter", "label=com.docker.swarm.service.name=portfolio_auth"], text=True).split()
        if len(tasks) != 1:
            raise RuntimeError("Expected one running Authelia task on this manager.")
        result = subprocess.check_output(docker + ["exec", tasks[0], "authelia", "crypto", "hash", "generate", "pbkdf2", "--variant", "sha512", "--iterations", "310000", "--random", "--random.length", "64"], text=True)
        client = re.search(r"^Random Password: (.+)$", result, re.M)
        hashed = re.search(r"^Digest: (.+)$", result, re.M)
        if not client or not hashed:
            raise RuntimeError("Authelia did not generate the client credential.")
        install(source, json.dumps(dict(client=client[1], digest=hashed[1], cookie=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())) + "\n")
    keys = json.loads(source.read_text())
    install(config, "client_secret = " + json.dumps(keys["client"]) + "\ncookie_secret = " + json.dumps(keys["cookie"]) + "\n")
    install(digest, keys["digest"] + "\n")
    print("Private Kuma OIDC credentials ready.")


if __name__ == "__main__":
    main()
