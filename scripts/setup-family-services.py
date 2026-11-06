"""Bootstrap private family service files as the portfolio checkout owner on the manager."""
import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

ROOT = Path("/opt/portfolio")
AUTH = ROOT / ".auth/secrets"
PRIVATE = ROOT / ".secrets/family"


def install(path, value):
    if path.exists():
        if path.read_text() != value:
            raise RuntimeError(f"Restore the matching private file: {path.name}")
        return
    with path.open("x") as f:
        f.write(value)


def new_client(task):
    output = subprocess.check_output(["sudo", "-n", "docker", "exec", task, "authelia", "crypto", "hash", "generate", "pbkdf2", "--variant", "sha512", "--iterations", "310000", "--random", "--random.length", "64"], text=True)
    password = re.search(r"^Random Password: (.+)$", output, re.M)
    digest = re.search(r"^Digest: (.+)$", output, re.M)
    if not password or not digest:
        raise RuntimeError("Could not create client secret.")
    return {"password": password[1], "digest": digest[1]}


def main():
    os.umask(0o077)
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = AUTH / "directory"
    directory.mkdir(mode=0o700, exist_ok=True)
    users = directory / "users.yml"
    if not users.exists():
        source = (AUTH / "users.yml").read_text()
        if "admins" not in json.loads(source)["users"]["rithvik"]["groups"]:
            raise RuntimeError("Expected an existing owner account.")
        install(users, source)
    recovery = PRIVATE / "recovery.json"
    clients = ("notes", "vault", "notes-edge", "vault-edge")
    if not recovery.exists():
        if any(PRIVATE.iterdir()) or any((AUTH / (client + "-client-hash")).exists() for client in clients):
            raise RuntimeError("Restore the existing private recovery set.")
        tasks = subprocess.check_output(["sudo", "-n", "docker", "ps", "-q", "--filter", "label=com.docker.swarm.service.name=portfolio_auth"], text=True).split()
        if len(tasks) != 1:
            raise RuntimeError("Expected one local Authelia task.")
        keys = {client: new_client(tasks[0]) for client in clients}
        for app in ("notes", "vault"):
            keys[app + "-edge"]["cookie"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        for name in ("notes_db_password", "outline_key", "outline_utils"):
            keys[name] = secrets.token_hex(32)
        install(recovery, json.dumps(keys) + "\n")
    keys = json.loads(recovery.read_text())
    for client in clients:
        install(AUTH / (client + "-client-hash"), keys[client]["digest"] + "\n")
    for app in ("notes", "vault"):
        edge = keys[app + "-edge"]
        install(PRIVATE / (app + "_edge"), "client_secret = " + json.dumps(edge["password"]) + "\ncookie_secret = " + json.dumps(edge["cookie"]) + "\n")
    install(PRIVATE / "outline_client", keys["notes"]["password"])
    install(PRIVATE / "vault_client", keys["vault"]["password"])
    for name in ("notes_db_password", "outline_key", "outline_utils"):
        install(PRIVATE / name, keys[name])
    install(PRIVATE / "outline_db_url", "postgres://outline:" + keys["notes_db_password"] + "@notes_db:5432/outline")
    print("Family directory and private service credentials ready.")


if __name__ == "__main__":
    main()
