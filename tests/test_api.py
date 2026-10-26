import io
from datetime import timedelta

import pytest
from PIL import Image
from sqlalchemy import select, text

from factory.config import settings
from factory.db import Session
from factory.models import RenderArtifact, VideoProject, utcnow
from factory.security import digest


def test_channels_and_dashboard(client):
    assert len(client.get("/channels").json()) == 2
    metrics = client.get("/dashboard").json()
    assert metrics["projects"] == 0
    assert metrics["average_render_seconds"] is None
    assert metrics["external_metrics"] is None
    assert len(client.get("/series?channel_id=wondernest").json()) == 5
    with Session() as db:
        assert db.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_crud_duplicate_edit_and_resume(client, project):
    assert client.get("/projects/"+project["id"]).json()["jobs"][0]["state"] == "DRAFT"
    duplicate = client.post("/projects", json={"idea": " A SMALL robot discovers a garden ", "channel_id": "wondernest"})
    assert duplicate.status_code == 409
    script = {"title": "The garden", "description": "An original story", "beats": ["Robot meets a flower"], "sources": [], "safety_notes": []}
    response = client.patch("/projects/"+project["id"], json={"script": script})
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert response.json()["approved_hash"] is None
    job = client.post(f"/projects/{project['id']}/jobs/resume", json={}).json()
    again = client.post(f"/projects/{project['id']}/jobs/resume", json={}).json()
    assert job["id"] == again["id"]


@pytest.mark.parametrize("body", [
    {"idea": "tiny"}, {"idea": "A story", "channel_id": "wondernest", "target_duration": 90},
    {"idea": "An engine", "channel_id": "how-it-works", "target_duration": 30},
    {"idea": "A story", "channel_id": "wondernest", "content_type": "episode", "target_duration": 40},
    {"idea": "A story", "unknown": "injected"},
])
def test_invalid_projects(client, body):
    assert client.post("/projects", json=body).status_code == 422


def test_channel_routing(client):
    kids = client.post("/projects", json={"idea": "A magical story for children"}).json()
    adult = client.post("/projects", json={"idea": "Explain how an engine works"}).json()
    assert kids["channel_id"] == "wondernest" and kids["target_duration"] == 35
    assert adult["channel_id"] == "how-it-works" and adult["target_duration"] == 75


def test_series_and_characters(client):
    series = client.post("/series", json={"channel_id": "wondernest", "name": "Ocean Friends", "style": {"palette": "blue"}}).json()
    char = client.post("/characters", json={"series_id": series["id"], "name": "Pearl", "description": "An original curious fish"})
    assert char.status_code == 201
    cid = char.json()["id"]
    assert client.patch("/characters/"+cid, json={"series_id": series["id"], "name": "Pearl II"}).status_code == 200
    assert client.delete("/library/series/"+series["id"]).status_code == 409
    assert client.delete("/library/characters/"+cid).status_code == 200
    assert client.delete("/library/series/"+series["id"]).status_code == 200


def test_asset_import_deduplication(client):
    buffer = io.BytesIO()
    Image.new("RGBA", (32,32), "#64e8cf").save(buffer, "PNG")
    payload = buffer.getvalue()
    first = client.post("/assets?license=Original&kind=prop", files={"file": ("star.png", payload, "image/png")})
    assert first.status_code == 201, first.text
    second = client.post("/assets?license=Original&kind=prop", files={"file": ("copy.png", payload, "image/png")})
    assert first.json()["id"] == second.json()["id"]
    assert client.get(f"/assets/{first.json()['id']}/image").content == payload
    assert client.post("/assets?license=Original", files={"file": ("bad.svg", b"<svg/>")}).status_code == 422
    assert client.post("/assets", files={"file": ("star.png", payload)}).status_code == 422


def test_calendar_conflict_and_timezone(client, project):
    second = client.post("/projects", json={"idea": "A rabbit sees a rainbow", "channel_id": "wondernest"}).json()
    when = (utcnow()+timedelta(days=2)).isoformat()
    body = {"scheduled_at": when, "timezone": "America/Manaus", "mode": "manual"}
    assert client.post(f"/projects/{project['id']}/schedule", json=body).json()["status"] == "PLANNED"
    assert client.post(f"/projects/{second['id']}/schedule", json=body).status_code == 409
    body["scheduled_at"] = "2030-01-01T12:00:00"
    assert client.post(f"/projects/{second['id']}/schedule", json=body).status_code == 422
    assert client.delete(f"/projects/{project['id']}/schedule").status_code == 200


