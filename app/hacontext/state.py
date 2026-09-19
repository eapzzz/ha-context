"""Private application state, discovery and explicitly confirmed maintenance.

This module never edits Home Assistant. Every delete is bounded by tool ownership.
"""
from __future__ import annotations
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile
from typing import Any
from . import engine

PROJECT_MARKER = 'ha-context-project:2'
INSTALL_MARKER = '.ha-context-install.json'


def safe_text(value: object) -> str:
    """Strip terminal control sequences from untrusted names and error strings."""
    text = str(value)
    text = re.sub(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))', '', text)
    return ''.join(c for c in text if c in '\n\t' or (ord(c) >= 32 and not 127 <= ord(c) < 160))


def validate_install_root(root: Path) -> Path:
    root = root.expanduser()
    if root.is_symlink():
        raise ValueError('The installation folder must not be a symbolic link.')
    path = root.resolve()
    forbidden = {Path('/'), Path.home().resolve(), Path('/etc'), Path('/usr'),
                 Path('/opt'), Path('/var'), Path('/config'), Path('/homeassistant'), Path('/data')}
    if path in forbidden:
        raise ValueError('Choose a dedicated ha-context folder, not a system or home folder.')
    for parent in (path, *path.parents):
        if (parent / 'configuration.yaml').exists():
            raise ValueError('ha-context must be installed OUTSIDE Home Assistant configuration.')
    return path


def private_replace(path: Path, text: str) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Refusing to write through a symbolic link.')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.writing-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@dataclasses.dataclass
class Settings:
    url: str = ''
    source_mode: str = 'api'
    source_dir: str = ''
    container: str = ''
    runtime: str = 'docker'
    docker_sudo: bool = False
    auto_url: bool = False
    supervisor: bool = False
    network_privacy: bool = False
    device_details: bool = True
    timeout: int = 10
    retention: int = 5
    label: str = 'Home Assistant'

    def validate(self) -> None:
        if not self.supervisor:
            engine.normalize_url(self.url)
        if self.source_mode not in {'api', 'local', 'container'}:
            raise ValueError('Select API only, a local folder, or a container.')
        if self.runtime not in {'docker', 'podman'}:
            raise ValueError('Unsupported container runtime.')
        if self.source_mode == 'container' and not self.container:
            raise ValueError('Select a Home Assistant container first.')
        if self.source_mode == 'local' and not self.source_dir:
            raise ValueError('Select the configuration folder first.')
        if not isinstance(self.timeout, int) or not 2 <= self.timeout <= 60:
            raise ValueError('Connection timeout must be between 2 and 60 seconds.')
        if not isinstance(self.retention, int) or not 0 <= self.retention <= 100:
            raise ValueError('Keep between 1 and 100 exports, or 0 to keep all.')
        if self.supervisor and os.environ.get('HA_CONTEXT_ADDON') != '1':
            raise ValueError('Automatic Supervisor authentication works inside the HA OS app only.')


