import hashlib,importlib.util,json
from pathlib import Path
import pytest

@pytest.fixture
def bundle_module():
    path=Path(__file__).resolve().parents[2]/'scripts/build_offline_bundle.py'
    spec=importlib.util.spec_from_file_location('offline_bundle',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def test_bundle_never_selects_live_environment_or_private_storage(bundle_module,monkeypatch):
    paths=['.env','.env.example','app/.env.secret','output/report.json','db_data/private.db','uploaded_pdfs/book.pdf','foo.py']
    monkeypatch.setattr(bundle_module.subprocess,'check_output',lambda *a,**k:'\0'.join(paths).encode())
    assert list(bundle_module.source_files())==['.env.example','foo.py']

def test_model_manifest_paths_and_blob_integrity_are_verified(bundle_module,tmp_path):
    root=tmp_path/'models';target=tmp_path/'target'
    manifest=root/'manifests/registry.ollama.ai/library/example/latest';manifest.parent.mkdir(parents=True)
    blob=b'public synthetic model data';digest=hashlib.sha256(blob).hexdigest()
    (root/'blobs').mkdir();(root/'blobs'/('sha256-'+digest)).write_bytes(blob)
    manifest.write_text(json.dumps({'config':{'digest':'sha256:'+digest},'layers':[]}))
    bundle_module.copy_model(root,target,'example:latest')
    assert (target/'blobs'/('sha256-'+digest)).read_bytes()==blob
    (root/'blobs'/('sha256-'+digest)).write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='checksum'):bundle_module.copy_model(root,target,'example:latest')
    manifest.write_text(json.dumps({'config':{'digest':'../../private'},'layers':[]}))
    with pytest.raises(ValueError,match='Invalid model'):bundle_module.copy_model(root,target,'example:latest')

def test_copy_refreshes_read_only_generated_file(bundle_module,tmp_path):
    source=tmp_path/'source';dest=tmp_path/'generated';source.write_text('new');dest.write_text('old');dest.chmod(0o444)
    bundle_module.copy(source,dest)
    assert dest.read_text()=='new'
