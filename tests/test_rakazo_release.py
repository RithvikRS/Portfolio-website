import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('release_verify',ROOT/'scripts/verify-rakazo-release.py')
release=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(release)
HAS_CRYPTO=importlib.util.find_spec('cryptography') is not None


class ReleaseSafetyTests(unittest.TestCase):
    def test_ownership_guard_rejects_foreign_resources(self):
        state={'prefix':'rakazo-release-test'}
        for kind,info in [('container',{'Config':{'Labels':{release.LABEL:'another'}}}),('volume',{'Labels':{}}),('network',{})]:
            with patch.object(release.docker,'call',return_value=json.dumps([info])) as call:
                with self.assertRaises(RuntimeError):release.owned(state,kind,'foreign-id')
                self.assertEqual(call.call_count,1)
                self.assertEqual(call.call_args.args,(kind,'inspect','foreign-id'))

    def test_remove_never_deletes_an_unowned_container(self):
        state={'prefix':'rakazo-release-test','containers':{'api':'production-container'}}
        with patch.object(release.docker,'call',return_value='[{"Config":{"Labels":{}}}]') as call:
            with self.assertRaises(RuntimeError):release.remove(state,'api')
            self.assertTrue(all(args.args[0]!='rm' for args in call.call_args_list))
        self.assertIn('api',state['containers'])

    def test_state_path_refuses_repository_and_arbitrary_files_before_docker(self):
        for path in [str(ROOT/'state.json'),'/tmp/state.json','/opt/portfolio/state.json']:
            with patch.object(release.docker,'call') as call:
                with self.assertRaises(RuntimeError):release.load(path)
                call.assert_not_called()

    @unittest.skipUnless(HAS_CRYPTO,'cryptography is required only for the remote encrypted rehearsal')
    def test_encrypted_backup_roundtrip_and_tamper_rejection(self):
        from cryptography.exceptions import InvalidTag
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);backup=root/'backup';backup.mkdir()
            state={'directory':directory,'database':'rakazo_workspace_verify_test','owner_password':'synthetic-owner',
                   'app_password':'synthetic-app','database_url':'postgres://test','owner_url':'postgres://owner','image':'sha256:'+'a'*64}
            for name,value in [('database.dump',b'database fixture'),('secrets',b'secret fixture'),('data',b'file fixture')]:
                (backup/name).write_bytes(value)
            release.seal_backup(state,backup)
            self.assertEqual({p.name for p in backup.iterdir()},{'archive.aesgcm'})
            self.assertNotIn(b'secret fixture',(backup/'archive.aesgcm').read_bytes())
            destination=release.open_backup(state,backup)
            self.assertEqual((destination/'data').read_bytes(),b'file fixture')
            self.assertEqual((destination/'secrets').read_bytes(),b'secret fixture')
            payload=(backup/'archive.aesgcm').read_bytes()
            (backup/'archive.aesgcm').write_bytes(payload[:-1]+bytes([payload[-1]^1]))
            with self.assertRaises(InvalidTag):release.open_backup(state,backup)


if __name__=='__main__':unittest.main()
