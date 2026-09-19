"""Build source and offline portable archives from an explicit clean project tree.

Run on a build machine that already has the pinned requirements installed.
The portable package bundles pure-Python code and dependency licenses, never fonts.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

MODULES={'prompt_toolkit':'prompt_toolkit','yaml':'PyYAML','websocket':'websocket-client','wcwidth':'wcwidth'}
TOP={'app','tests','docs','.github','README.md','LICENSE','SECURITY.md','CHANGELOG.md',
     'install.sh','ha-context','pyproject.toml','repository.yaml','.gitignore','.ha-context-project'}
SKIP={'__pycache__','.pytest_cache','.git','.venv','.vendor','local'}


def digest(raw: bytes) -> str:return hashlib.sha256(raw).hexdigest()


def source_files(root: Path) -> dict[str,bytes]:
    files={}
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if not rel.parts or rel.parts[0] not in TOP or set(rel.parts)&SKIP:continue
        if p.is_symlink():raise ValueError('Source contains a symlink: '+str(rel))
        if p.is_file():
            if p.suffix in {'.pyc','.pyo','.so','.ttf','.otf','.woff','.woff2'}:continue
            files[rel.as_posix()]=p.read_bytes()
    manifest={'tool':'ha-context','files':sorted([*files,'project-files.json']),
              'sha256':{name:digest(raw) for name,raw in files.items()}}
    files['project-files.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    (root/'project-files.json').write_bytes(files['project-files.json'])
    return files


def vendor_files(root: Path) -> dict[str,bytes]:
    files={}
    for module,distribution in MODULES.items():
        package=Path(importlib.util.find_spec(module).origin).parent
        for p in sorted(package.rglob('*')):
            if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts:continue
            if p.suffix in {'.pyc','.pyo','.so','.pyd','.dll','.ttf','.otf','.woff','.woff2'}:continue
            files['.vendor/'+module+'/'+p.relative_to(package).as_posix()]=p.read_bytes()
        dist=importlib.metadata.distribution(distribution)
        for rel in dist.files or []:
            name=str(rel)
            if '.dist-info/' in name and (name.endswith(('METADATA','WHEEL','top_level.txt')) or '/licenses/' in name or name.endswith('LICENSE')):
                p=Path(dist.locate_file(rel))
                if p.is_file():files['.vendor/'+name]=p.read_bytes()
        if not any(distribution.lower().replace('-','_') in n.lower().replace('-','_') and 'license' in n.lower() for n in files):
            raise ValueError('License not found for '+distribution)
    files['.vendor/requirements.sha256']=(digest((root/'app/requirements.txt').read_bytes())+'\n').encode()
    files['.vendor/THIRD_PARTY.txt']=('\n'.join(f'{d} {importlib.metadata.version(d)} — license in its .dist-info directory' for d in MODULES.values())+'\n').encode()
    return files


def add(z: zipfile.ZipFile, name: str, data: bytes):
    info=zipfile.ZipInfo(name,date_time=(2026,9,19,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
    info.external_attr=((0o100755 if name in {'ha-context','install.sh'} else 0o100644)<<16)
    z.writestr(info,data)


def build(root: Path, output: Path):
    output.mkdir(parents=True,exist_ok=True)
    files=source_files(root)
    with zipfile.ZipFile(output/'ha-context-source.zip','w') as z:
        for name,data in files.items():add(z,'ha-context/'+name,data)
    files.update(vendor_files(root))
    with zipfile.ZipFile(output/'ha-context.pyz','w') as z:
        for name,data in files.items():add(z,name,data)
        # Python imports modules from archive.pyz/.vendor, but its standard
        # metadata finder inspects ZIP roots, not subdirectories within a ZIP.
        # Expose the SAME metadata at the archive root for bootstrap imports.
        # These aliases are deliberately outside the install payload: the
        # installed application keeps a single copy under .vendor.
        for name,data in files.items():
            if name.startswith('.vendor/') and '.dist-info/' in name:
                add(z,name.removeprefix('.vendor/'),data)
        add(z,'distribution.json',(json.dumps({'sha256':{name:digest(data) for name,data in files.items()}},indent=2)+'\n').encode())
        add(z,'__main__.py',(root/'app/bootstrap.py').read_bytes())
    print('Created source ZIP and offline portable installer in '+str(output))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    build(Path(__file__).resolve().parents[1],args.output)
