import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("access_console", Path(__file__).resolve().parents[1] / "scripts/access-console.py")
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)


class AccessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name) / "users.yml"
        self.owner = dict(displayname="Owner", email="owner@example.org", groups=["admins"], password="existing")
        self.directory.write_text(json.dumps({"users": {"rithvik": self.owner}}))

    def apply(self, **params):
        return console.update(self.directory, {k: v if isinstance(v, list) else [v] for k,v in params.items()})

    def create(self, name, grant):
        return self.apply(action="create", username=name, name=name, email=name+"@example.org", services=[grant])

    def users(self):
        return json.loads(self.directory.read_text())["users"]

    def test_isolate_users_and_revoke_one_grant(self):
        first = self.create("one", "notes")
        second = self.create("two", "vault")
        users = self.users()
        self.assertNotEqual(first, second)
        self.assertNotIn(first, self.directory.read_text())
        self.assertEqual(users["one"]["groups"], ["notes"])
        self.assertEqual(users["two"]["groups"], ["vault"])
        self.apply(action="save", username="one", disabled="on")
        self.assertTrue(self.users()["one"]["disabled"])
        self.assertEqual(self.users()["one"]["groups"], [])
        self.assertEqual(self.users()["two"], users["two"])
        self.assertEqual(self.users()["rithvik"], self.owner)

    def test_forbid_privilege_escalation_and_owner_edits(self):
        before = self.directory.read_bytes()
        for name, grant in [("one", "admins"), ("rithvik", "notes")]:
            with self.assertRaises(ValueError):
                self.create(name, grant)
        self.assertEqual(self.directory.read_bytes(), before)

    def test_forbid_duplicate_identity(self):
        with self.assertRaises(ValueError):
            self.apply(action="create",username="shadow",name="Shadow",email="Owner@EXAMPLE.org")
        self.assertEqual(list(self.users()), ["rithvik"])

    def test_model_authorization_uses_current_enabled_admin(self):
        self.assertTrue(console.model_admin_allowed(self.directory, "OWNER@example.org"))
        for email in ["", "missing@example.org", "owner@example.org,attacker@example.org"]:
            self.assertFalse(console.model_admin_allowed(self.directory, email))
        for changes in [{"groups": []}, {"groups": ["notes"]}, {"disabled": True}]:
            record = {**self.owner, **changes}
            self.directory.write_text(json.dumps({"users": {"rithvik": record}}))
            self.assertFalse(console.model_admin_allowed(self.directory, "owner@example.org"))
        self.directory.write_text(json.dumps({"users": {"a": self.owner, "b": self.owner}}))
        self.assertFalse(console.model_admin_allowed(self.directory, "owner@example.org"))
        for content in ['{}', 'invalid', '{"users": {}}']:
            self.directory.write_text(content)
            self.assertFalse(console.model_admin_allowed(self.directory, "owner@example.org"))

    def test_rakazo_requires_unique_enabled_owner_not_another_admin(self):
        self.assertTrue(console.rakazo_owner_allowed(self.directory, 'OWNER@example.org'))
        self.directory.write_text(json.dumps({'users': {'rithvik': self.owner,
            'other': {**self.owner, 'email': 'other@example.org'}}}))
        self.assertFalse(console.rakazo_owner_allowed(self.directory, 'other@example.org'))
        for changes in [{'groups': []}, {'disabled': True}, {'email': 'changed@example.org'}]:
            self.directory.write_text(json.dumps({'users': {'rithvik': {**self.owner, **changes}}}))
            self.assertFalse(console.rakazo_owner_allowed(self.directory, 'owner@example.org'))
        for users in [{'other': self.owner}, {'rithvik': self.owner, 'duplicate': self.owner}]:
            self.directory.write_text(json.dumps({'users': users}))
            self.assertFalse(console.rakazo_owner_allowed(self.directory, 'owner@example.org'))
        self.directory.write_text('invalid')
        self.assertFalse(console.rakazo_owner_allowed(self.directory, 'owner@example.org'))


    def test_rakazo_grant_admission_and_immediate_revocation(self):
        self.create("member", "rakazo")
        self.assertTrue(console.rakazo_member_allowed(self.directory, "MEMBER@example.org"))
        self.assertTrue(console.rakazo_member_allowed(self.directory, "owner@example.org"))
        self.assertFalse(console.rakazo_owner_allowed(self.directory, "member@example.org"))
        self.assertFalse(console.model_admin_allowed(self.directory, "member@example.org"))
        self.apply(action="save", username="member", services=["notes"])
        self.assertFalse(console.rakazo_member_allowed(self.directory, "member@example.org"))
        self.apply(action="save", username="member", services=["rakazo"], disabled="on")
        self.assertFalse(console.rakazo_member_allowed(self.directory, "member@example.org"))
        self.apply(action="save", username="member", services=["rakazo"])
        self.assertTrue(console.rakazo_member_allowed(self.directory, "member@example.org"))

    def test_rakazo_rejects_duplicate_malformed_and_ungranted_identities(self):
        member = {**self.owner, "email": "member@example.org", "groups": ["rakazo"]}
        for email in ["", "missing@example.org", "member@example.org,owner@example.org", "x" * 255]:
            self.assertFalse(console.rakazo_member_allowed(self.directory, email))
        for extra in [{"groups": []}, {"groups": ["admins"]}, {"groups": "rakazo"}, {"disabled": True}]:
            self.directory.write_text(json.dumps({"users": {"rithvik": self.owner, "member": {**member, **extra}}}))
            self.assertFalse(console.rakazo_member_allowed(self.directory, "member@example.org"))
        self.directory.write_text(json.dumps({"users": {"one": member, "two": {**member, "email": "MEMBER@example.org"}}}))
        self.assertFalse(console.rakazo_member_allowed(self.directory, "member@example.org"))
        for content in ["invalid", "{}", '{"users": null}', '{"users": {"member": null}}']:
            self.directory.write_text(content)
            self.assertFalse(console.rakazo_member_allowed(self.directory, "member@example.org"))

    def test_rakazo_grant_navigation_and_guide(self):
        granted = console.navigation(False, ["rakazo"], "/dashboard/")
        denied = console.navigation(False, ["notes"], "/dashboard/")
        self.assertIn('href="/rakazo"', granted)
        self.assertNotIn('href="/rakazo"', denied)
        self.assertNotIn('href="/models"', granted)
        self.assertEqual(console.navigation(True, ["admins"], "/admin/").count('href="/rakazo"'), 2)
        self.assertIn('value="rakazo"', console.checks([]))
        self.assertIn('href="/rakazo"', console.guide(["rakazo"], False))
        self.assertNotIn('href="/rakazo"', console.guide([], False))
        self.assertIn("each person will connect", console.guide(["rakazo"], False))

    def test_rakazo_http_member_and_owner_checks_remain_separate(self):
        import http.client
        import threading
        self.create("member", "rakazo")
        server = console.HTTPServer(("127.0.0.1", 0), console.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.object(console, "DIRECTORY", self.directory):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                try:
                    for path, email, status in [
                        ("/internal/authorize-rakazo", "member@example.org", 204),
                        ("/internal/authorize-rakazo-owner", "member@example.org", 403),
                        ("/internal/authorize-rakazo-owner", "owner@example.org", 204),
                        ("/internal/authorize-rakazo", "missing@example.org", 403),
                    ]:
                        connection.request("GET", path, headers={"X-Rakazo-Email": email})
                        response = connection.getresponse()
                        self.assertEqual(response.status, status)
                        self.assertEqual(response.getheader("Cache-Control"), "no-store")
                        response.read()
                    self.apply(action="save", username="member", services=[])
                    connection.request("GET", "/internal/authorize-rakazo", headers={"X-Rakazo-Email": "member@example.org"})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 403)
                    response.read()
                finally:
                    connection.close()
        finally:
            server.shutdown()
            worker.join(timeout=2)
            server.server_close()
