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
        if user:
            raise ValueError("That username is already in use. Choose another username.")
        if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", email):
            raise ValueError("Enter a valid sign-in email address.")
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


GUIDE = "/dashboard/guide/"


def navigation(owner, groups, current):
    home = "/admin/" if owner else "/dashboard/"
    workspace = [("Overview", home)]
    if owner:
        workspace.append(("Service access", BASE))
    workspace.append(("User guide", GUIDE))
    personal = [(title, "/" + key) for key, title in [("notes", "Outline"), ("vault", "Vaultwarden")] if owner or key in groups]
    sections = [("Workspace", workspace), ("Personal tools", personal)]
    if owner:
        sections.append(("Administration", [("OmniRoute", "/models"), ("Uptime Kuma", "/uptime"), ("Portainer", "/portainer/"), ("Fieldnotes", "/admin/notes/")]))
    parts = []
    for title, items in sections:
        if items:
            parts.append(f'<p class="nav-label">{title}</p>')
        for name, path in items:
            attrs = 'class="nav-item active" aria-current="page"' if path == current else 'class="nav-item"'
            parts.append(f'<a {attrs} href="{path}">{name}</a>')
    links = "".join(parts)
    return (f'<aside class="sidebar"><a class="workspace-brand" href="{home}"><span class="brand-symbol">r.</span>'
            '<span>rithvik<span class="brand-caption">workspace</span></span></a>'
            f'<nav class="desktop-nav" aria-label="Workspace">{links}</nav>'
            f'<details class="mobile-nav"><summary>Menu</summary><nav aria-label="Workspace">{links}</nav></details></aside>')


def guide(groups, owner):
    parts = ['<h1>User guide</h1><p class="intro">Start here when you join the workspace or need help getting back in.</p>',
             '<section class="panel"><h2>First sign-in</h2><ol><li>Open <a href="/dashboard/">your dashboard</a> and enter the username and password the owner gave you.</li>'
             '<li>Register your own authenticator when prompted. Ask the owner privately for your enrollment message, then enter the current six-digit code.</li>'
             '<li>Choose a service from Personal tools. If a service is missing, ask the owner to grant access to your account.</li></ol></section>']
    if owner or "notes" in groups:
        parts.append('<section class="panel"><h2>Outline notes</h2><p>Open <a href="/notes">Outline</a> and choose Authelia. Create a document in your Personal space for a private note. To collaborate, open the document, choose Share, select the person, and choose view or edit. Check the collection permissions before adding a shared document.</p></section>')
    if owner or "vault" in groups:
        parts.append('<section class="panel"><h2>Password vault</h2><p>Open <a href="/vault">Vaultwarden</a>, enter the email assigned to your workspace account and choose single sign-on. On your first visit, set your own master password. Use <strong>Lock now</strong> when you want to unlock the vault again on the same device. Keep your master password private.</p></section>')
    if owner:
        parts.append('<section class="panel"><h2>Administrator tools</h2><p>Open <a href="/admin/access/">Service access</a> to create a member or edit their grants. Use <a href="/models">OmniRoute</a> for provider keys and model routing, <a href="/uptime">Kuma</a> for monitoring, <a href="/portainer/">Portainer</a> for containers and <a href="/admin/notes/">Fieldnotes</a> for public writing.</p></section>')
    parts.append('<section class="panel"><h2>Sign out or get help</h2><p>Use Log out inside a service to return to your dashboard. On a shared device, also sign out of the dashboard and close the browser. If you lose access to your authenticator, contact the workspace owner privately.</p></section>')
    return "".join(parts)


def checks(groups):
    return "".join(f'<label class="choice"><input type="checkbox" name="services" value="{key}" {"checked" if key in groups else ""}> {title}</label>' for key, title in SERVICES.items())


def create_form(fields):
    inputs = []
    for key, title, kind, limit in [("name", "Display name", "text", 100), ("username", "Username", "text", 40), ("email", "Sign-in email", "email", 254)]:
        value = esc(fields.get(key, [""])[0])
        inputs.append(f'<label class="field">{title}<input name="{key}" type="{kind}" maxlength="{limit}" value="{value}" required></label>')
    return (f'<a class="back" href="{BASE}">← Accounts</a><h1>Create account</h1><p class="intro">Choose the services this person can open. You’ll receive their initial password after saving.</p>'
            + '<form class="panel" method="post" action="' + BASE + '">' + "".join(inputs)
            + '<p>Use 2–40 lowercase letters, numbers, underscores or dashes for the username. Start with a letter.</p>'
            + '<fieldset><legend>Service permissions</legend>' + checks(fields.get("services", [])) + '</fieldset>'
            + f'<button name="action" value="create">Create account</button> <a class="back" href="{BASE}">Cancel</a></form>')


