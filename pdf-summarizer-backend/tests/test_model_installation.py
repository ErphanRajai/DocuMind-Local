"""Installer tests never download a model, change live settings or open a console."""
import hashlib
import io
import json
from pathlib import Path
import sys
import threading
from unittest.mock import MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import model_installation as install
import documind_cli as cli

NAME = install.CATALOG[0]['name']

@pytest.fixture
def manager(tmp_path, monkeypatch):
    project = tmp_path/'app'; project.mkdir()
    root = tmp_path/'old-models'; root.mkdir()
    m = install.ModelManager(project, {'OLLAMA_MODELS': str(root), 'DOCUMIND_OLLAMA_PORT': '21434', 'DOCUMIND_OLLAMA_OWNED':'1'})
    monkeypatch.setattr(install, 'remote_manifest', lambda name: [{'digest':'sha256:'+'a'*64,'size':1000}])
    monkeypatch.setattr(install, 'disk_free', lambda path: 10**12)
    return m

@pytest.mark.parametrize('value', ['llama3.2;calc.exe', '../private', 'https://evil.test/model', 'bge-m3'])
def test_only_catalogue_models_can_be_downloaded(value):
    with pytest.raises(install.InstallError): install.model_name(value)

def test_preview_counts_bytes_without_starting_download(manager, monkeypatch):
    spawn=MagicMock(side_effect=AssertionError('Preview cannot spawn a process'))
    monkeypatch.setattr(install.subprocess,'Popen',spawn)
    row=manager.preview(NAME,str(manager.active_root))
    assert row['model_bytes']==1000 and row['download_bytes']==1000
    assert not row['restart_required'] and row['copy_bytes']==0
    spawn.assert_not_called()

def test_unknown_running_server_storage_requires_controlled_restart(manager,monkeypatch):
    manager.environment.pop('DOCUMIND_OLLAMA_OWNED')
    monkeypatch.setattr(install,'read_json',lambda *a,**k:{'models':[{'name':NAME,'digest':'sha256:'+'f'*64}]})
    with pytest.raises(install.InstallError,match='Cannot confirm'):manager.preview(NAME,str(manager.active_root))

def test_actual_server_path_is_used_instead_of_a_matching_copied_manifest(manager,monkeypatch,tmp_path):
    actual=tmp_path/'actual-ollama';actual.mkdir()
    monkeypatch.setattr(install,'read_json',lambda url,*a,**k:{'models':[{'name':NAME}]} if url.endswith('/tags') else {'modelfile':f'FROM "{actual / "blobs" / "sha256-public"}"\n'})
    discovered=install.ModelManager(manager.project,{'DOCUMIND_OLLAMA_PORT':'21434','OLLAMA_MODELS':str(manager.active_root)})
    assert discovered.active_root==actual and discovered.storage_verified()

def test_review_requires_free_space_and_dedicated_non_nested_folder(manager, monkeypatch):
    with pytest.raises(install.InstallError,match='root'):manager.preview(NAME,str(manager.project))
    with pytest.raises(install.InstallError,match='inside'):manager.preview(NAME,str(manager.active_root/'nested'))
    monkeypatch.setattr(install,'disk_free',lambda path:1)
    with pytest.raises(install.InstallError,match='free space'):manager.preview(NAME,str(manager.active_root))

def test_wrong_size_blob_is_still_counted_as_needed(manager):
    blob=manager.active_root/'blobs'/('sha256-'+'a'*64);blob.parent.mkdir();blob.write_bytes(b'bad')
    assert manager.preview(NAME,str(manager.active_root))['download_bytes']==1000
    blob.write_bytes(b'x'*1000)
    assert manager.preview(NAME,str(manager.active_root))['download_bytes']==0

def test_relocation_reuses_copied_blobs_without_double_counting_space(manager,tmp_path):
    blob=manager.active_root/'blobs'/('sha256-'+'a'*64);blob.parent.mkdir();blob.write_bytes(b'x'*1000)
    target=tmp_path/'new-library'
    preview=manager.preview(NAME,str(target))
    assert preview['copy_bytes']==1000 and preview['download_bytes']==0
    install.copy_library(manager.active_root,target,threading.Event(),lambda *a:None)
    resumed=manager.preview(NAME,str(target))
    assert resumed['copy_bytes']==0 and resumed['download_bytes']==0

def test_copy_preserves_original_and_rejects_conflicts(manager,tmp_path):
    source=manager.active_root/'blobs'/('sha256-'+hashlib.sha256(b'original').hexdigest());source.parent.mkdir();source.write_bytes(b'original')
    target=tmp_path/'new-models'
    install.copy_library(manager.active_root,target,threading.Event(),lambda *args:None)
    assert source.read_bytes()==(target/'blobs'/source.name).read_bytes()==b'original'
    (target/'blobs'/source.name).write_bytes(b'conflict')
    with pytest.raises(install.InstallError,match='different file'):install.copy_library(manager.active_root,target,threading.Event(),lambda *args:None)
    assert source.read_bytes()==b'original'

