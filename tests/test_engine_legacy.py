import importlib.util
import json
import pathlib
import tempfile
import unittest
import zipfile

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'app' / 'hacontext' / 'engine.py'

class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = None
        if SCRIPT.exists():
            spec = importlib.util.spec_from_file_location('ha_context', SCRIPT)
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)

    def module(self):
        self.assertIsNotNone(self.mod, 'ha_context.py implementation is missing')
        return self.mod

    def test_nested_secret(self):
        m = self.module(); r = m.Redactor(['TOPSECRET123'])
        data = r.clean({'device_id':'abc', 'password':'hello', 'x':['TOPSECRET123'], 'latitude':50.1})
        self.assertEqual(data['device_id'], 'abc')
        self.assertNotIn('TOPSECRET123', json.dumps(data))
        self.assertEqual(data['password'], '[REDACTED]')
        self.assertEqual(data['latitude'], '[REDACTED]')

    def test_urls_bearer_jwt(self):
        m = self.module(); r = m.Redactor([])
        text = 'http://user:pass@host:8123/a?token=abc123&x=4 Bearer abcdef123 /api/webhook/secretXYZ'
        text += ' eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklm'
        out = r.text(text)
        for word in ('user:pass', 'abc123','abcdef123','secretXYZ','eyJhbGci'):
            self.assertNotIn(word, out)
        self.assertIn('host:8123', out)

    def test_yaml_tags_and_multiline(self):
        m = self.module(); r = m.Redactor([])
        text = 'automation: !include automations.yaml\npassword: |\n  one\n  two\ntoken: !secret ha_token\naction:\n  - action: light.turn_on\n'
        out = r.yaml(text)
        self.assertIn('!include', out); self.assertIn('automations.yaml', out)
        self.assertIn('!secret', out); self.assertIn('ha_token', out)
        self.assertNotIn('one', out); self.assertIn('light.turn_on', out)

    def test_invalid_yaml_rejected(self):
        m = self.module()
        with self.assertRaises(Exception): m.Redactor([]).yaml('x: [broken')

    def test_yaml_flow_nested_secret(self):
        m = self.module()
        out = m.Redactor([]).yaml('mqtt: {username: me, password: hidden123}\n')
        self.assertNotIn('hidden123', out)

    def test_learned_secret_used_everywhere(self):
        m = self.module(); r = m.Redactor([])
        r.learn_yaml('foo: somePrivateValue777\n')
        self.assertNotIn('somePrivateValue777', r.text('payload somePrivateValue777'))

    def test_services_schema_preserved(self):
        m = self.module()
        out = m.Redactor([]).clean({'lock':{'unlock':{'fields':{'code':{'name':'Code','selector':{'text':{}}}}}}}, schema=True)
        self.assertIsInstance(out['lock']['unlock']['fields']['code'], dict)
        self.assertEqual(out['lock']['unlock']['fields']['code']['name'], 'Code')

    def test_private_state(self):
        m = self.module()
        r = m.Redactor([])
        out = r.clean({'entity_id':'input_text.safe', 'state':'123456', 'attributes':{'mode':'password'}})
        self.assertEqual(out['state'], '[REDACTED]')
        out = r.clean({'entity_id':'sensor.phone_geocoded_location','state':'Private address'})
        self.assertEqual(out['state'], '[REDACTED]')

    def test_collector_filters_auth_symlinks_and_secrets(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root/'configuration.yaml').write_text('automation: !include automations.yaml\n')
            (root/'automations.yaml').write_text('[]\n')
            (root/'secrets.yaml').write_text('secret: DO_NOT_EXPORT\n')
            (root/'.storage').mkdir()
            (root/'.storage/auth').write_text('DO_NOT_READ')
            (root/'link.yaml').symlink_to('/etc/passwd')
            data = m.collect_files(str(root), 10000, 100000)
            self.assertIn('configuration.yaml', data['files'])
            self.assertNotIn('secrets.yaml', data['files'])
            self.assertNotIn('.storage/auth', data['files'])
            self.assertNotIn('link.yaml', data['files'])
            self.assertTrue(data['secret_sources'])
            self.assertTrue(any(x['path']=='link.yaml' for x in data['skipped']))

    def test_config_entries_projection(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp); (root/'.storage').mkdir()
            raw={'data':{'entries':[{'entry_id':'a','domain':'mqtt','data':{'password':'secret'},'options':{'secret':'x'}},
                                    {'entry_id':'b','domain':'group','data':{'entities':['light.desk']},'options':{}}]}}
            (root/'.storage/core.config_entries').write_text(json.dumps(raw))
            data=m.collect_files(str(root),10000,100000)
            projected=json.loads(data['files']['.storage/core.config_entries']['text'])
            self.assertNotIn('secret',json.dumps(projected))
            self.assertIn('light.desk', json.dumps(projected))

    def test_file_size_recorded(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp); (root/'big.yaml').write_text('x'*100)
            data=m.collect_files(str(root),10,100)
            self.assertNotIn('big.yaml',data['files']); self.assertTrue(data['skipped'])

    def test_entity_join_with_disabled_entity(self):
        m = self.module()
        out = m.entity_index([{'entity_id':'light.desk','state':'on','attributes':{'friendly_name':'Desk'}}],
            [{'entity_id':'light.desk','device_id':'dev'}, {'entity_id':'sensor.disabled','disabled_by':'user'}],
            [{'id':'dev','area_id':'room'}], [{'area_id':'room','name':'Bedroom'}])
        byid={row['entity_id']:row for row in out}
        self.assertEqual(byid['light.desk']['effective_area_name'],'Bedroom')
        self.assertEqual(byid['sensor.disabled']['disabled_by'],'user')

    def test_url_validation(self):
        m=self.module()
        self.assertEqual(m.normalize_url('http://localhost:8123/'),'http://localhost:8123')
        for x in ('ftp://x','http://u:p@x','http://x/?token=123','file:///etc/passwd'):
            with self.assertRaises(ValueError): m.normalize_url(x)

    def test_write_operations_rejected(self):
        m=self.module(); client=m.HAClient('http://127.0.0.1:9','test',1)
        for path in ('/api/services/light/turn_on','/api/template','/api/error_log'):
            with self.assertRaises(ValueError): client.get(path)
        for typ in ('call_service','fire_event','config_entries/update'):
            with self.assertRaises(ValueError): client.ws_request(typ)

    def test_archive_text_and_modes(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            out=m.write_export(pathlib.Path(tmp), {'entities.json':'[{"entity_id":"light.desk"}]\n'}, {'version':'test'}, [])
            self.assertTrue((out/'ha-context.txt').exists())
            self.assertEqual((out/'ha-context.txt').stat().st_mode & 0o777,0o600)
            with zipfile.ZipFile(out/'ha-context.zip') as z:
                self.assertEqual(z.read('ha-context.txt'),(out/'ha-context.txt').read_bytes())
                self.assertIn('light.desk',z.read('entities.json').decode())

    def test_include_graph_marks_missing_files(self):
        m=self.module()
        files={'configuration.yaml':{'kind':'yaml','text':'automation: !include automations.yaml\nscript: !include missing.yaml\nx: !include_dir_merge_named packages\n'},
               'automations.yaml':{'kind':'yaml','text':'[]'},
               'packages/lights.yaml':{'kind':'yaml','text':'{}'}}
        refs=m.include_references(files)
        bytarget={x['target']:x for x in refs}
        self.assertEqual(bytarget['automations.yaml']['status'],'collected')
        self.assertEqual(bytarget['missing.yaml']['status'],'missing_or_excluded')
        self.assertEqual(bytarget['packages']['status'],'collected')

    def test_coordinate_sensor_state_redacted(self):
        m=self.module()
        out=m.Redactor([]).clean({'entity_id':'sensor.phone_latitude','state':'50.12345'})
        self.assertEqual(out['state'],'[REDACTED]')

    def test_installer_exists(self):
        self.assertTrue((SCRIPT.parents[2]/'install.sh').is_file())
        self.assertTrue((SCRIPT.parents[1]/'requirements.txt').is_file())

if __name__=='__main__': unittest.main()
