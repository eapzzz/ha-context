"""End-to-end tests with synthetic HA data; no real devices or HA instance needed."""
import base64
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'ha_context.py'
TOKEN = 'SYNTHETIC_HA_ACCESS_TOKEN_123456789'
SECRET = 'SYNTHETIC_MQTT_SECRET_987654321'

class MockHA(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def reply(self, data, code=200):
        raw=json.dumps(data).encode(); self.send_response(code)
        self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw)))
        self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        self.server.audit.append(('GET',self.path))
        if self.path == '/api/websocket': return self.handle_ws()
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN: return self.reply({},401)
        states=[{'entity_id':'light.desk','state':'on','attributes':{'friendly_name':'Desk','supported_color_modes':['brightness'],'brightness':120}},
                {'entity_id':'automation.morning','state':'on','attributes':{'id':'12345'}},
                {'entity_id':'script.goodnight','state':'off','attributes':{}},
                {'entity_id':'sensor.phone_latitude','state':'50.1234567','attributes':{}},
                {'entity_id':'input_text.hidden','state':'HIDDEN_INPUT_VALUE','attributes':{'mode':'password'}}]
        values={'/api/':{'message':'API running.'},
                '/api/config':{'version':'test-fixture','time_zone':'Europe/Warsaw','config_dir':str(self.server.root),'latitude':50.1234567},
                '/api/states':states,
                '/api/events':[{'event':'state_changed','listener_count':10}],
                '/api/services':[{'domain':'lock','services':{'unlock':{'fields':{'code':{'name':'Code','selector':{'text':{}}}}}}}],
                '/api/config/automation/config/12345':{'id':'12345','actions':[{'action':'light.turn_on','target':{'entity_id':'light.desk'}}]},
                '/api/config/script/config/goodnight':{'sequence':[{'action':'light.turn_off','target':{'entity_id':'light.desk'}}]}}
        if self.path not in values: return self.reply({},404)
        return self.reply(values[self.path])
    def exact(self,count):
        raw=b''
        while len(raw)<count:
            chunk=self.rfile.read(count-len(raw))
            if not chunk: raise EOFError
            raw+=chunk
        return raw
    def frame_in(self):
        first,second=self.exact(2); length=second & 127
        if length==126:length=struct.unpack('!H',self.exact(2))[0]
        elif length==127:length=struct.unpack('!Q',self.exact(8))[0]
        mask=self.exact(4) if second&128 else None
        payload=self.exact(length)
        if mask:payload=bytes(v^mask[i%4] for i,v in enumerate(payload))
        return first&15,payload
    def frame_out(self, obj, opcode=1):
        raw=json.dumps(obj).encode() if opcode==1 else obj
        header=bytes([128|opcode])
        if len(raw)<126:header+=bytes([len(raw)])
        elif len(raw)<65536:header+=bytes([126])+struct.pack('!H',len(raw))
        else:header+=bytes([127])+struct.pack('!Q',len(raw))
        self.wfile.write(header+raw);self.wfile.flush()
    def handle_ws(self):
        key=self.headers['Sec-WebSocket-Key']
        accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        self.send_response(101);self.send_header('Upgrade','websocket');self.send_header('Connection','Upgrade')
        self.send_header('Sec-WebSocket-Accept',accept);self.end_headers()
        self.frame_out({'type':'auth_required','ha_version':'test-fixture'})
        try:
            _,raw=self.frame_in();msg=json.loads(raw)
            if msg.get('access_token')!=TOKEN:
                self.frame_out({'type':'auth_invalid'});return
            self.frame_out({'type':'auth_ok','ha_version':'test-fixture'})
            while True:
                opcode,raw=self.frame_in()
                if opcode==8:self.frame_out(raw,8);break
                if opcode==9:self.frame_out(raw,10);continue
                msg=json.loads(raw); typ=msg['type']; self.server.audit.append(('WS',typ))
                values={'config/entity_registry/list':[{'id':'entity-reg-1','entity_id':'light.desk','device_id':'dev1','platform':'test'},
                                                       {'id':'entity-reg-2','entity_id':'sensor.disabled','disabled_by':'user'}],
                        'config/device_registry/list':[{'id':'dev1','name':'Desk lamp','area_id':'bedroom','config_entry_id':'entry1'}],
                        'config/area_registry/list':[{'area_id':'bedroom','name':'Bedroom'}],
                        'config/floor_registry/list':[], 'config/label_registry/list':[],
                        'config/category_registry/list':[], 'config_entries/get':[{'entry_id':'entry1','domain':'test','title':'Test lamp'}],
                        'lovelace/dashboards/list':[], 'lovelace/config':{'views':[{'title':'Home'}]},
                        'device_automation/trigger/list':[{'platform':'device','device_id':'dev1','domain':'test','type':'pressed'}],
                        'device_automation/action/list':[], 'device_automation/condition/list':[],
                        'device_automation/trigger/capabilities':{'extra_fields':[]}}
                self.frame_out({'id':msg['id'],'type':'result','success':True,'result':values.get(typ,[])})
        except (EOFError,ConnectionError,BrokenPipeError):pass
        finally:self.close_connection=True