class Store:
    def __init__(self, root: Path, *, addon: bool | None = None):
        self.root = root.expanduser().absolute()
        self.addon = os.environ.get('HA_CONTEXT_ADDON') == '1' if addon is None else addon
        self.local = Path('/data/local') if self.addon else self.root / 'local'
        self.config = self.local / 'config.json'
        self.notes = self.local / 'notes.md'
        self.annotations = self.local / 'annotations.json'
        self.exports = self.local / 'exports'
        self.logs = self.local / 'logs'

    def initialize(self) -> None:
        if not self.addon:
            validate_install_root(self.root)
        if self.local.is_symlink():
            raise ValueError('Private data folder must not be a symbolic link.')
        self.local.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.local.chmod(0o700)
        for path in (self.exports, self.logs):
            if path.is_symlink():
                raise ValueError('Private subfolders must not be symbolic links.')
            path.mkdir(mode=0o700, exist_ok=True)
            path.chmod(0o700)
        if not self.addon:
            marker = self.root / INSTALL_MARKER
            if not marker.exists():
                private_replace(marker, json.dumps({'tool':'ha-context', 'root':str(self.root.resolve())}))

    def load(self) -> Settings | None:
        if not self.config.exists():
            return None
        if self.config.is_symlink() or self.config.stat().st_size > 65536:
            raise ValueError('Unsafe configuration file. Review it using Maintenance.')
        try:
            data = json.loads(self.config.read_text())
            fields = {f.name for f in dataclasses.fields(Settings)}
            return Settings(**{k:v for k,v in data.items() if k in fields})
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError('Saved settings are invalid. Reset settings to run onboarding again.') from exc

    def token(self) -> str:
        cfg = self.load()
        if cfg and cfg.supervisor:
            value = os.environ.get('SUPERVISOR_TOKEN', '')
        else:
            path = self.local/'token'
            if path.is_symlink():
                raise ValueError('Refusing to read token from a symbolic link.')
            value = path.read_text().strip() if path.exists() else ''
        if not value:
            raise ValueError('No access token. Open Connection settings.')
        return value

    def save(self, settings: Settings, token: str | None = None) -> None:
        if token is not None and not settings.supervisor:
            if not token.strip() or '\n' in token.strip() or '\r' in token.strip():
                raise ValueError('Paste a single non-empty token.')
        self.initialize()
        private_replace(self.config, json.dumps(dataclasses.asdict(settings), indent=2)+'\n')
        if token is not None and not settings.supervisor:
            private_replace(self.local/'token', token.strip()+'\n')
        if settings.supervisor and (self.local/'token').exists():
            (self.local/'token').unlink()
        if not self.notes.exists():
            private_replace(self.notes, '')

    def load_annotations(self) -> list[dict[str, str]]:
        """Read only the tool's typed context notes, never HA configuration."""
        path=self.annotations
        if not path.exists() and not path.is_symlink():
            return []
        if path.is_symlink() or path.stat().st_size>1_048_576:
            raise ValueError('Unsafe or oversized context notes file.')
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            if data.get('schema')!=1 or not isinstance(data.get('annotations'),list):
                raise ValueError()
            result=[];seen=set()
            for item in data['annotations']:
                kind,ident,note=item['kind'],item['id'],item['note']
                if kind not in {'entity','device','area'} or not isinstance(ident,str) or not ident or len(ident)>512:
                    raise ValueError()
                if any(ord(c)<32 for c in ident) or not isinstance(note,str) or len(note)>20000:
                    raise ValueError()
                if (kind,ident) in seen:raise ValueError()
                seen.add((kind,ident));result.append({'kind':kind,'id':ident,'note':note})
            return result
        except (ValueError,KeyError,TypeError,AttributeError) as exc:
            raise ValueError('Context notes could not be read. The original file was preserved.') from exc

    def annotation(self, kind: str, ident: str) -> str:
        return next((n['note'] for n in self.load_annotations() if n['kind']==kind and n['id']==ident),'')

    def save_annotation(self, kind: str, ident: str, note: str) -> None:
        if kind not in {'entity','device','area'} or not isinstance(ident,str) or not ident or len(ident)>512:
            raise ValueError('Choose an entity, device or area from the snapshot.')
        if any(ord(c)<32 for c in ident) or not isinstance(note,str) or len(note)>20000:
            raise ValueError('Invalid note. Keep it below 20,000 characters.')
        self.initialize()
        notes=[n for n in self.load_annotations() if (n['kind'],n['id'])!=(kind,ident)]
        if note.strip():notes.append({'kind':kind,'id':ident,'note':note})
        notes.sort(key=lambda n:(n['kind'],n['id']))
        raw=json.dumps({'schema':1,'annotations':notes},ensure_ascii=False,indent=2)+'\n'
        if len(raw.encode())>1_048_576:raise ValueError('Context notes exceed the 1 MiB limit.')
        private_replace(self.annotations,raw)

    def reset(self) -> None:
        self.initialize()
        for name in ('config.json', 'token', 'last-check.json'):
            path = self.local/name
            if path.exists() or path.is_symlink():
                path.unlink()  # Unlink, never follow.

    def history(self) -> list[Path]:
        if not self.exports.is_dir() or self.exports.is_symlink():
            return []
        out=[]
        for path in self.exports.iterdir():
            if path.is_symlink() or not path.is_dir() or path.name.startswith('.'):
                continue
            try:
                m = json.loads((path/'manifest.json').read_text())
                if m.get('tool') == 'ha-context':
                    out.append(path)
            except (ValueError,OSError):
                continue
        return sorted(out, key=lambda p:p.name, reverse=True)

    def delete_export(self, path: Path) -> None:
        if path not in self.history() or path.parent.resolve() != self.exports.resolve():
            raise ValueError('Not an owned ha-context export.')
        if os.path.ismount(path):
            raise ValueError('Refusing to delete a mount point.')
        shutil.rmtree(path)

    def prune(self, keep: int) -> None:
        if keep > 0:
            for path in self.history()[keep:]:
                self.delete_export(path)

    def uninstall(self) -> None:
        if self.addon:
            raise ValueError('Home Assistant manages this app. Use its Uninstall button in Settings > Apps.')
        root = validate_install_root(self.root)
        marker=json.loads((root/INSTALL_MARKER).read_text())
        if marker.get('tool')!='ha-context' or marker.get('root')!=str(root):
            raise ValueError('Installation identity does not match. Nothing was removed.')
        settings = self.load()
        if settings and settings.source_dir:
            src=Path(settings.source_dir).expanduser().resolve()
            if root == src or root.is_relative_to(src) or src.is_relative_to(root):
                raise ValueError('Installation overlaps Home Assistant configuration. Nothing was removed.')
        if any(os.path.ismount(p) for p in root.rglob('*') if p.is_dir() and not p.is_symlink()):
            raise ValueError('Installation contains a mount point. Nothing was removed.')
        for base in (Path.home()/'.local/bin', Path('/usr/local/bin')):
            link=base/'ha-context'
            if link.is_symlink() and link.resolve()==(root/'ha-context').resolve():
                try:
                    link.unlink()
                except PermissionError:
                    raise ValueError('System command needs authorization to remove. Use Authorize command removal first.')
        os.chdir(root.parent)
        shutil.rmtree(root)