def test_cancelled_copy_creates_no_replacement_files(manager,tmp_path):
    source=manager.active_root/'blobs'/('sha256-'+'a'*64);source.parent.mkdir();source.write_bytes(b'original')
    cancel=threading.Event();cancel.set()
    with pytest.raises(InterruptedError):install.copy_library(manager.active_root,tmp_path/'new',cancel,lambda *args:None)
    assert source.read_bytes()==b'original' and not (tmp_path/'new').exists()

def test_preview_is_single_use_and_only_one_install_can_run(manager):
    p=manager.preview(NAME,str(manager.active_root));job=manager.create_job(p['id'],console=False)
    assert job['state']=='queued'
    with pytest.raises(install.InstallError,match='already open'):manager.create_job(p['id'],console=False)
    manager.cancel(job['id'])
    with pytest.raises(install.InstallError,match='expired'):manager.create_job(p['id'],console=False)

def test_console_open_failure_is_retryable(manager,monkeypatch):
    monkeypatch.setattr(manager,'open_console',MagicMock(side_effect=OSError('blocked')))
    p=manager.preview(NAME,str(manager.active_root))
    with pytest.raises(install.InstallError,match='Command Prompt'):manager.create_job(p['id'])
    assert manager.status(next(iter(manager.jobs)))['state']=='failed'
    p=manager.preview(NAME,str(manager.active_root));assert manager.create_job(p['id'],console=False)['state']=='queued'

def test_console_closed_before_download_releases_queued_job(manager):
    job=manager.create_job(manager.preview(NAME,str(manager.active_root))['id'],console=False)
    console=MagicMock();console.poll.return_value=0;manager.consoles[job['id']]=console
    assert manager.status(job['id'])['state']=='cancelled'
    assert manager.jobs[job['id']]['finished'].is_set()

def test_loopback_helper_requires_its_secret_and_does_not_return_it(manager,monkeypatch):
    import urllib.request,urllib.error
    monkeypatch.setattr(install,'read_json',lambda *a,**kw:{'models':[]})
    manager.start();base=f'http://127.0.0.1:{manager.server.server_port}'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with pytest.raises(urllib.error.HTTPError) as denied:opener.open(base+'/catalog')
        assert denied.value.code==403
        request=urllib.request.Request(base+'/catalog',headers={'Authorization':'Bearer '+manager.token})
        with opener.open(request) as response:body=response.read().decode()
        assert 'models' in json.loads(body) and manager.token not in body
    finally:manager.close()

def fake_pull(manager,monkeypatch,events,names=None):
    monkeypatch.setattr(install,'LOCAL',MagicMock(open=lambda *a,**k:io.BytesIO(b''.join(json.dumps(row).encode()+b'\n' for row in events))))
    monkeypatch.setattr(install,'read_json',lambda *a,**k:{'models':[{'name':n} for n in (names if names is not None else [NAME])]})
    return manager.create_job(manager.preview(NAME,str(manager.active_root))['id'],console=False)['id']

def test_success_requires_terminal_event_and_installed_tag(manager,monkeypatch):
    key=fake_pull(manager,monkeypatch,[{'status':'downloading','total':1000,'completed':500},{'status':'success'}])
    rows=list(manager.run(key));assert rows[-1]['state']=='completed' and rows[0]['completed']==500
    assert manager.jobs[key]['finished'].is_set()

@pytest.mark.parametrize('events,names', [([{'status':'downloading'}],[NAME]),([{'error':'provider failed'}],[NAME]),([{'status':'success'}],[])])
def test_failed_or_unverified_download_never_looks_installed(manager,monkeypatch,events,names):
    key=fake_pull(manager,monkeypatch,events,names)
    assert list(manager.run(key))[-1]['state']=='failed'
    assert not (manager.project/'.env').exists()

def test_closing_progress_stream_cancels_and_releases_job(manager,monkeypatch):
    key=fake_pull(manager,monkeypatch,[{'status':'downloading','total':1000,'completed':500},{'status':'success'}])
    stream=manager.run(key);next(stream);stream.close()
    assert manager.status(key)['state']=='cancelled' and manager.jobs[key]['finished'].is_set()

def test_cli_help_and_no_implicit_download(capsys):
    with pytest.raises(SystemExit) as exit:cli.main(['--help'])
    assert exit.value.code==0 and 'models' in capsys.readouterr().out
    with pytest.raises(install.InstallError):cli.from_desktop('not-a-valid-job')

