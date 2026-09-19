import json,os,stat,subprocess,sys,zipfile
from pathlib import Path
from unittest.mock import patch
import pytest
from hacontext.engine import Redactor,collect_files
from hacontext.state import Store,source_archive,legacy_candidates,remove_legacy


def test_notification_contents_are_not_left_in_attributes():
    value={'entity_id':'sensor.phone_last_notification','state':'Private text here',
           'attributes':{'friendly_name':'Last notification','android.text':'SECRET_MESSAGE_TEXT','post_time':12345}}
    cleaned=Redactor().clean(value)
    assert 'SECRET_MESSAGE_TEXT' not in json.dumps(cleaned)
    assert cleaned['attributes']['friendly_name']=='Last notification'


def test_notification_permission_is_telemetry_not_content():
    value={'entity_id':'binary_sensor.phone_notification_permission','state':'on','attributes':{}}
    assert Redactor().clean(value)==value


def test_config_fifo_is_not_read(tmp_path):
    os.mkfifo(tmp_path/'broken.yaml')
    code='from hacontext.engine import collect_files;import sys;print(collect_files(sys.argv[1],1024,4096))'
    r=subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True,timeout=2,
                     env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'app')})
    assert r.returncode==0 and 'non-regular file' in r.stdout


def test_source_sharing_rejects_symlinked_parent_even_inside_install(tmp_path):
    store=Store(tmp_path/'tool');store.initialize()
    (store.local/'secret.py').write_text('PRIVATE_VALUE')
    (store.root/'app').symlink_to(store.local,target_is_directory=True)
    (store.root/'project-files.json').write_text(json.dumps({'files':['app/secret.py']}))
    with pytest.raises(ValueError):source_archive(store.root,tmp_path/'share.zip')


def test_uninstall_keeps_other_directories(tmp_path):
    store=Store(tmp_path/'tool');store.initialize()
    other=tmp_path/'ha';other.mkdir();(other/'configuration.yaml').write_text('kept')
    store.uninstall()
    assert not store.root.exists() and (other/'configuration.yaml').read_text()=='kept'


def test_legacy_standalone_script_is_detected_and_removed(tmp_path):
    p=tmp_path/'ha_context.py';p.write_text('"""Read-only Home Assistant context exporter."""\nVERSION = \'1.0.1\'\n')
    current=tmp_path/'new'
    assert p in legacy_candidates(tmp_path,current)
    remove_legacy(p,tmp_path,current)
    assert not p.exists()


def test_integration_metadata_discards_opaque_options():
    from hacontext.engine import integration_metadata
    data=[{'entry_id':'one','domain':'custom','title':'Device',
           'data':{'opaque':'DO_NOT_PUBLISH'},'options':{'opaque':'DO_NOT_PUBLISH'}}]
    assert integration_metadata(data)==[{'entry_id':'one','domain':'custom','title':'Device'}]


def test_invalid_new_token_does_not_change_saved_settings(tmp_path):
    from hacontext.state import Settings
    store=Store(tmp_path/'tool');store.initialize()
    store.save(Settings(url='http://127.0.0.1:8123'), 'good-token')
    before=store.config.read_bytes()
    with pytest.raises(ValueError):store.save(Settings(url='http://other.local:8123'),'bad\ntoken')
    assert store.config.read_bytes()==before
