import importlib.util
from unittest.mock import MagicMock
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("documind_launcher", Path(__file__).resolve().parents[2] / "launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_ollama_settings_are_scoped_and_override_large_inherited_context():
    original = {"OLLAMA_CONTEXT_LENGTH":"65536", "DOCUMIND_OLLAMA_PORT":"21434", "DOCUMIND_OLLAMA_KV_CACHE_TYPE":"q8_0"}
    result = launcher.ollama_environment(original)
    assert original["OLLAMA_CONTEXT_LENGTH"] == "65536"
    assert result["OLLAMA_CONTEXT_LENGTH"] == "8192"
    assert result["OLLAMA_FLASH_ATTENTION"] == "1" and result["OLLAMA_KV_CACHE_TYPE"] == "q8_0"
    assert result["OLLAMA_HOST"] == "127.0.0.1:21434"
    assert result["OLLAMA_KEEP_ALIVE"] == "15m" and result["OLLAMA_NUM_PARALLEL"] == "1"


@pytest.mark.parametrize("settings", [{"DOCUMIND_OLLAMA_PORT":"70000"}, {"DOCUMIND_OLLAMA_KV_CACHE_TYPE":"invalid"}])
def test_invalid_ollama_configuration_is_rejected(settings):
    with pytest.raises(ValueError):
        launcher.ollama_environment(settings)


def test_existing_ollama_server_is_not_restarted(monkeypatch):
    response = MagicMock()
    response.__enter__.return_value.status = 200
    monkeypatch.setattr(launcher.urllib.request, "urlopen", lambda *args, **kwargs: response)
    spawn = MagicMock(side_effect=AssertionError("Must not spawn another server"))
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    assert launcher.start_ollama_if_needed() is None
    spawn.assert_not_called()


def test_shutdown_only_targets_owned_server(monkeypatch):
    run = MagicMock()
    monkeypatch.setattr(launcher.subprocess, "run", run)
    launcher.stop_owned_ollama(None)
    run.assert_not_called()
    process = MagicMock(pid=12345)
    process.poll.return_value = None
    launcher.stop_owned_ollama(process)
    if launcher.os.name == "nt":
        assert run.call_args.args[0] == ["taskkill", "/PID", "12345", "/T", "/F"]
    else:
        process.terminate.assert_called_once()


def test_classic_frontend_remains_available(monkeypatch):
    monkeypatch.setattr(launcher,"UI_MODE","classic")
    command,cwd=launcher.frontend_command()
    assert "streamlit" in command and cwd==launcher.ROOT


def test_missing_web_build_has_actionable_setup_message(monkeypatch,tmp_path):
    monkeypatch.setattr(launcher,"UI_MODE","next")
    monkeypatch.setattr(launcher,"ROOT",tmp_path)
    with pytest.raises(RuntimeError,match="npm ci"):
        launcher.frontend_command()


@pytest.mark.parametrize("url",["http://example.test:3100","https://127.0.0.1:3100","http://127.0.0.1"])
def test_frontend_url_must_match_a_local_http_server(monkeypatch,url):
    monkeypatch.setattr(launcher,"FRONTEND_URL",url)
    with pytest.raises(ValueError,match="local HTTP"):
        launcher.frontend_command()


def test_classic_port_matches_configured_browser_url(monkeypatch):
    monkeypatch.setattr(launcher,"UI_MODE","classic")
    monkeypatch.setattr(launcher,"FRONTEND_URL","http://127.0.0.1:6200")
    assert "--server.port=6200" in launcher.frontend_command()[0]


def test_next_launcher_uses_direct_node_process_and_built_app(monkeypatch,tmp_path):
    root=tmp_path/"documind-web"
    cli=root/"node_modules"/"next"/"dist"/"bin"/"next"
    cli.parent.mkdir(parents=True);cli.write_text("test entry")
    (root/".next").mkdir();(root/".next"/"BUILD_ID").write_text("test build")
    monkeypatch.setattr(launcher,"ROOT",tmp_path)
    monkeypatch.setattr(launcher,"UI_MODE","next")
    monkeypatch.setattr(launcher,"FRONTEND_URL","http://127.0.0.1:3100")
    monkeypatch.setattr(launcher.shutil,"which",lambda _:"node.exe")
    command,cwd=launcher.frontend_command()
    assert command==["node.exe",str(cli),"start","--hostname","127.0.0.1","--port","3100"] and cwd==root
    assert launcher.frontend_command("http://127.0.0.1:4400")[0][-1] == "4400"


def test_reserved_frontend_port_uses_first_bindable_fallback(monkeypatch):
    probe = MagicMock()
    probe.__enter__.return_value = probe
    probe.bind.side_effect = [PermissionError("Windows reserved this port"), OSError("In use"), None]
    monkeypatch.setattr(launcher.socket, "socket", lambda *args: probe)
    assert launcher.choose_frontend_url("http://127.0.0.1:4317") == "http://127.0.0.1:4401"
    assert [call.args[0][1] for call in probe.bind.call_args_list] == [4317, 4400, 4401]


def test_available_frontend_port_is_preserved(monkeypatch):
    probe = MagicMock()
    probe.__enter__.return_value = probe
    monkeypatch.setattr(launcher.socket, "socket", lambda *args: probe)
    assert launcher.choose_frontend_url("http://127.0.0.1:4317") == "http://127.0.0.1:4317"


def test_exhausted_frontend_ports_have_actionable_error(monkeypatch):
    probe = MagicMock()
    probe.__enter__.return_value = probe
    probe.bind.side_effect = OSError("Unavailable")
    monkeypatch.setattr(launcher.socket, "socket", lambda *args: probe)
    with pytest.raises(RuntimeError, match="No frontend port"):
        launcher.choose_frontend_url("http://127.0.0.1:4317")


def test_exited_frontend_fails_readiness_without_waiting(monkeypatch):
    process = MagicMock()
    process.poll.return_value = 1
    request = MagicMock(side_effect=AssertionError("An exited process cannot become ready"))
    monkeypatch.setattr(launcher.urllib.request, "urlopen", request)
    assert not launcher.wait_for_url("http://127.0.0.1:4400", process=process)
    request.assert_not_called()


def test_launcher_checks_docker_engine_not_just_cli(monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda _: "docker.exe")
    run = MagicMock()
    run.return_value.returncode = 1
    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.main() == 1
    assert run.call_args.args[0] == ["docker", "info", "--format", "{{.ServerVersion}}"]

def test_selected_library_overrides_generic_ollama_location(monkeypatch,tmp_path):
    monkeypatch.setattr(launcher,'ROOT',tmp_path)
    monkeypatch.delenv('DOCUMIND_MODEL_DIRECTORY',raising=False)
    monkeypatch.setenv('OLLAMA_MODELS','old-location')
    (tmp_path/'.env').write_text('DOCUMIND_MODEL_DIRECTORY='+str(tmp_path/'chosen-models'))
    assert launcher.load_project_environment()['OLLAMA_MODELS']==str(tmp_path/'chosen-models')

def test_changed_library_does_not_kill_a_foreign_server(monkeypatch,tmp_path):
    monkeypatch.setattr(launcher,'ENVIRONMENT',{'DOCUMIND_OLLAMA_PORT':'21434','DOCUMIND_MODEL_DIRECTORY':str(tmp_path/'models'),'OLLAMA_MODELS':str(tmp_path/'models')})
    response=MagicMock();response.__enter__.return_value.status=200
    monkeypatch.setattr(launcher.urllib.request,'urlopen',lambda *a,**kw:response)
    probe=MagicMock();probe.__enter__.return_value=probe;probe.bind.side_effect=[OSError('in use'),None]
    monkeypatch.setattr(launcher.socket,'socket',lambda *a:probe)
    monkeypatch.setattr(launcher.shutil,'which',lambda *a:'ollama')
    process=MagicMock();spawn=MagicMock(return_value=process)
    monkeypatch.setattr(launcher.subprocess,'Popen',spawn)
    monkeypatch.setattr(launcher,'wait_for_url',lambda *a,**kw:True)
    assert launcher.start_ollama_if_needed() is process
    assert spawn.call_args.kwargs['env']['OLLAMA_HOST']=='127.0.0.1:21435'
    assert launcher.ENVIRONMENT['DOCUMIND_OLLAMA_PORT']=='21435'
