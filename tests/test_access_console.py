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