def legacy_candidates(home: Path, current: Path) -> list[Path]:
    """Only recognized previous exporter artifacts; never walk unrelated folders."""
    home=home.expanduser().resolve();current=current.resolve();result=[]
    def safe(p):
        return (p.exists() and not p.is_symlink() and p.resolve().is_relative_to(home)
                and p.resolve()!=current and not current.is_relative_to(p.resolve())
                and not (p/'configuration.yaml').exists())
    old=home/'.config/ha-context'
    try:
        v=json.loads((old/'connection.json').read_text())
        if safe(old) and isinstance(v,dict) and 'url' in v and 'token' in v and set(x.name for x in old.iterdir()) <= {'connection.json'}:
            result.append(old)
    except (OSError, ValueError): pass
    for old in [home/'.local/share/ha-context',home/'ha-context-toolkit',home/'ha-context-update']:
        script=old/'ha_context.py'
        try:
            head=script.read_text()[:1500]
            if safe(old) and 'Read-only Home Assistant context exporter' in head:
                # Tool-created folder, but refuse unexpected top-level user files.
                known={'ha_context.py','install.sh','run.sh','requirements.txt','README_PL.md','README_PL.txt',
                       'TEST_REPORT.txt','tests','venv','.venv','__pycache__'}
                if set(p.name for p in old.iterdir()) <= known:
                    result.append(old)
        except OSError: pass
    old=home/'ha_context.py'
    try:
        if safe(old) and old.is_file() and old.stat().st_size < 2_000_000:
            head=old.read_text()[:2000]
            if 'Read-only Home Assistant context exporter' in head and re.search(r"VERSION\s*=\s*['\"]1\.",head):
                result.append(old)
    except (OSError,UnicodeError): pass
    old=home/'ha-context-exports'
    if safe(old) and old.is_dir():
        entries=list(old.iterdir())
        try:
            if entries and all(not p.is_symlink() and p.is_dir() and json.loads((p/'manifest.json').read_text()).get('tool')=='ha-context' for p in entries):
                result.append(old)
        except (OSError,ValueError): pass
    return result


def remove_legacy(path: Path, home: Path, current: Path) -> None:
    if path not in legacy_candidates(home,current):
        raise ValueError('This is not a recognized legacy exporter path. Nothing was removed.')
    if os.path.ismount(path) or any(os.path.ismount(p) for p in path.rglob('*') if p.is_dir() and not p.is_symlink()):
        raise ValueError('Refusing to remove a mounted directory.')
    shutil.rmtree(path) if path.is_dir() else path.unlink()


def grouped_issues(warnings: list[dict]) -> list[dict]:
    groups={}
    for row in warnings:
        reason=row.get('reason','Unknown issue')
        g=groups.setdefault(reason,{'reason':reason,'sections':[]})
        g['sections'].append(row.get('section','unknown')+((': '+str(row['path'])) if row.get('path') else ''))
    return list(groups.values())


def compare_exports(before: list[dict], after: list[dict]) -> dict:
    def idx(rows):
        keys=('entity_id','device_id','platform','disabled_by','hidden_by','effective_area_id','name')
        return {r['entity_id']:{k:r.get(k) for k in keys} for r in rows}
    a,b=idx(before),idx(after)
    return {'added':sorted(b.keys()-a.keys()),'removed':sorted(a.keys()-b.keys()),
            'changed':sorted(k for k in a.keys()&b.keys() if a[k]!=b[k])}


def discover_containers(use_sudo=False) -> tuple[list[dict], list[str]]:
    rows=[];issues=[]
    for runtime in ('docker','podman'):
        try:
            found=engine.containers(runtime,use_sudo=use_sudo and runtime=='docker')
            for row in found:
                prefix=['sudo','-n','docker'] if row.get('docker_sudo') else [runtime]
                networks=engine.run_command(prefix+['inspect','--format','{{json .NetworkSettings.Networks}}',row['name']])
                row['networks']=json.loads(networks)
                rows.append(row)
        except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired) as exc:
            issues.append(runtime+' could not be inspected: '+safe_error(exc)+'. '
                          + ('Use Authorize Docker in Connection settings.' if runtime=='docker'
                             else 'Check this user’s Podman access.'))
    return rows,issues