def page(users, edit=None):
    rows = []
    for name, u in sorted(users.items(), key=lambda item: item[1]["displayname"].casefold()):
        owner = name == OWNER or "admins" in u["groups"]
        status = "Administrator" if owner else ("Disabled" if u.get("disabled") else "Active")
        grants = ", ".join(title for key, title in SERVICES.items() if key in u["groups"])
        title = f'<div><h3>{esc(u["displayname"])}</h3><p>{esc(name)} · {esc(u["email"])}</p></div>'
        row = f'<article class="member"><div class="member-head">{title}<span class="state">{status}</span></div>'
        if owner:
            row += '<p>Infrastructure owner · All services</p>'
        else:
            disabled = "checked" if u.get("disabled") else ""
            row += (f'<p>{esc(grants) or "No services assigned"}</p><details {"open" if edit == name else ""}><summary>Edit access</summary>'
                    f'<form method="post" action="{BASE}"><input type="hidden" name="username" value="{esc(name)}">'
                    '<fieldset><legend>Service permissions</legend>' + checks(u["groups"]) + '</fieldset>'
                    f'<fieldset><legend>Account status</legend><label class="choice"><input type="checkbox" name="disabled" {disabled}> Disable sign-in</label></fieldset>'
                    '<button name="action" value="save">Save changes</button></form></details>')
        rows.append(row + '</article>')
    return ('<div class="page-heading"><div><h1>Service access</h1><p class="intro">Manage who can sign in and which services they can open.</p></div>'
            f'<a class="action" href="{BASE}?new=1">Create account</a></div><section class="panel"><h2>Accounts ({len(users)})</h2>' + "".join(rows) + '</section>')


def model_admin_allowed(directory, email):
    """Accept only the email from Caddy's verified OIDC proxy response."""
    if not email or len(email) > 254:
        return False
    try:
        users = json.loads(directory.read_text())["users"].values()
        matches = [u for u in users if u.get("email", "").casefold() == email.casefold()]
        return (len(matches) == 1 and not matches[0].get("disabled", False)
                and "admins" in matches[0].get("groups", []))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_page(self, status, body):
        path = urlsplit(self.path).path
        groups = self.headers.get("Remote-Groups", "").split(",")
        nav = navigation(self.authorized(), groups, path) if self.headers.get("Remote-User") and status != 403 else ""
        title = {BASE: "Service access", GUIDE: "User guide", "/dashboard/": "Your dashboard"}.get(path, "Workspace")
        content = (f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · Rithvik</title>'
                   '<link rel="stylesheet" href="/css/admin.css"><body><a class="skip" href="#main">Skip to content</a>'
                   f'<div class="workspace">{nav}<div class="workspace-body"><header class="topbar"><span>Workspace / {title}</span><a href="/auth/logout">Sign out</a></header>'
                   f'<main class="console" id="main">{body}</main></div></div></body></html>').encode()
        self.send_response(status)
        for k,v in {"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store","Content-Security-Policy":"default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'","X-Content-Type-Options":"nosniff","Referrer-Policy":"same-origin","Content-Length":str(len(content))}.items():
            self.send_header(k,v)
        self.end_headers()
        self.wfile.write(content)

    def authorized(self):
        # Caddy supplies these after MFA on a dedicated unpublished overlay.
        return self.headers.get("Remote-User") == OWNER and "admins" in self.headers.get("Remote-Groups","").split(",")

    def do_GET(self):
        if self.path == "/internal/authorize-models":
            allowed = model_admin_allowed(DIRECTORY, self.headers.get("X-Models-Email", ""))
            self.send_response(204 if allowed else 403)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/health":
            self.send_page(200, "ok")
        elif self.path == GUIDE and self.headers.get("Remote-User"):
            self.send_page(200, guide(self.headers.get("Remote-Groups", "").split(","), self.authorized()))
        elif self.path == "/dashboard/" and self.headers.get("Remote-User"):
            groups = set(self.headers.get("Remote-Groups", "").split(","))
            if self.authorized():
                self.send_response(303)
                self.send_header("Location", "/admin/")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            links = [f'<p><a href="/{key}">{title}</a></p>' for key, title in SERVICES.items() if key in groups]
            self.send_page(200, "<h1>Your dashboard</h1><h2>Personal tools</h2>" + ("".join(links) or "<p>No services assigned.</p>") + '<a href="/auth/logout">Sign out of dashboard</a>')
        elif urlsplit(self.path).path != BASE or not self.authorized():
            self.send_page(403, "Access denied")
        else:
            query = parse_qs(urlsplit(self.path).query)
            users = json.loads(DIRECTORY.read_text())["users"]
            saved = query.get("saved", [""])[0]
            notice = f'<p role="status" class="notice">Saved access for {esc(saved)}.</p>' if saved in users else ""
            self.send_page(200, create_form({}) if "new" in query else notice + page(users))

    def do_POST(self):
        if self.path != BASE or not self.authorized() or self.headers.get("Origin") != ORIGIN:
            return self.send_page(403, "Access denied")
        fields = {}
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192 or self.headers.get_content_type() != "application/x-www-form-urlencoded":
                raise ValueError("Invalid form.")
            fields = parse_qs(self.rfile.read(length).decode(), max_num_fields=10)
            password = update(DIRECTORY, fields)
        except ValueError as error:
            form = create_form(fields) if fields.get("action") == ["create"] else page(json.loads(DIRECTORY.read_text())["users"], fields.get("username", [""])[0])
            return self.send_page(400, f'<p role="alert" class="notice">{esc(str(error))}</p>' + form)
        if password:
            self.send_page(201, f'<h1>Account created</h1><section class="panel"><h2>{esc(fields["username"][0])}</h2><p>Copy this initial password now and give it to the account owner privately. It appears only once.</p><code>{esc(password)}</code></section><p><a href="{BASE}">Return to service access</a></p>')
        else:
            self.send_response(303)
            self.send_header("Location", BASE + "?saved=" + fields["username"][0])
            self.end_headers()


if __name__ == "__main__":
    os.umask(0o077)
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
