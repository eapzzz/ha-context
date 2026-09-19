import json, os
from pathlib import Path
import pytest
from hacontext.state import Store, Settings, legacy_candidates, remove_legacy, validate_install_root, compare_exports, grouped_issues, choose_endpoint


def test_private_settings_roundtrip(tmp_path):
    s=Store(tmp_path/'app');s.initialize()
    s.save(Settings(url='http://localhost:8123'), 'synthetic-long-test-token')
    assert s.load().url=='http://localhost:8123'
    assert s.token()=='synthetic-long-test-token'
    assert s.config.stat().st_mode&0o777==0o600
    assert s.local.stat().st_mode&0o777==0o700
    assert 'synthetic' not in s.config.read_text()


def test_reset_keeps_exports_notes_and_code(tmp_path):
    s=Store(tmp_path/'app');s.initialize();s.save(Settings(),'test-token-long')
    (s.exports/'keep.txt').write_text('keep');s.notes.write_text('physical room notes')
    (s.root/'keep.py').write_text('code')
    s.reset()
    assert not s.config.exists() and not (s.local/'token').exists()
    assert (s.exports/'keep.txt').exists() and s.notes.exists() and (s.root/'keep.py').exists()


def test_symlink_local_rejected(tmp_path):
    root=tmp_path/'app';root.mkdir();outside=tmp_path/'outside';outside.mkdir()
    (root/'local').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError): Store(root).initialize()


def test_home_or_ha_root_rejected(tmp_path):
    with pytest.raises(ValueError): validate_install_root(Path.home())
    root=tmp_path/'ha';root.mkdir();(root/'configuration.yaml').write_text('')
    with pytest.raises(ValueError): validate_install_root(root)
    with pytest.raises(ValueError): validate_install_root(root/'app')


def test_legacy_empty_nothing_to_show(tmp_path):
    assert legacy_candidates(tmp_path,tmp_path/'new')==[]
    (tmp_path/'ha-context-exports').mkdir()
    assert legacy_candidates(tmp_path,tmp_path/'new')==[]


def test_legacy_identity_not_name_and_safe_delete(tmp_path):
    root=tmp_path/'new';root.mkdir()
    old=tmp_path/'.config/ha-context';old.mkdir(parents=True)
    (old/'connection.json').write_text(json.dumps({'url':'http://localhost:8123','token':'synthetic-token'}))
    paths=legacy_candidates(tmp_path,root)
    assert old in paths
    remove_legacy(old,tmp_path,root)
    assert not old.exists() and root.exists()
    with pytest.raises(ValueError): remove_legacy(tmp_path,tmp_path,root)


def test_legacy_symlink_targets_never_removed(tmp_path):
    outside=tmp_path/'outside';outside.mkdir();(outside/'keep').write_text('x')
    p=tmp_path/'.config';p.mkdir();(p/'ha-context').symlink_to(outside,target_is_directory=True)
    assert legacy_candidates(tmp_path,tmp_path/'new')==[]
    assert (outside/'keep').exists()


def test_grouping_same_cause():
    groups=grouped_issues([{'section':s,'reason':'WebSocket HTTP 403'} for s in ['entities','devices']])
    assert len(groups)==1 and len(groups[0]['sections'])==2


def test_diff_ignores_live_readings():
    a=[{'entity_id':'sensor.test','state':'1','attributes':{'friendly_name':'Test'}}]
    b=[{'entity_id':'sensor.test','state':'2','attributes':{'friendly_name':'Test'}}]
    assert compare_exports(a,b)['changed']==[]
    b[0]['disabled_by']='user'
    assert compare_exports(a,b)['changed']==['sensor.test']


def test_endpoint_from_selected_container_not_any_network():
    row={'ports':{'8123/tcp':[{'HostIp':'0.0.0.0','HostPort':'8124'}]},'networks':{'bridge':{'IPAddress':'172.18.0.7'}}}
    assert choose_endpoint(row)=='http://127.0.0.1:8124'
    row['ports']={}
    assert choose_endpoint(row)=='http://172.18.0.7:8123'
