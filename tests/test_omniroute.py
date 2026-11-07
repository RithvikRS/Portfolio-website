import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class GatewayBoundaryTests(unittest.TestCase):
    def test_gateway_is_private_and_state_is_pinned(self):
        catalog = json.loads((ROOT / "deploy/swarm-services.json").read_text())
        app = catalog["services"]["omniroute"]
        edge = catalog["services"]["omniroute_sso"]
        self.assertNotIn("ports", app)
        self.assertEqual(app["environment"]["REQUIRE_API_KEY"], "true")
        self.assertEqual(app["environment"]["ENABLE_REQUEST_LOGS"], "false")
        self.assertNotIn("swarm_models_app", catalog["caddy_networks"])
        self.assertEqual(app["networks"], ["swarm_models_app"])
        self.assertIn("--allowed-group=admins", edge["command"])
        self.assertEqual([arg for arg in edge["command"] if arg.startswith("--allowed-group=")], ["--allowed-group=admins"])
        self.assertIn("node.id == tzqsl1t88r3l1i8zcqvcmredo", app["deploy"]["placement"]["constraints"])
        self.assertEqual(app["volumes"][0]["source"], "/srv/swarm/omniroute")
        self.assertEqual(app["deploy"]["update_config"]["order"], "stop-first")
        self.assertFalse(catalog["networks"]["swarm_models_app"]["attachable"])

    def test_model_link_is_not_granted_to_members(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("console_gateway_test", ROOT / "scripts/access-console.py")
        console = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(console)
        self.assertNotIn('/models', console.navigation(False, ['notes', 'vault'], '/dashboard/'))
        self.assertIn('/models', console.navigation(True, ['admins'], '/dashboard/'))

    def test_native_oidc_receives_verified_email_without_broadening_admission(self):
        config = (ROOT / "deploy/authelia/configuration.yml").read_text()
        policy = config.split("      omniroute_identity:", 1)[1].split("    authorization_policies:", 1)[0]
        self.assertIn("id_token: ['email', 'email_verified']", policy)
        client = config.split("      - client_id: 'portfolio-omniroute'", 1)[1].split("      - client_id:", 1)[0]
        self.assertIn("claims_policy: 'omniroute_identity'", client)
        self.assertIn("authorization_policy: 'infrastructure_admins'", client)
        self.assertIn("require_pkce: true", client)
        bootstrap = (ROOT / "scripts/bootstrap-omniroute.mjs").read_text()
        self.assertIn("oidcAllowedSubjects: ['rithvik.stuff@gmail.com']", bootstrap)
