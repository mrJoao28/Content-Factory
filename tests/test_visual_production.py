import copy
import sys
import threading
import time

import pytest
from factory.config import settings
from factory.db import Session
from factory.models import ProductionJob, VideoProject
from factory.queue import claim
from factory.schemas import ProjectCreate
from factory.security import Cancelled, ConfigurationRequired
from factory.storyboard_limits import validate_generated
from factory.visual_demos import demo
from factory.visual_render import blender_info, checked_process, fingerprint, input_manifest, render_3d
from factory.visual_schema import VisualBoard
from test_render import sine


def test_catalog_identity_timing_and_ground_constraints():
    for name, duration in (("slice", 3), ("dino", 8), ("milo", 35), ("engineering", 3)):
        board = demo(name).validate_project(duration, 24)
        assert sum(round(s.duration*24) for s in board.scenes) == duration*24
    data = demo("slice").model_dump(mode="json")
    invalid = copy.deepcopy(data)
    invalid["scenes"][0]["characters"][0]["asset_version"] = "milo-v1"
    with pytest.raises(ValueError, match="version mismatch"):
        VisualBoard.model_validate(invalid)
    invalid = copy.deepcopy(data)
    invalid["scenes"][0]["characters"][0]["position"][2] = .1
    with pytest.raises(ValueError, match="ground"):
        VisualBoard.model_validate(invalid)
    with pytest.raises(ValueError, match="project duration"):
        demo("dino").validate_project(35, 24)


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(python="print('unsafe')"),
    lambda s: s["actions"][0].update(kind="execute"),
    lambda s: s["actions"][0].update(target=[8, 0, 0]),
    lambda s: s["actions"][0].update(end=4),
    lambda s: s["camera"][0].update(time=1),
    lambda s: s.update(particles=10000),
    lambda s: s["characters"][0].update(character_id="unknown"),
    lambda s: s["props"][0].update(file="../../asset.blend"),
])
def test_rejects_unsafe_or_impossible_data(mutation):
    data = demo("slice").model_dump(mode="json")
    mutation(data["scenes"][0])
    with pytest.raises(ValueError):
        VisualBoard.model_validate(data)


def test_generation_validation_before_checkpoint():
    with pytest.raises(ValueError, match="selected character"):
        validate_generated(demo("dino"), {"duration": 8, "fps": 24, "visual_selection": {"character": "milo"}})
    data = demo("dino").model_dump(mode="json")
    data["duration"] = 35
    with pytest.raises(ValueError, match="durations"):
        VisualBoard.model_validate(data)
    with pytest.raises(ValueError, match="contain the selected character"):
        validate_generated(demo("engineering"), {"duration": 3, "channel": "wondernest",
                           "visual_selection": {"character": "dino"}})


def test_voice_validation_rejects_silent_pcm_without_counting_music_as_speech(tmp_path):
    import wave

    from factory.visual_audio import audible_wav
    path = tmp_path/"speech.wav"
    with wave.open(str(path), "wb") as source:
        source.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        source.writeframes(bytes(22050*2))
    with pytest.raises(ConfigurationRequired, match="silent"):
        audible_wav(path)
    sine(path)
    audible_wav(path)


def test_explicit_short_3d_duration_and_conflict():
    for duration in (8, 15, 35):
        body = ProjectCreate(idea=f"An original {duration}-second Dino story", channel_id="wondernest",
                             target_duration=duration, visual={"engine": "blender_3d"})
        assert body.target_duration == duration
    with pytest.raises(ValueError, match="conflicts"):
        ProjectCreate(idea="A 35-second story", target_duration=8, visual={"engine": "blender_3d"})


def test_no_silent_fallback_when_blender_missing(client, monkeypatch):
    monkeypatch.setattr(settings, "blender_path", "definitely-not-installed-blender")
    response = client.post("/projects", json={"idea": "Dino original discovery", "channel_id": "wondernest",
                           "target_duration": 8, "visual": {"engine": "blender_3d"}})
    assert response.status_code == 409
    assert "3D never falls back" in response.json()["detail"]
    assert client.get("/projects").json() == []


