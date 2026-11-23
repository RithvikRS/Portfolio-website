import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('controller_verifier',Path(__file__).parents[1]/'scripts/verify-rakazo-controller.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class BoundedHomeTests(unittest.TestCase):
    def check(self,family=True,wrong=False,cache_mounted=True,legacy_mounted=True):
        base=m.BASE;cache=base/'engine/cache';homes=base/'workspaces/homes';home=homes/'pilot-owner';image=Path('/srv/swarm/.rakazo-runtime-cache.img')
        mounts={str(cache):cache_mounted,str(homes):family,str(home):legacy_mounted}
        def stat(p,*a,**kw):
            inode=100 if p in [homes,cache/'family-homes'] else 200
            if wrong and p==home: inode=999
            return SimpleNamespace(st_dev=1,st_ino=inode,st_size=8*1024**3)
        with patch.object(m.os.path,'ismount',side_effect=lambda p:mounts.get(str(p),False)),patch.object(Path,'stat',stat),patch.object(Path,'resolve',lambda p:p),patch.object(m.subprocess,'check_output',side_effect=['/dev/loop9',str(image)]):
            m.verify_bounded_home()
    def test_family_parent_bind(self):self.check()
    def test_legacy_bind(self):self.check(family=False)
    def test_wrong_home_inode(self):
        with self.assertRaisesRegex(AssertionError,'bounded storage'):self.check(wrong=True)
    def test_missing_cache_mount(self):
        with self.assertRaisesRegex(AssertionError,'not mounted'):self.check(cache_mounted=False)
    def test_unmounted_legacy_home(self):
        with self.assertRaisesRegex(AssertionError,'not mounted'):self.check(family=False,legacy_mounted=False)
if __name__=='__main__':unittest.main()
