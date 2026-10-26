import pytest
from factory.audio import Piper
from factory.codex import CodexProvider, strict_schema
from factory.schemas import AgentResult
from factory.security import ConfigurationRequired


def test_codex_auth_required_without_fake_content(monkeypatch):
    import factory.codex

    monkeypatch.setattr(factory.codex, "auth_status", lambda: {"state": "AUTH_REQUIRED"})
    provider = CodexProvider()
    with pytest.raises(ConfigurationRequired):
        provider.generate("Script Writer", {"idea": "A garden"}, AgentResult)
    assert provider.history == []


def test_structured_output_schema_is_strict():
    schema = strict_schema(AgentResult.model_json_schema())
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_piper_missing_voice_is_actionable(monkeypatch):
    from factory.config import settings

    monkeypatch.setattr(settings, "piper_path", "")
    with pytest.raises(ConfigurationRequired, match="import narration"):
        Piper().generate("A little robot waves.")


def test_official_cli_jsonl_stream_and_process_cleanup(monkeypatch, tmp_path):
    import sys

    import factory.codex
    from factory.config import settings

    script = tmp_path / "external_cli_fixture.py"
    script.write_text(
        "import sys,json\nsys.stdin.read()\nprint(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps({'summary':'Validated fixture','flags':[]})}}),flush=True)\n"
    )
    monkeypatch.setattr(factory.codex, "auth_status", lambda: {"state": "READY"})
    monkeypatch.setattr(factory.codex, "executable", lambda: [sys.executable, str(script)])
    monkeypatch.setattr(settings, "codex_provider", "cli")
    events = []
    result = CodexProvider().generate(
        "Creative Director", {"idea": "An original garden"}, AgentResult, emit=events.append
    )
    assert result.summary == "Validated fixture" and "item.completed" in events
    assert not list(settings.storage_root.glob("codex-*"))
    script.write_text("import time,sys\nsys.stdin.read()\ntime.sleep(20)\n")
    monkeypatch.setattr(settings, "codex_timeout_seconds", 1)
    from factory.security import TransientFailure

    with pytest.raises(TransientFailure, match="timed out"):
        CodexProvider().generate("Creative Director", {}, AgentResult)
