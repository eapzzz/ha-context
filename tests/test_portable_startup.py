"""Exercise the shipped archive, not just files extracted from it.

-I -S excludes installed distributions; those can mask broken zip metadata lookup.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import time
import zipfile

import pytest

import build_release


@pytest.fixture(scope='module')
def portable(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    out = tmp_path_factory.mktemp('portable-release')
    build_release.build(root, out)
    return out / 'ha-context.pyz'


def isolated(python_code, *args):
    return subprocess.run(
        [sys.executable, '-I', '-S', '-c', python_code, *map(str, args)],
        capture_output=True, text=True, timeout=20,
    )


def test_zip_dependency_metadata_is_visible_without_site_packages(portable):
    result = isolated('''
import importlib.metadata as md
import json, sys
p = sys.argv[1]
sys.path[:0] = [p + '/app', p + '/.vendor', p]
expected = dict(line.strip().split('==') for line in __import__('zipfile').ZipFile(p).read('app/requirements.txt').decode().splitlines() if line.strip())
found = {name: md.version(name) for name in expected}
assert found == expected, (found, expected)
import prompt_toolkit, yaml, websocket, wcwidth
for module in (prompt_toolkit, yaml, websocket, wcwidth):
    assert module.__file__.startswith(p + '/.vendor/'), module.__file__
assert not any('site-packages' in entry for entry in sys.path), sys.path
print(json.dumps(found))
''', portable)
    assert result.returncode == 0, result.stderr
    assert 'prompt_toolkit' in result.stdout


def test_pyz_metadata_aliases_equal_vendored_metadata(portable):
    with zipfile.ZipFile(portable) as z:
        for name in z.namelist():
            if name.startswith('.vendor/') and '.dist-info/' in name:
                alias = name.removeprefix('.vendor/')
                assert alias in z.namelist(), f'Metadata alias absent: {alias}'
                assert z.read(alias) == z.read(name)
        payload = json.loads(z.read('distribution.json'))['sha256']
        # Bootstrap aliases are for zip lookup only. Install one copy in .vendor.
        assert all('.dist-info/' not in name or name.startswith('.vendor/') for name in payload)
        assert all(hashlib.sha256(z.read(n)).hexdigest() == h for n, h in payload.items())


def test_isolated_installer_imports_before_showing_folder_dialog(portable, tmp_path):
    if os.name != 'posix':
        pytest.skip('Linux terminal installer')
    import fcntl
    import termios
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 110, 0, 0))
    process = subprocess.Popen(
        [sys.executable, '-I', '-S', str(portable)],
        stdin=slave, stdout=slave, stderr=slave,
        env={**os.environ, 'HOME': str(tmp_path), 'TERM': 'xterm-256color'},
        start_new_session=True,
    )
    os.close(slave)
    output = bytearray()
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], .1)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
                # A terminal query deserves a terminal response, not a timeout.
                if b'\x1b[6n' in chunk:
                    os.write(master, b'\x1b[1;1R')
                if b'Choose one folder for the program' in output:
                    break
            if process.poll() is not None:
                break
        text = output.decode(errors='replace')
        assert 'Choose one folder for the program' in text, text
        assert 'PackageNotFoundError' not in text and 'Traceback' not in text
        assert not (tmp_path / 'ha-context').exists(), 'Viewing installer must not install'
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
        os.close(master)


def test_installed_ui_imports_offline_without_bootstrap_aliases(portable, tmp_path):
    target = tmp_path / 'installed'
    process = subprocess.run(
        [sys.executable, '-I', '-S', str(portable), '--install-only', str(target)],
        capture_output=True, text=True, timeout=20,
    )
    assert process.returncode == 0, process.stderr
    assert not list(target.glob('*.dist-info'))
    result = isolated('''
import sys
from pathlib import Path
p = Path(sys.argv[1])
sys.path[:0] = [str(p/'app'), str(p/'.vendor')]
import prompt_toolkit, yaml, websocket, wcwidth
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from hacontext.state import Store
from hacontext.ui import ContextUI
s = Store(p)
s.initialize()
with create_pipe_input() as inp:
    ui = ContextUI(s, input=inp, output=DummyOutput())
    assert ui.page == 'welcome', ui.page
print('Installed UI initialized from bundled dependencies')
''', target)
    assert result.returncode == 0, result.stderr
