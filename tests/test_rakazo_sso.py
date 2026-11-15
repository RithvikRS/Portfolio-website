import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class RakazoSSOTests(unittest.TestCase):
    def test_gate_reuses_central_identity_and_limits_owner(self):
        c = json.loads((ROOT / 'deploy/swarm-services.json').read_text())
        edge = c['services']['rakazo_sso']
        args = edge['command']
        for value in ['--oidc-issuer-url=https://rithvik.ddns.net/auth',
                      '--authenticated-emails-file=/run/secrets/rakazo_owner_email',
                      '--allowed-group=admins', '--code-challenge-method=S256',
                      '--cookie-refresh=2m', '--session-store-type=redis',
                      '--cookie-name=__Host-rakazo_sso', '--upstream=static://202']:
            self.assertIn(value, args)
        self.assertFalse(any(v.startswith('--email-domain=') or v.startswith('--skip-auth') for v in args))
        for name in ['rakazo_sso', 'rakazo_sessions']:
            service = c['services'][name]
            self.assertNotIn('ports', service)
            self.assertTrue(service['read_only'])
            self.assertEqual(service['cap_drop'], ['ALL'])
            for network in service['networks']:
                self.assertTrue(c['networks'][network]['internal'])
        peers = {name for name,s in c['services'].items() if 'swarm_rakazo_sessions' in s.get('networks',[])}
        self.assertEqual(peers, {'rakazo_sso', 'rakazo_sessions'})
        auth = (ROOT / 'deploy/authelia/configuration.yml').read_text()
        client = auth.split("      - client_id: 'portfolio-rakazo-edge'",1)[1].split('      - client_id:',1)[0]
        self.assertIn("authorization_policy: 'rakazo_owner'", client)
        self.assertIn("require_pkce: true", client)

    def test_routing_checks_current_owner_before_app_and_renews_cookie(self):
        caddy = (ROOT / 'deploy/Caddyfile.swarm').read_text().split('rakazo.144.24.135.201.sslip.io {',1)[1]
        self.assertLess(caddy.index('request_header -X-Rakazo-Email'), caddy.index('rewrite /oauth2/auth?'))
        self.assertIn('include Set-Cookie', caddy)
        self.assertIn('request_header X-Rakazo-Email {rp.header.X-Auth-Request-Email}', caddy)
        self.assertLess(caddy.index('uri /internal/authorize-rakazo?'), caddy.index('reverse_proxy rakazo_api:3100'))
        self.assertIn('respond "Authentication required" 401', caddy)
        self.assertIn('redir / /app 302', caddy)
        self.assertNotIn('authelia_url=https://rakazo.', caddy)