def test_regeneration_preserves_script_and_selection_and_invalidates_approval(client, project):
    pid = project["id"]
    script = {"title": "Keep the script", "description": "Original", "beats": ["Beginning", "End"]}
    with Session.begin() as db:
        row = db.get(VideoProject, pid)
        row.script, row.approved_hash = script, "a"*64
        row.storyboard = {"invalid_old_board": True}
        job = db.query(ProductionJob).filter_by(project_id=pid).one()
        selection = job.checkpoint["_ai_selection"]
        job.checkpoint = {**job.checkpoint, "creative_director": {"summary": "Original idea"},
                          "script_writer": script, "storyboard_planner": {"invalid": True}}
        job.state = "FAILED"
    body = {"expected_revision": 1, "confirm_invalidation": True}
    result = client.post(f"/projects/{pid}/visual/regenerate", json=body)
    assert result.status_code == 200, result.text
    current = client.get(f"/projects/{pid}").json()
    assert current["revision"] == 2 and current["script"] == script
    assert current["approved_hash"] is None and current["storyboard"] == {}
    new = next(j for j in current["jobs"] if j["revision"] == 2)
    assert new["checkpoint"]["script_writer"] == script
    assert new["checkpoint"]["_ai_selection"] == selection
    assert "storyboard_planner" not in new["checkpoint"]
    assert client.post(f"/projects/{pid}/visual/regenerate", json=body).status_code == 409
    assert len(client.get(f"/projects/{pid}").json()["jobs"]) == 2


def test_reject_regeneration_with_worker_lease(client, project):
    assert claim("active-renderer")
    response = client.post(f"/projects/{project['id']}/visual/regenerate",
                           json={"expected_revision": 1, "confirm_invalidation": True})
    assert response.status_code == 409
    assert client.get(f"/projects/{project['id']}").json()["revision"] == 1


def test_cache_covers_audio_version_profile_timeline_and_revision(tmp_path):
    audio = tmp_path/"audio.wav"
    sine(audio)
    original = input_manifest(demo("slice"), width=360, height=640, fps=24, quality="preview",
                              revision=1, audio=audio, info={"version": "4.5.5", "device": "CPU"})
    baseline = fingerprint(original)
    for key, value in (("revision", 2), ("quality", "final"), ("fps", 30), ("template_sha256", "other")):
        assert fingerprint({**original, key: value}) != baseline
    assert fingerprint(copy.deepcopy(original)) == baseline


def test_real_child_process_cancellation_and_timeout(tmp_path):
    ready = tmp_path/"ready"
    cancel = threading.Event()
    # This is a trusted test-owned process, never generated content.
    script = tmp_path/"wait.py"
    script.write_text("import time\nfrom pathlib import Path\nPath("+repr(str(ready))+").touch()\ntime.sleep(30)\n", encoding="utf-8")
    def request_cancel():
        deadline = time.monotonic()+10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        cancel.set()
    worker = threading.Thread(target=request_cancel)
    worker.start()
    try:
        with pytest.raises(Cancelled):
            checked_process([sys.executable, script], cancel=cancel.is_set, timeout=15)
    finally:
        worker.join(timeout=2)
    assert ready.exists()
    with pytest.raises(ConfigurationRequired, match="timeout"):
        checked_process([sys.executable, "-c", "import time; time.sleep(5)"], cancel=lambda: False, timeout=.2)


def test_real_blender_export_and_resume_when_installed(tmp_path):
    try:
        blender_info()
    except ConfigurationRequired as exc:
        pytest.skip(str(exc))
    from factory.render import validate_video
    audio = tmp_path/"audio.wav"
    sine(audio, seconds=.5)  # Known test audio, never presented as generated narration.
    board = demo("slice")
    # Real short smoke through the exact production renderer, CPU and 24 FPS.
    data = board.model_dump(mode="json")
    data["duration"] = data["scenes"][0]["duration"] = .5
    data["scenes"][0]["actions"][0].update(end=.5, target=[-.4, 0, 0])
    board = VisualBoard.model_validate(data)
    result = render_3d(board, tmp_path/"video.mp4", width=90, height=160, fps=24, audio=audio)
    assert all(validate_video(tmp_path/"video.mp4", 90, 160, 24, .5)["checks"].values())
    assert result["frames"] == 12
    again = render_3d(board, tmp_path/"video.mp4", width=90, height=160, fps=24, audio=audio)
    assert again["resumed_frames"] == 12