def choose_endpoint(row: dict) -> str:
    mappings=(row.get('ports') or {}).get('8123/tcp') or []
    for port in mappings:
        if port.get('HostPort'):
            host=port.get('HostIp') or '127.0.0.1'
            if host in {'0.0.0.0','::'}: host='127.0.0.1'
            if ':' in host: host='['+host+']'
            return f"http://{host}:{int(port['HostPort'])}"
    if row.get('network_mode')=='host': return 'http://127.0.0.1:8123'
    addresses=[]
    for net in (row.get('networks') or {}).values():
        if net.get('IPAddress'): addresses.append(net['IPAddress'])
    if len(addresses)==1: return 'http://'+addresses[0]+':8123'
    if len(addresses)>1:
        raise ValueError('This container has several networks. Enter its reachable local URL explicitly.')
    raise ValueError('No local address detected. Enter the reachable HA URL explicitly.')


def resolved_settings(settings: Settings) -> Settings:
    settings.validate()
    value=dataclasses.replace(settings)
    if settings.auto_url and settings.source_mode=='container':
        rows,issues=discover_containers(settings.docker_sudo)
        selected=[r for r in rows if r['name']==settings.container and r['runtime']==settings.runtime]
        if len(selected)!=1:
            access_issues = [message for message in issues if message.startswith(settings.runtime)]
            if access_issues:
                raise ValueError('Cannot verify the selected container. ' + ' '.join(access_issues))
            raise ValueError('The selected container was not found among running HA containers. '
                             'Check its name and runtime in Connection settings.')
        value.url=choose_endpoint(selected[0])
    return value


def engine_args(settings: Settings, output: Path):
    from types import SimpleNamespace
    return SimpleNamespace(config_dir=settings.source_dir if settings.source_mode=='local' else None,
        source_mode=settings.source_mode, container=settings.container or None,
        runtime=settings.runtime, docker_sudo=settings.docker_sudo,
        max_file_mb=8,max_config_mb=64,no_device_details=not settings.device_details,
        device_capabilities=True,output=str(output))


def client_for(settings: Settings, token: str):
    return engine.HAClient(settings.url,token,timeout=settings.timeout,supervisor=settings.supervisor)


def diagnostics(settings: Settings, token: str) -> list[dict]:
    settings=resolved_settings(settings)
    c=client_for(settings,token);out=[]
    try:
        for label, action in [('REST API',lambda:c.get('/api/config')),
                              ('WebSocket',lambda:c.ws_request('config/entity_registry/list'))]:
            try:
                value=action()
                out.append({'check':label,'status':'OK','detail':('HA '+str(value.get('version'))) if isinstance(value,dict) else str(len(value))+' registry entries'})
            except Exception as exc:
                out.append({'check':label,'status':'FAILED','detail':safe_error(exc,token)})
        if settings.source_mode=='api':
            out.append({'check':'Configuration files','status':'NOT SELECTED','detail':'API-only mode; local YAML/includes will not be present.'})
        else:
            try:
                args=engine_args(settings,Path('/unused'))
                src=engine.select_source(args,{'config_dir':'/config'},[])
                if src['kind']=='local':
                    engine.readable_config_folder(src['path'])
                    ok=True
                else:
                    prefix=['sudo','-n','docker'] if src.get('docker_sudo') else [src['runtime']]
                    engine.run_command(prefix+['exec',src['name'],'python3','-c',
                        'import os,sys;sys.exit(0 if os.access(sys.argv[1],os.R_OK) else 1)', src['path']+'/configuration.yaml'])
                    ok=True
                out.append({'check':'Configuration files','status':'OK' if ok else 'FAILED','detail':src['path']})
            except Exception as exc:
                out.append({'check':'Configuration files','status':'FAILED','detail':safe_error(exc,token)})
    finally: c.close()
    return out


def safe_error(exc: Exception, token: str='') -> str:
    value=str(exc) if type(exc) in {RuntimeError,ValueError} else type(exc).__name__
    return safe_text(engine.Redactor([token]).text(value))[:1200]


def source_archive(root: Path, destination: Path) -> Path:
    """Publish allowlisted project files, never local state, exports or git history."""
    manifest=json.loads((root/'project-files.json').read_text())
    expected=manifest.get('files',[])
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
        for name in expected:
            rel=Path(name)
            if rel.is_absolute() or '..' in rel.parts or rel.parts[0] in {'local','.git','.venv','.vendor'}:
                raise ValueError('Unsafe project manifest entry.')
            path=root/rel
            if any(p.is_symlink() for p in [path, *path.parents] if p == root or root in p.parents) or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Cannot publish a symbolic link or external file.')
            z.write(path,'ha-context/'+name)
    destination.chmod(0o600)
    return destination
