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
        self.assertIn("--cookie-csrf-per-request=true", edge["command"])
        self.assertIn("--cookie-csrf-per-request-limit=8", edge["command"])
        self.assertIn("--code-challenge-method=S256", edge["command"])
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

    def test_renewal_remains_private_and_rechecks_admin_groups(self):
        catalog = json.loads((ROOT / "deploy/swarm-services.json").read_text())
        services = catalog["services"]
        args = services["omniroute_sso"]["command"]
        for option in ["--cookie-refresh=2m", "--cookie-expire=30m", "--session-store-type=redis", "--allowed-group=admins"]:
            self.assertIn(option, args)
        self.assertNotIn("--session-cookie-minimal=true", args)
        peers = {name for name, service in services.items() if "swarm_models_sessions" in service.get("networks", [])}
        self.assertEqual(peers, {"omniroute_sessions", "omniroute_sso"})
        self.assertNotIn("ports", services["omniroute_sessions"])
        self.assertTrue(all(v["type"] == "tmpfs" for v in services["omniroute_sessions"]["volumes"]))
        self.assertNotIn("swarm_models_sessions", catalog["caddy_networks"])
        self.assertTrue(catalog["networks"]["swarm_models_sessions"]["internal"])
        auth = (ROOT / "deploy/authelia/configuration.yml").read_text()
        client = auth.split("      - client_id: 'portfolio-omniroute-edge'", 1)[1].split("      - client_id:", 1)[0]
        self.assertIn("grant_types: ['authorization_code', 'refresh_token']", client)
        self.assertIn("authorization_policy: 'infrastructure_admins'", client)
        self.assertIn("require_pkce: true", client)
        self.assertIn("claims_policy: 'omniroute_edge_identity'", client)
