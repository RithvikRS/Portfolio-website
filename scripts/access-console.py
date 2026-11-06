"""Owner-only console for individual Authelia accounts and application grants."""
import base64
import hashlib
import html
import json
import os
import re
import secrets
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

DIRECTORY = Path("/directory/users.yml")
BASE = "/admin/access/"
SERVICES = {"notes": "Outline notes", "vault": "Password vault"}
OWNER = os.environ.get("OWNER", "rithvik")
ORIGIN = os.environ.get("ORIGIN", "https://rithvik.ddns.net")
esc = html.escape


def save(directory, record):
    with tempfile.NamedTemporaryFile(dir=directory.parent, mode="w", delete=False) as tmp:
        json.dump(record, tmp, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
    os.replace(tmp.name, directory)


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, 310000)
    def encode(value):
        return base64.b64encode(value).decode().rstrip("=").replace("+", ".")
    return "$pbkdf2-sha512$310000$" + encode(salt) + "$" + encode(digest)


def update(directory, fields):
    record = json.loads(directory.read_text())
    users = record["users"]
    username = fields.get("username", [""])[0]
    if not re.fullmatch("[a-z][a-z0-9_-]{1,39}", username):
        raise ValueError("Use 2 to 40 lowercase letters, numbers, dashes or underscores.")
    user = users.get(username)
    if username == OWNER or (user and "admins" in user["groups"]):
        raise ValueError("Manage infrastructure administrators through the recovery procedure.")
    action = fields.get("action", [""])[0]
    grants = set(fields.get("services", []))
    if grants - SERVICES.keys():
        raise ValueError("Unknown service.")
    password = None
    if action == "create":
        email = fields.get("email", [""])[0].strip().lower()
        if user or not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", email):
            raise ValueError("Choose a new username and enter a valid email.")
        if any(u["email"].lower() == email for u in users.values()):
            raise ValueError("An account already uses this email.")
        name = fields.get("name", [""])[0].strip()
        if not name or len(name) > 100 or len(email) > 254:
            raise ValueError("Enter a display name and a valid email.")
        password = secrets.token_urlsafe(24)
        user = users[username] = dict(displayname=name, email=email, groups=[], password=password_hash(password))
    elif action != "save" or not user:
        raise ValueError("Unknown account or operation.")
    user["groups"] = sorted((set(user["groups"]) - SERVICES.keys()) | grants)
    user["disabled"] = "disabled" in fields
    save(directory, record)
    return password


def checks(groups):
    return " ".join(f'<label><input type="checkbox" name="services" value="{key}" {"checked" if key in groups else ""}> {title}</label>' for key, title in SERVICES.items())


def page(users):
    rows = []
    for name, u in sorted(users.items()):
        title = f'<h3>{esc(u["displayname"])}</h3><p>{esc(name)} · {esc(u["email"])}</p>'
        if name == OWNER or "admins" in u["groups"]:
            rows.append(f"<section>{title}<p>Infrastructure administrator</p></section>")
        else:
            disabled = "checked" if u.get("disabled") else ""
            rows.append(f'<section>{title}<form method="post"><input type="hidden" name="username" value="{esc(name)}">{checks(u["groups"])} <label><input type="checkbox" name="disabled" {disabled}> Disable account</label> <button name="action" value="save">Save access</button></form></section>')
    return (f'<a href="/admin/">Workspace</a><h1>Service access</h1><p>Grant access by account. Manage shared documents and vault collections inside their apps.</p>'
            + "".join(rows) + f'<section><h2>Create an account</h2><form method="post"><label>Username <input name="username" required></label> <label>Name <input name="name" required></label> <label>Email <input name="email" type="email" required></label><p>{checks([])}</p><button name="action" value="create">Create account</button></form></section>')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_page(self, status, body):
        content = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Service access</title><style>body{font:1rem/1.5 system-ui;color:#193d30;max-width:55rem;padding:2rem;margin:auto}section{border-top:1px solid #ccd6ce;padding:1rem 0}label,button{display:inline-block;margin:.3rem}button,input{font:inherit}code{overflow-wrap:anywhere}</style><main>' + body + '</main></html>').encode()
        self.send_response(status)
        for k,v in {"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store","Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'","X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","Content-Length":str(len(content))}.items():
            self.send_header(k,v)
        self.end_headers()
        self.wfile.write(content)

    def authorized(self):
        # Caddy supplies these after MFA on a dedicated unpublished overlay.
        return self.headers.get("Remote-User") == OWNER and "admins" in self.headers.get("Remote-Groups","").split(",")

    def do_GET(self):
        if self.path == "/health":
            self.send_page(200, "ok")
        elif self.path == "/dashboard/" and self.headers.get("Remote-User"):
            groups = set(self.headers.get("Remote-Groups", "").split(","))
            if self.authorized():
                self.send_response(303)
                self.send_header("Location", "/admin/")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            links = [f'<p><a href="/{key}" target="_blank" rel="noopener">{title}</a></p>' for key, title in SERVICES.items() if key in groups]
            self.send_page(200, "<h1>Your dashboard</h1>" + ("".join(links) or "<p>No services assigned.</p>") + '<a href="/auth/logout">Sign out of dashboard</a>')
        elif urlsplit(self.path).path != BASE or not self.authorized():
            self.send_page(403, "Access denied")
        else:
            self.send_page(200, page(json.loads(DIRECTORY.read_text())["users"]))

    def do_POST(self):
        if self.path != BASE or not self.authorized() or self.headers.get("Origin") != ORIGIN:
            return self.send_page(403, "Access denied")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192 or self.headers.get_content_type() != "application/x-www-form-urlencoded":
                raise ValueError("Invalid form.")
            password = update(DIRECTORY, parse_qs(self.rfile.read(length).decode(), max_num_fields=10))
        except ValueError as error:
            return self.send_page(400, esc(str(error)))
        if password:
            self.send_page(201, f'<h1>Account created</h1><p>Save this password and give it privately to the account owner.</p><code>{esc(password)}</code><p><a href="{BASE}">Return to service access</a></p>')
        else:
            self.send_response(303)
            self.send_header("Location", BASE)
            self.end_headers()


if __name__ == "__main__":
    os.umask(0o077)
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
