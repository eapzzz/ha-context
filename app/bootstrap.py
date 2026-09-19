"""Portable first-run installer. No network, pip or root shell required."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import zipfile


def install(archive: Path, target: Path) -> Path:
    from hacontext.state import validate_install_root, PROJECT_MARKER
    target=validate_install_root(target)
    if target.exists():
        raise ValueError('That folder already exists. Choose a new dedicated folder; nothing was overwritten.')
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('distribution.json'))
        payload=manifest['sha256']
        if not isinstance(payload,dict) or len(payload)>5000:
            raise ValueError('Invalid distribution manifest.')
        if z.read('.ha-context-project').decode().strip()!=PROJECT_MARKER:
            raise ValueError('Unrecognized application package.')
        items=[];total=0
        for name,digest in payload.items():
            rel=PurePosixPath(name)
            if (rel.is_absolute() or '..' in rel.parts or '\\' in name
                or not rel.parts or rel.parts[0] in {'local','.git','.venv'}):
                raise ValueError('Invalid path in package.')
            info=z.getinfo(name)
            total+=info.file_size
            if stat.S_ISLNK(info.external_attr>>16) or total>80*1024*1024 or info.file_size>8*1024*1024:
                raise ValueError('Invalid package size or file type.')
            data=z.read(info)
            if hashlib.sha256(data).hexdigest()!=digest:
                raise ValueError('Package integrity check failed. Use an intact trusted copy.')
            items.append((name,data,info.external_attr>>16))
        stage=Path(tempfile.mkdtemp(prefix='.ha-context-install-',dir=target.parent))
        try:
            for name,data,mode in items:
                dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(data);dest.chmod(0o755 if mode&0o111 else 0o644)
            # Never replace an existing target, even if another installer created it.
            if target.exists():raise ValueError('The destination was created during installation. Nothing was replaced.')
            os.rename(stage,target)
            target.chmod(0o700)
        finally:
            if stage.exists():shutil.rmtree(stage)
    return target


def main():
    if sys.version_info<(3,10):raise SystemExit('Python 3.10 or newer is required.')
    if os.name!='posix':raise SystemExit('Run the portable installer on Linux or your Linux server.')
    archive=Path(sys.argv[0]).resolve()
    # Include the ZIP root explicitly for bundled .dist-info discovery.
    sys.path[:0]=[str(archive)+'/app',str(archive)+'/.vendor',str(archive)]
    import argparse
    parser=argparse.ArgumentParser(description='Install and open ha-context. An intact portable file works offline.')
    parser.add_argument('--install-only',metavar='FOLDER',help='install without opening the interface')
    args=parser.parse_args()
    if args.install_only:
        try:print(install(archive,Path(args.install_only)))
        except Exception as exc:raise SystemExit(str(exc))
        return
    if not sys.stdin.isatty():raise SystemExit('Open an interactive terminal or SSH session to start onboarding.')
    from prompt_toolkit.shortcuts import input_dialog,message_dialog
    from hacontext.ui import STYLE
    from hacontext.state import safe_text
    target=Path.home()/'ha-context'
    while True:
        chosen=input_dialog(title='ha-context  /  Welcome',
            text='Choose one folder for the program, private settings and exports.\n\n'
                 'No AI connection. No Home Assistant changes.\n'
                 'Existing folders are never overwritten.\n\n'
                 'After installation, the guided setup opens automatically.',
            default=str(target),ok_text='Install',cancel_text='Cancel',style=STYLE).run()
        if chosen is None:return
        try:target=install(archive,Path(chosen).expanduser());break
        except Exception as exc:
            message_dialog(title='Choose another folder',text=safe_text(exc),style=STYLE).run()
    os.execv('/bin/bash',['bash',str(target/'ha-context')])


if __name__=='__main__':main()
