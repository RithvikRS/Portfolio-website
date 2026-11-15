import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("rakazo_build", Path(__file__).resolve().parents[1]/"scripts/build-rakazo-app.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class RakazoBuildTests(unittest.TestCase):
    def test_compilation_has_fixed_resource_and_network_boundaries(self):
        args = build.container_args("test-build")
        for key, value in {"--network":"none", "--memory":"3g", "--memory-swap":"3g",
                           "--cpus":"2", "--pids-limit":"512", "--cap-drop":"ALL",
                           "--security-opt":"no-new-privileges"}.items():
            self.assertEqual(args[args.index(key)+1], value)
        self.assertFalse({"--privileged", "--volume", "-v", "--mount", "--env-file"} & set(args))
        self.assertEqual(args[args.index("--tmpfs")+1],
                         "/app/apps/web/node_modules/.vite-temp:rw,noexec,nosuid,nodev,size=67108864,mode=0700,uid=0,gid=0")
        self.assertIn(build.BASE_IMAGE, args)

    def test_patch_is_limited_to_compiled_application_sources(self):
        build.validate_patch(b"--- a/apps/api/src/app.ts\n+++ b/apps/api/src/app.ts\n")
        build.validate_patch(b"--- /dev/null\n+++ b/packages/contracts/src/new.ts\n")
        for patch in [
            b"--- a/package.json\n+++ b/package.json\n",
            b"--- a/apps/api/src/app.ts\n+++ /dev/null\n",
            b"--- a/apps/api/src/../../bad\n+++ b/apps/api/src/../../bad\n",
            b"GIT binary patch\n",
        ]:
            with self.assertRaises(RuntimeError):
                build.validate_patch(patch)

    def test_commit_restores_nonroot_production_and_failclosed_defaults(self):
        args = build.commit_args("bounded-compiler", "derived:test", "a"*64)
        self.assertEqual(args[0], "commit")
        self.assertEqual(args[-2:], ["bounded-compiler", "derived:test"])
        for change in [
            "USER node", "WORKDIR /app",
            'CMD ["pnpm", "--filter", "@rakazo/api", "start"]',
            'ENV NODE_ENV=production CI="" NODE_OPTIONS="" RAYON_NUM_THREADS=2',
            'ENV WORKSPACE_ONLY=true SANDBOX_PROVIDER=none CLOUD_AGENT_PROVIDER=none AUTH_PASSWORD_ENABLED=false USER_DEVICES_ENABLED=false',
        ]:
            self.assertIn(change, args)
        self.assertNotIn("build", args)
        self.assertIn("NODE_ENV=test pnpm exec vitest", build.BUILD_COMMAND)

    def test_tag_provenance_changes_with_any_build_input(self):
        a, record = build.input_fingerprint({"z":b"one", "a":b"two"})
        b, _ = build.input_fingerprint({"a":b"two", "z":b"one"})
        c, _ = build.input_fingerprint({"a":b"changed", "z":b"one"})
        self.assertEqual(a,b)
        self.assertNotEqual(a,c)
        self.assertEqual(record["source"],build.UPSTREAM_SHA)


if __name__ == "__main__":
    unittest.main()