def test_version_check_does_not_claim_render_readiness(client, monkeypatch):
    monkeypatch.setattr(settings, "blender_path", "missing-blender-executable")
    result = client.get("/visual/catalog")
    assert result.status_code == 200
    assert result.json()["blender"]["state"] == "UNAVAILABLE"
    assert result.json()["characters"] == {"dino": "dino-v1", "milo": "milo-v1"}


@pytest.mark.parametrize("version", ["4.5.5", "5.2.0", "5.2.3"])
def test_supported_blender_lts_series(monkeypatch, version):
    import factory.visual_render
    monkeypatch.setattr(settings, "blender_path", sys.executable)
    monkeypatch.setattr(factory.visual_render, "run", lambda *a, **kw: f"Blender {version} LTS\n".encode())
    result = blender_info()
    assert result["version"] == version
    assert (result["engine"], result["device"]) == ("CYCLES", "CPU")


@pytest.mark.parametrize("version", ["3.6.0", "4.4.0", "5.1.0", "5.20.0", "6.0.0"])
def test_unsupported_blender_series_is_not_accepted(monkeypatch, version):
    import factory.visual_render
    monkeypatch.setattr(settings, "blender_path", sys.executable)
    monkeypatch.setattr(factory.visual_render, "run", lambda *a, **kw: f"Blender {version}\n".encode())
    with pytest.raises(ConfigurationRequired, match="4.5 and 5.2"):
        blender_info()


def test_creation_persists_visual_snapshot_without_changing_text_provider(client, monkeypatch):
    import factory.visual_render
    # External executable version probe only. No render is simulated or reported.
    monkeypatch.setattr(settings, "blender_path", sys.executable)
    monkeypatch.setattr(factory.visual_render, "run", lambda *a, **kw: b"Blender 4.5.5\n")
    response = client.post("/projects", json={"idea": "Milo's original fifteen-second garden adventure",
                           "channel_id": "wondernest", "target_duration": 15,
                           "visual": {"engine": "blender_3d", "character": "milo", "environment": "dusk_garden"}})
    assert response.status_code == 201, response.text
    result = client.get("/projects/"+response.json()["id"]).json()
    assert result["visual_config"]["engine"] == "blender_3d"
    assert result["visual_config"]["character"] == "milo"
    assert (result["width"], result["height"], result["fps"]) == (360, 640, 24)
    assert result["jobs"][0]["checkpoint"]["_ai_selection"]["provider"] == "codex"
    assert not result["artifacts"]


def test_real_blender_queue_to_review_when_installed(client, monkeypatch):
    try:
        blender_info()
    except ConfigurationRequired as exc:
        pytest.skip(str(exc))
    import factory.codex
    from factory.queue import Worker
    from factory.schemas import AgentResult, Metadata, Script
    project = client.post("/projects", json={"idea": "Dino real Blender integration test",
                          "channel_id": "wondernest", "target_duration": 8,
                          "visual": {"engine": "blender_3d"}}).json()
    plan = demo("slice").model_dump(mode="json")
    plan["duration"] = plan["scenes"][0]["duration"] = .5
    plan["scenes"][0]["actions"][0].update(end=.5, target=[-.4, 0, 0])
    board = VisualBoard.model_validate(plan)
    sine(settings.storage_root/"test-voice.wav", seconds=.5)
    with Session.begin() as db:
        row = db.get(VideoProject, project["id"])
        row.target_duration, row.width, row.height = .5, 90, 160
        row.narration = {"path": "test-voice.wav"}

    def generate(self, role, context, response_type, **kwargs):
        assert context["visual_catalog"]["version"] == "factory-3d-v1"
        if response_type is VisualBoard:
            return board
        if response_type is Script:
            return Script(title="Dino's discovery", description="Original fixture", beats=["Discover", "Wonder"])
        if response_type is Metadata:
            return Metadata(title="Dino's discovery", description="Original fixture", tags=["original"])
        return AgentResult(summary="External text fixture; human review required")

    monkeypatch.setattr(factory.codex.CodexProvider, "generate", generate)
    assert Worker().once()
    result = client.get("/projects/"+project["id"]).json()
    assert result["status"] == "HUMAN_REVIEW", result["jobs"]
    assert len(result["artifacts"]) == 1 and result["approved_hash"] is None
    assert result["artifacts"][0]["probe"]["visual"]["engine"] == "blender_3d"
    assert all(result["artifacts"][0]["probe"]["checks"].values())
