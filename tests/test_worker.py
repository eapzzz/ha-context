import hashlib,json,threading,zipfile,http.server
from pathlib import Path
from hacontext.state import Store,Settings
from hacontext.worker import run_export,companion_index,rebuild_bundle,network_clean
from mock_ha import MockHA,TOKEN,SECRET


def test_full_export_against_real_mock_network(tmp_path):
    config=tmp_path/'ha';config.mkdir();(config/'.storage').mkdir()
    (config/'configuration.yaml').write_text('automation: !include automations.yaml\nmqtt:\n  password: '+SECRET+'\n')
    (config/'automations.yaml').write_text('[]')
    (config/'secrets.yaml').write_text('password: '+SECRET+'\n')
    (config/'.storage/auth').write_text('DO_NOT_READ_THIS_AUTH_FILE')
    (config/'scripts.yaml').write_text('{}')
    before={str(p):p.read_bytes() for p in config.rglob('*') if p.is_file()}
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),MockHA)
    server.root=config;server.audit=[]
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        store=Store(tmp_path/'app');store.initialize()
        cfg=Settings(url=f'http://127.0.0.1:{server.server_port}',source_mode='local',source_dir=str(config),timeout=2)
        store.save(cfg,TOKEN)
        root,summary=run_export(store)
        assert root in store.history()
        text=(root/'ha-context.txt').read_text()
        for token in (SECRET,TOKEN,'DO_NOT_READ_THIS_AUTH_FILE','50.1234567','HIDDEN_INPUT_VALUE'):
            assert token not in text
        for good in ('light.desk','sensor.disabled','Bedroom','Code','brightness'):assert good in text
        with zipfile.ZipFile(root/'ha-context.zip') as z:
            assert z.read('ha-context.txt').decode()==text
            for row in json.loads(z.read('manifest.json'))['files']:
                raw=z.read(row['path'])
                assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
        assert before=={str(p):p.read_bytes() for p in config.rglob('*') if p.is_file()}
        assert all(m in {'GET','WS'} for m,p in server.audit)
        assert all('call_service' not in p for m,p in server.audit)
    finally:server.shutdown();server.server_close()


def test_companion_registrations_not_merged_by_name():
    es=[{'entity_id':'sensor.phone','platform':'mobile_app','device_id':'old','disabled_by':'config_entry'},
        {'entity_id':'sensor.phone_2','platform':'mobile_app','device_id':'new','state':'unavailable'}]
    out=companion_index(es,[{'id':'old','name':'Phone','disabled_by':'config_entry'},{'id':'new','name':'Phone'}])
    assert len(out)==2
    assert out[0]['enabled']==[] and out[1]['enabled']==['sensor.phone_2']
    assert out[1]['unavailable']==['sensor.phone_2']


def test_network_privacy_preserves_ids():
    val={'entity_id':'sensor.phone_wi_fi_connection_2','state':'Private Home'}
    assert network_clean(val)['entity_id']==val['entity_id']
    assert network_clean(val)['state']=='[PRIVATE NETWORK]'
