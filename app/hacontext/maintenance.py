"""Narrowly scoped command installation and transactional source updates."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import zipfile
from .state import Store, private_replace, PROJECT_MARKER, safe_text


def command_path() -> Path:
    local=Path.home()/'.local/bin'
    candidates=[Path(p).expanduser().absolute() for p in os.environ.get('PATH','').split(os.pathsep) if p]
    if local.absolute() in candidates:return local/'ha-context'
    # This standard Linux PATH location avoids permanent shell-configuration edits.
    return Path('/usr/local/bin/ha-context')


def known_old_launcher(path: Path) -> bool:
    try:
        if path.is_symlink():
            return path.resolve().parent==Path.home()/'.local/share/ha-context'
        if path.stat().st_size>8192:return False
        text=path.read_text()
        return 'ha_context.py' in text and '.local/share/ha-context' in text and 'exec ' in text
    except OSError:return False


def install_link(store: Store, path: Path, sudo=False) -> None:
    expected=store.root/'ha-context'
    if not expected.is_file():raise ValueError('The command launcher is missing from the program folder.')
    if path not in {Path.home()/'.local/bin/ha-context',Path('/usr/local/bin/ha-context')}:
        raise ValueError('Unexpected command destination.')
    if path.is_symlink() and path.resolve()==expected.resolve():return
    if path.exists() or path.is_symlink():
        if sudo or not known_old_launcher(path):
            raise ValueError('The command name is already used by an unrecognized installation. Nothing was overwritten.')
        backup=store.local/'migration'/'previous-launcher'
        private_replace(backup,path.read_text())
        path.unlink()
    if sudo:
        proc=subprocess.run(['sudo','-n','ln','-s','--',str(expected),str(path)],capture_output=True,check=False)
        if proc.returncode:raise ValueError('Could not install the command shortcut. Authorization may have expired.')
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.symlink_to(expected)


def remove_system_link(store: Store) -> None:
    link=Path('/usr/local/bin/ha-context')
    if not link.is_symlink() or link.resolve()!=(store.root/'ha-context').resolve():
        raise ValueError('The system command does not point to this installation. Nothing was removed.')
    proc=subprocess.run(['sudo','-n','rm','--',str(link)],capture_output=True,check=False)
    if proc.returncode:raise ValueError('Could not remove the command shortcut. Installation remains.')


def git_update(root: Path) -> str:
    if not (root/'.git').exists():raise ValueError('This is not a Git checkout.')
    def git(*args):
        proc=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,timeout=120,
                            env={**os.environ,'GIT_TERMINAL_PROMPT':'0'},check=False)
        if proc.returncode:raise ValueError('Git could not complete '+args[0]+'. Check repository access and the configured upstream. Local data was preserved.')
        return proc.stdout.strip()
    if git('status','--porcelain','--untracked-files=no'):
        raise ValueError('Tracked files have local changes. Automatic update refused; nothing was overwritten.')
    git('remote','get-url','origin')
    git('fetch','origin')
    git('merge','--ff-only','@{upstream}')
    return 'Source is up to date at '+git('rev-parse','--short','HEAD')+'.'


ALLOWED_TOP={'app','tests','docs','.github','README.md','LICENSE','SECURITY.md','CHANGELOG.md',
             'install.sh','ha-context','pyproject.toml','repository.yaml','.gitignore','.ha-context-project','project-files.json'}


def checked_member(name: str) -> str:
    if name.startswith('ha-context/'):name=name[len('ha-context/'):]
    p=Path(name)
    if '\\' in name or p.is_absolute() or not p.parts or '..' in p.parts or p.parts[0] not in ALLOWED_TOP:
        raise ValueError('Source archive contains a disallowed path.')
    if any(x in p.parts for x in {'local','.git','.venv','.vendor','__pycache__'}):
        raise ValueError('Source archive contains private/runtime files.')
    return p.as_posix()


def install_source_zip(store: Store, archive: Path) -> None:
    if store.addon:raise ValueError('Update this HA OS app through Home Assistant.')
    if not archive.is_file():raise ValueError('The selected ZIP does not exist.')
    files={};total=0
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist())>2000:raise ValueError('Too many files in source archive.')
        for info in z.infolist():
            if info.is_dir():continue
            name=checked_member(info.filename)
            if stat.S_ISLNK(info.external_attr>>16):raise ValueError('Symlinks are not allowed in source archives.')
            total+=info.file_size
            if total>50*1024*1024 or info.file_size>8*1024*1024:raise ValueError('Source archive size limit exceeded.')
            if name in files:raise ValueError('Duplicate source archive path.')
            files[name]=z.read(info)
    if files.get('.ha-context-project',b'').decode().strip()!=PROJECT_MARKER:
        raise ValueError('This is not an identified ha-context source package.')
    try:manifest=json.loads(files['project-files.json'])
    except (KeyError,ValueError):raise ValueError('The source manifest is missing or invalid.')
    if set(manifest.get('files',[]))!=set(files):raise ValueError('Source archive and manifest disagree.')
    for name,digest in manifest.get('sha256',{}).items():
        if name not in files or hashlib.sha256(files[name]).hexdigest()!=digest:
            raise ValueError('Source integrity check failed.')
    current=json.loads((store.root/'project-files.json').read_text())
    previous=set(current['files']);incoming=set(files)
    # Validate every destination before changing any file.
    for name in previous|incoming:
        checked_member(name)
        dest=store.root/name
        if dest.is_symlink() or any(p.is_symlink() for p in dest.parents if p.is_relative_to(store.root)):
            raise ValueError('Source destination contains a symlink. Update refused.')
    backup=store.local/'rollback'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True,mode=0o700)
    saved=[];written=[]
    try:
        for name in previous|incoming:
            source=store.root/name
            if source.is_file():
                target=backup/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);saved.append(name)
        for name,raw in files.items():
            dest=store.root/name;dest.parent.mkdir(parents=True,exist_ok=True)
            temp=dest.with_name(dest.name+'.ha-context-writing')
            with temp.open('xb') as stream:stream.write(raw)
            os.replace(temp,dest);written.append(name)
        for name in previous-incoming:
            (store.root/name).unlink(missing_ok=True)
        for name in ('ha-context','install.sh'):
            if (store.root/name).exists():(store.root/name).chmod(0o755)
    except Exception:
        for name in written:
            if name not in saved:(store.root/name).unlink(missing_ok=True)
        for name in saved:
            target=store.root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(backup/name,target)
        raise