def test_review_and_publication_guard(client, project):
    pid = project["id"]
    assert client.post(f"/projects/{pid}/publish/youtube", json={"confirm": True}).status_code == 422
    assert client.post(f"/projects/{pid}/manual-package", json={}).status_code == 422
    file = settings.output_dir / pid / "1/video.mp4"
    file.parent.mkdir(parents=True)
    # Synthetic bytes only test the approval guard; never treated as a real render.
    file.write_bytes(b"guard-test-artifact")
    hashed = digest(file)
    with Session.begin() as db:
        db.add(RenderArtifact(project_id=pid, revision=1, path=str(file.relative_to(settings.output_dir)),
                              sha256=hashed, probe={"checks": {"codec": True}}, render_seconds=1))
        db.get(VideoProject,pid).metadata_json = {"title": "A robot"}
    body = {"approved": True, "notes": "Reviewed all scenes", "artifact_hash": hashed}
    assert client.post(f"/projects/{pid}/review", json={**body, "artifact_hash": "0"*64}).status_code == 409
    assert client.post(f"/projects/{pid}/review", json=body).status_code == 200
    file.write_bytes(b"modified")
    assert client.post(f"/projects/{pid}/manual-package", json={}).status_code == 422


def test_csrf_origin_host_and_path_guards(client, project):
    assert client.post("/projects", json={"idea": "Injected request"}, headers={"X-Factory-Client": ""}).status_code == 403
    assert client.get("/channels", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/channels", headers={"Host": "evil.example"}).status_code == 400
    from factory.security import safe_path
    with pytest.raises(ValueError):
        safe_path(settings.storage_root, "../.env")
    with pytest.raises(ValueError):
        safe_path(settings.storage_root, "C:/Windows/win.ini")
    assert client.get(f"/projects/{project['id']}/media/../../.env").status_code == 404


def test_events_and_preference_validation(client, project):
    rows = client.get("/events").json()
    assert rows[0]["project_id"] == project["id"]
    assert client.get(f"/events?after={rows[-1]['id']}").json() == []
    assert client.patch("/settings", json={"timezone": "America/Manaus"}).status_code == 200
    assert client.patch("/settings", json={"auto_publish": True}).status_code == 422



def test_imported_narration_invalidates_artifact_revision(client,project,tmp_path):
    from factory.render import ffprobe
    from factory.security import ConfigurationRequired
    from test_render import sine
    try:ffprobe()
    except ConfigurationRequired as exc:pytest.skip(str(exc))
    pid=project["id"]
    voice=tmp_path/"narration.wav";sine(voice)
    with Session.begin() as db:
        db.get(VideoProject,pid).approved_hash="1"*64
    response=client.post(f"/projects/{pid}/audio",files={"file":("narration.wav",voice.read_bytes(),"audio/wav")})
    assert response.status_code==200,response.text
    detail=client.get("/projects/"+pid).json()
    assert detail["approved_hash"] is None and detail["revision"]==2
    assert client.get(f"/projects/{pid}/media/video").status_code==404
    assert client.patch("/settings",json={"timezone":"Not/AZone"}).status_code==422



def test_music_import_and_mix_revision(client,project,tmp_path):
    from factory.render import ffprobe
    from factory.security import ConfigurationRequired
    from test_render import sine
    try:ffprobe()
    except ConfigurationRequired as exc:pytest.skip(str(exc))
    voice=tmp_path/"music.wav";sine(voice)
    result=client.post("/assets/audio?license=Original&kind=music",files={"file":("music.wav",voice.read_bytes(),"audio/wav")})
    assert result.status_code==201,result.text
    asset=result.json()
    assert client.get(f"/assets/{asset['id']}/audio").status_code==200
    assert client.get(f"/assets/{asset['id']}/image").status_code==404
    pid=project["id"]
    mix=client.patch(f"/projects/{pid}/audio-mix",json={"music_asset_id":asset["id"],"music_volume":.12})
    assert mix.status_code==200 and mix.json()["revision"]==2
    assert client.patch(f"/projects/{pid}/audio-mix",json={"effects":[{"asset_id":asset["id"],"time":100}]}).status_code==422
