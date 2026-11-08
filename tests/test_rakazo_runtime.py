import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("rakazo_runtime", Path(__file__).resolve().parents[1] / "deploy/rakazo/runtime_launcher.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

class RuntimePolicyTests(unittest.TestCase):
    def setUp(self):
        self.spec = {"linux": {"resources": {"memory": {"limit": 2147483648}, "cpu": {"quota": 100000, "period": 100000}, "pids": {"limit": 512}}}, "process": {"user": {"uid": 1000, "gid": 1000}, "noNewPrivileges": True, "capabilities": {}}}

    def test_requires_every_resource_ceiling(self):
        for resource in ("memory", "cpu", "pids"):
            with self.subTest(resource=resource):
                candidate = copy.deepcopy(self.spec)
                del candidate["linux"]["resources"][resource]
                with self.assertRaises(KeyError): runtime.limits(candidate)

    def test_rejects_unlimited_and_excessive_limits(self):
        for group, key, value in [("memory", "limit", -1), ("memory", "limit", 2147483649), ("cpu", "quota", -1), ("cpu", "quota", 100001), ("pids", "limit", -1), ("pids", "limit", 513)]:
            with self.subTest(group=group, value=value):
                candidate = copy.deepcopy(self.spec)
                candidate["linux"]["resources"][group][key] = value
                with self.assertRaises(ValueError): runtime.limits(candidate)

    def test_rejects_privileged_computers(self):
        for key, value in [("user", {"uid": 0, "gid": 0}), ("capabilities", {"effective": ["CAP_SYS_ADMIN"]}), ("noNewPrivileges", False)]:
            candidate = copy.deepcopy(self.spec)
            candidate["process"][key] = value
            with self.assertRaises(ValueError): runtime.limits(candidate)

    def test_denies_production_socket_and_arbitrary_host_mount(self):
        for source, target in [("/var/run/docker.sock", "/var/run/docker.sock"), ("/opt/portfolio/.secrets", "/home/rakazo"), ("/", "/host")]:
            with self.assertRaises(ValueError):
                runtime.validate_mounts({"mounts": [{"type": "bind", "source": source, "destination": target}]}, "a" * 64)

    def test_applies_group_oom_and_no_swap(self):
        result = runtime.limits(self.spec)
        self.assertEqual(result["memory.oom.group"], "1")
        self.assertEqual(result["memory.swap.max"], "0")

if __name__ == "__main__": unittest.main()
