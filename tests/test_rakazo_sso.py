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
                      '--email-domain=*', '--allowed-group=rakazo',
                      '--allowed-group=admins', '--code-challenge-method=S256',
                      '--cookie-refresh=2m', '--session-store-type=redis',
                      '--cookie-name=__Host-rakazo_sso', '--upstream=static://202']:
            self.assertIn(value, args)
        self.assertFalse(any(v.startswith('--authenticated-emails-file=') or v.startswith('--skip-auth') for v in args))
        for name in ['rakazo_api', 'rakazo_assistant']:
            self.assertEqual(c['services'][name]['environment']['MULTI_USER_ASSISTANT'], 'true')
        for name in ['rakazo_sso', 'rakazo_sessions']:
            service = c['services'][name]
            self.assertNotIn('ports', service)
            self.assertTrue(service['read_only'])
            self.assertEqual(service['cap_drop'], ['ALL'])
            for network in service['networks']:
                self.assertTrue(c['networks'][network]['internal'])
        peers = {name for name,s in c['services'].items() if 'swarm_rakazo_sessions' in s.get('networks',[])}
        self.assertEqual(peers, {'rakazo_sso', 'rakazo_sessions'})
        identity_peers = {name for name,service in c['services'].items() if 'swarm_rakazo_identity' in service.get('networks', [])}
        self.assertEqual(identity_peers, {'rakazo_api', 'access_console'})
        self.assertTrue(c['networks']['swarm_rakazo_identity']['internal'])
        auth = (ROOT / 'deploy/authelia/configuration.yml').read_text()
        client = auth.split("      - client_id: 'portfolio-rakazo-edge'",1)[1].split('      - client_id:',1)[0]
        self.assertIn("authorization_policy: 'rakazo_members'", client)
        self.assertIn("require_pkce: true", client)

    def test_transient_discovery_failure_retries_but_release_still_requires_readiness(self):
        c = json.loads((ROOT / 'deploy/swarm-services.json').read_text())
        policy = c['services']['rakazo_sso']['deploy']['update_config']
        self.assertEqual(policy, {'parallelism': 1, 'order': 'stop-first',
                                  'failure_action': 'continue', 'monitor': '45s'})
        self.assertIn('http://rakazo_sso:4180/ready', c['internal_checks'])
        self.assertTrue(any(check['url'] == 'https://rakazo.144.24.135.201.sslip.io/'
                            for check in c['http_checks']))

    def test_routing_checks_current_owner_before_app_and_renews_cookie(self):
        caddy = (ROOT / 'deploy/Caddyfile.swarm').read_text().split('rakazo.144.24.135.201.sslip.io {',1)[1]
        self.assertLess(caddy.index('request_header -X-Rakazo-Email'), caddy.index('rewrite /oauth2/auth?'))
        self.assertIn('include Set-Cookie', caddy)
        self.assertIn('request_header X-Rakazo-Email {rp.header.X-Auth-Request-Email}', caddy)
        self.assertLess(caddy.index('uri /internal/authorize-rakazo?'), caddy.index('reverse_proxy rakazo_api:3100'))
        self.assertIn('respond "Authentication required" 401', caddy)
        self.assertIn('redir / /app 302', caddy)
        self.assertNotIn('authelia_url=https://rakazo.', caddy)

    def test_desktop_receives_identity_only_after_current_owner_check(self):
        caddy = (ROOT / 'deploy/Caddyfile.swarm').read_text()
        gate = caddy.split('rakazo.144.24.135.201.sslip.io {', 1)[1]
        self.assertIn('import private_identity', gate)
        self.assertIn('request_header -Remote-User', caddy)
        self.assertIn('request_header -Remote-Groups', caddy)
        desktop = gate.split('handle_path /computer/* {', 1)[1].split('}', 1)[0]
        for header in ['request_header Remote-User rithvik', 'request_header Remote-Groups admins']:
            self.assertIn(header, desktop)
            self.assertLess(gate.index('uri /internal/authorize-rakazo-owner?'), gate.index(header))
        self.assertIn('@ownerDesktop path /computer /computer/*', gate)
        self.assertIn('forward_auth @ownerDesktop access_console:8080', gate)
        self.assertLess(desktop.index('request_header Remote-Groups admins'), desktop.index('reverse_proxy rakazo_pilot:8080'))
