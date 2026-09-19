import hashlib,json,os,zipfile
from pathlib import Path
import pytest
import bootstrap
from hacontext.state import Store,Settings,source_archive
from hacontext.maintenance import install_source_zip


def make_archive(path,files):
    values={'.ha-context-project':b'ha-context-project:2\n',**files}
    manifest={'files':sorted([*values,'project-files.json']),
              'sha256':{n:hashlib.sha256(v).hexdigest() for n,v in values.items()}}
    values['project-files.json']=json.dumps(manifest).encode()
    with zipfile.ZipFile(path,'w') as z:
        for name,value in values.items():z.writestr(name,value)
        z.writestr('distribution.json',json.dumps({'sha256':{n:hashlib.sha256(v).hexdigest() for n,v in values.items()}}))
    return values


def test_portable_install_preserves_existing_folder(tmp_path):
    archive=tmp_path/'release.pyz';make_archive(archive,{'ha-context':b'launcher'})
    target=tmp_path/'existing';target.mkdir();(target/'keep').write_text('kept')
    with pytest.raises(ValueError):bootstrap.install(archive,target)
    assert (target/'keep').read_text()=='kept'


def test_portable_install_and_integrity(tmp_path):
    archive=tmp_path/'release.pyz';values=make_archive(archive,{'ha-context':b'launcher'})
    target=bootstrap.install(archive,tmp_path/'installed')
    assert (target/'ha-context').read_bytes()==b'launcher'
    assert not (target/'distribution.json').exists()
    with pytest.warns(UserWarning,match='Duplicate name'):
        with zipfile.ZipFile(archive,'a') as z:z.writestr('ha-context',b'corrupted')
    with pytest.raises(ValueError,match='integrity'):bootstrap.install(archive,tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def test_source_update_preserves_private_data(tmp_path):
    store=Store(tmp_path/'installed');store.initialize();store.save(Settings(url='http://localhost:8123'),'PRIVATE_FIXTURE_TOKEN')
    (store.root/'README.md').write_text('old')
    (store.root/'project-files.json').write_text(json.dumps({'files':['README.md','project-files.json']}))
    zip_path=tmp_path/'update.zip'
    values=make_archive(tmp_path/'portable.pyz',{'README.md':b'new','ha-context':b'#!/bin/sh\n','install.sh':b'#!/bin/sh\n'})
    with zipfile.ZipFile(zip_path,'w') as z:
        for name,value in values.items():z.writestr('ha-context/'+name,value)
    before=store.config.read_bytes()
    install_source_zip(store,zip_path)
    assert (store.root/'README.md').read_text()=='new'
    assert store.config.read_bytes()==before and store.token()=='PRIVATE_FIXTURE_TOKEN'
    assert list((store.local/'rollback').iterdir())


def test_clean_source_sharing_excludes_local(tmp_path):
    store=Store(tmp_path/'installed');store.initialize();store.save(Settings(url='http://localhost:8123'),'PRIVATE_FIXTURE_TOKEN')
    (store.root/'README.md').write_text('public')
    (store.root/'project-files.json').write_text(json.dumps({'files':['README.md','project-files.json']}))
    out=source_archive(store.root,tmp_path/'source.zip')
    with zipfile.ZipFile(out) as z:
        assert set(z.namelist())=={'ha-context/README.md','ha-context/project-files.json'}
        assert b'PRIVATE_FIXTURE_TOKEN' not in b''.join(z.read(n) for n in z.namelist())