def test_new_directory_preserves_library_and_saves_only_after_success(manager,monkeypatch,tmp_path):
    source=manager.active_root/'manifests/registry.ollama.ai/library/bge-m3/latest';source.parent.mkdir(parents=True);source.write_text('public model manifest')
    target=tmp_path/'new-library'
    (manager.project/'.env').write_text('UNRELATED_SETTING=preserve\n')
    process=MagicMock();process.poll.return_value=None
    monkeypatch.setattr(install.subprocess,'Popen',lambda *a,**k:process)
    monkeypatch.setattr(install.shutil,'which',lambda *a:'ollama')
    monkeypatch.setattr(install,'read_json',lambda url,**k:{'version':'local'} if url.endswith('/version') else {'models':[{'name':NAME}]})
    monkeypatch.setattr(install,'LOCAL',MagicMock(open=lambda *a,**k:io.BytesIO(b'{"status":"success"}\n')))
    row=manager.preview(NAME,str(target));key=manager.create_job(row['id'],console=False)['id']
    assert 'DOCUMIND_MODEL_DIRECTORY' not in (manager.project/'.env').read_text()
    result=list(manager.run(key))[-1]
    assert result['state']=='completed' and result['restart_required']
    assert source.read_text()==(target/source.relative_to(manager.active_root)).read_text()
    assert 'UNRELATED_SETTING=preserve' in (manager.project/'.env').read_text()
    assert f'DOCUMIND_MODEL_DIRECTORY={target}' in (manager.project/'.env').read_text()
    process.terminate.assert_called_once()

@pytest.mark.anyio
@pytest.mark.parametrize('failed',[False,True])
async def test_unavailable_or_empty_ollama_is_not_reported_as_installed(monkeypatch,failed):
    from app.services.llm_service import LLMService
    import app.services.llm_service as service
    from unittest.mock import AsyncMock
    client=MagicMock();client.__aenter__=AsyncMock(return_value=client);client.__aexit__=AsyncMock()
    response=MagicMock(status_code=200);response.json.return_value={'models':[]}
    client.get=AsyncMock(side_effect=OSError('unavailable') if failed else None,return_value=response)
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kw:client)
    assert await LLMService.get_available_models()==[]

def test_cli_list_and_info_do_not_start_a_download(manager,monkeypatch,capsys):
    monkeypatch.setattr(cli,'ModelManager',lambda *a,**k:manager)
    monkeypatch.setattr(manager,'catalogue',lambda:{'directory':str(manager.active_root),'ollama_available':True,'models':[{'name':NAME,'installed':False}]})
    start=MagicMock(side_effect=AssertionError('Read-only commands cannot install'))
    monkeypatch.setattr(manager,'create_job',start)
    assert cli.main(['models','list'])==0 and 'not installed' in capsys.readouterr().out
    assert cli.main(['models','info',NAME])==0 and 'Destination:' in capsys.readouterr().out
    start.assert_not_called()

def test_cli_declined_confirmation_creates_no_job(manager,monkeypatch,capsys):
    monkeypatch.setattr(cli,'ModelManager',lambda *a,**k:manager)
    monkeypatch.setattr('builtins.input',lambda *a:'n')
    assert cli.main(['models','install',NAME])==0
    assert not manager.jobs and 'No download started' in capsys.readouterr().out

def test_cli_explicit_yes_uses_verified_stream_and_returns_success(manager,monkeypatch):
    monkeypatch.setattr(cli,'ModelManager',lambda *a,**k:manager)
    monkeypatch.setattr(install,'LOCAL',MagicMock(open=lambda *a,**k:io.BytesIO(b'{"status":"success"}\n')))
    monkeypatch.setattr(install,'read_json',lambda *a,**k:{'models':[{'name':NAME}]})
    assert cli.main(['models','install',NAME,'--yes'])==0
    assert manager.status(next(iter(manager.jobs)))['state']=='completed'

@pytest.mark.parametrize('terminal',[True,False])
def test_desktop_cli_requires_verified_completion_and_never_prints_credential(manager,monkeypatch,capsys,terminal):
    review=manager.preview(NAME,str(manager.active_root));review.update(message='working',total=0,completed=0)
    first=io.BytesIO(json.dumps(review).encode())
    second=io.BytesIO((json.dumps({**review,'state':'completed' if terminal else 'running'})+'\n').encode())
    monkeypatch.setenv('DOCUMIND_MODEL_MANAGER_PORT','12345');monkeypatch.setenv('DOCUMIND_MODEL_MANAGER_TOKEN','synthetic-local-credential')
    monkeypatch.setattr(cli,'LOCAL',MagicMock(open=MagicMock(side_effect=[first,second])))
    assert cli.from_desktop('a'*32)==(0 if terminal else 1)
    assert 'synthetic-local-credential' not in capsys.readouterr().out
