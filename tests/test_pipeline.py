from pathlib import Path

import pytest

from factory.config import settings
from factory.db import Session
from factory.models import ProductionJob, RenderArtifact, VideoProject
from factory.queue import Worker
from factory.schemas import AgentResult, Board, Metadata, Script
from factory.security import ConfigurationRequired
from test_render import board, sine


@pytest.mark.parametrize("channel",["wondernest","how-it-works"])
def test_real_pipeline_with_only_ai_external_response_mocked(client,monkeypatch,channel):
    from factory.render import ffmpeg, ffprobe
    try:ffmpeg();ffprobe()
    except ConfigurationRequired as exc:pytest.skip(str(exc))
    project=client.post("/projects",json={"idea":"An original story about mechanisms "+channel,"channel_id":channel}).json()
    pid=project["id"]
    audio=settings.storage_root/"voice.wav";sine(audio)
    called=[]
    def generate(self,role,context,response_type,**kwargs):
        called.append(role)
        if response_type is Script:return Script(title="A gentle discovery",description="Authored test fixture",beats=["Discover","Explore","Share"])
        if response_type is Board:return board()
        if response_type is Metadata:return Metadata(title="A gentle discovery",description="Authored test fixture",tags=["Original"])
        return AgentResult(summary="Review test fixture",flags=["Human verification required"])
    import factory.codex
    monkeypatch.setattr(factory.codex.CodexProvider,"generate",generate)
    with Session.begin() as db:
        row=db.get(VideoProject,pid)
        row.target_duration=2;row.width=160;row.height=284
        row.narration={"path":"voice.wav"}
    assert Worker().once()
    detail=client.get("/projects/"+pid).json()
    assert detail["status"]=="HUMAN_REVIEW",detail["jobs"]
    assert len(called)==7
    artifact=detail["artifacts"][0]
    assert all(artifact["probe"]["checks"].values())
    assert client.get(f"/projects/{pid}/media/video").headers["content-type"]=="video/mp4"
    assert client.post(f"/projects/{pid}/manual-package",json={}).status_code==422
    assert client.post(f"/projects/{pid}/review",json={"approved":True,"notes":"Full playback and source review completed","artifact_hash":artifact["sha256"],"scientific_sources_checked":True}).status_code==200
    assert client.post(f"/projects/{pid}/manual-package",json={}).status_code==200
    package=client.get(f"/projects/{pid}/manual-package")
    assert package.status_code==200 and package.content[:2]==b"PK"
