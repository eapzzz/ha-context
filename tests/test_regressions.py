import json
from unittest.mock import patch
import pytest
from hacontext import engine


def test_short_secret_must_not_poison_sensor_numbers():
    r=engine.Redactor(); r.learn({'pin':'3'})
    assert r.clean({'pin':'3','state':'3'}) == {'pin':'[REDACTED]','state':'3'}


def test_storage_metadata_and_service_schemas_do_not_poison_ids():
    r=engine.Redactor()
    r.learn({'version':1,'key':'person','data':{}},storage_key='person')
    r.learn_yaml('play:\n  fields:\n    code:\n      description: spotifyplus\n',schema=True)
    assert r.text('person.alex') == 'person.alex'
    assert r.text('spotifyplus') == 'spotifyplus'


def test_volume_and_notification_count_are_not_content():
    for eid in ['sensor.phone_volume_level_notification_2','sensor.phone_active_notification_count']:
        o={'entity_id':eid,'state':'3','attributes':{'max':7}}
        r=engine.Redactor();r.learn(o)
        assert r.clean(o)==o


def test_ws_failure_latched_without_retry_storm():
    c=engine.HAClient('http://localhost:8123','synthetic-test-token')
    with patch.object(engine.websocket,'create_connection',side_effect=engine.websocket.WebSocketBadStatusException('bad',status_code=403)) as f:
        for _ in range(4):
            with pytest.raises(RuntimeError): c.ws_request('config/entity_registry/list')
        assert f.call_count == 1


def test_non_browser_client_does_not_invent_origin():
    c=engine.HAClient('http://localhost:8123','synthetic-test-token')
    with patch.object(engine.websocket,'create_connection') as f:
        f.return_value.recv.side_effect=['{"type":"auth_required"}','{"type":"auth_ok"}']
        c.connect()
        assert f.call_args.kwargs.get('suppress_origin') is True


def test_refuses_mutating_endpoints():
    c=engine.HAClient('http://localhost:8123','synthetic-test-token')
    with pytest.raises(ValueError): c.get('/api/services/light/turn_on')
    with pytest.raises(ValueError): c.ws_request('call_service')


def test_source_api_only_never_reads_local_config(tmp_path):
    from types import SimpleNamespace
    cfg=tmp_path/'configuration.yaml';cfg.write_text('sensitive: value')
    assert engine.select_source(SimpleNamespace(source_mode='api'),{'config_dir':str(tmp_path)},[]) is None
