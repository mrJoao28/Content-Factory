import json
import time
from datetime import timedelta

import httpx
import pytest
from PIL import Image

from factory.config import settings
from factory.db import Session
from factory.integrations import Google, OAuth, TikTok
from factory.models import RenderArtifact, VideoProject, utcnow
from factory.security import digest
from test_integrations import MemoryVault


def ready(client,channel="wondernest"):
    response=client.post("/projects",json={"idea":"An original test video "+channel,"channel_id":channel})
    pid=response.json()["id"]
    path=settings.output_dir/pid/"1/video.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"publishing-guard-fixture-only")
    Image.new("RGB",(320,180),"#64e8cf").save(path.parent/"thumbnail.png")
    hashed=digest(path)
    with Session.begin() as db:
        db.add(RenderArtifact(project_id=pid,revision=1,path=str(path.relative_to(settings.output_dir)),sha256=hashed,
                              probe={"checks":{"guard_fixture":True}},render_seconds=1))
        project=db.get(VideoProject,pid)
        project.approved_hash=hashed
        project.metadata_json={"title":"An original test video","description":"Fixture","tags":["Original"]}
    return pid


def test_youtube_resumable_made_for_kids_schedule_thumbnail_and_status(client,monkeypatch):
    calls=[]
    def respond(request):
        calls.append(request)
        if "channels" in request.url.path:
            return httpx.Response(200,json={"items":[{"id":"UC-test","statistics":{"viewCount":"12"}}]})
        if "thumbnails" in request.url.path:return httpx.Response(200,json={"items":[{"default":{"url":"https://example.test/thumbnail"}}]})
        if request.method=="GET":return httpx.Response(200,json={"items":[{"id":"test-video","status":{"privacyStatus":"public","uploadStatus":"processed"}}]})
        if request.method=="POST":return httpx.Response(200,headers={"location":"https://www.googleapis.com/upload/test-session"})
        return httpx.Response(200,json={"id":"test-video","status":{"privacyStatus":"private"}})
    transport=httpx.Client(transport=httpx.MockTransport(respond))
    vault=MemoryVault();vault.put("youtube",{"access_token":"test","expires_at":time.time()+3600})
    oauth=OAuth(client=transport,vault=vault)
    monkeypatch.setattr(settings,"youtube_channel_id","UC-test")
    monkeypatch.setattr("factory.publishing.Google",lambda platform:Google(platform,client=transport,oauth=oauth))
    monkeypatch.setattr("factory.integrations.Google",lambda platform:Google(platform,client=transport,oauth=oauth))
    pid=ready(client)
    assert client.post(f"/projects/{pid}/schedule",json={"scheduled_at":(utcnow()+timedelta(days=2)).isoformat(),"timezone":"America/Manaus","mode":"youtube"}).status_code==200
    response=client.post(f"/projects/{pid}/publish/youtube",json={"confirm":True,"privacy":"public"})
    assert response.status_code==200,response.text
    publication=response.json()
    assert publication["status"]=="UPLOADED"
    body=json.loads(next(r for r in calls if "upload/youtube/v3/videos" in r.url.path).content)
    assert body["status"]["selfDeclaredMadeForKids"] is True
    assert body["status"]["privacyStatus"]=="private" and body["status"]["publishAt"].endswith("Z")
    assert client.post(f"/projects/{pid}/publish/youtube",json={"confirm":True}).json()["id"]==publication["id"]
    assert len([r for r in calls if r.method=="POST" and "upload/youtube/v3/videos" in r.url.path])==1
    assert client.post(f"/publications/{publication['id']}/thumbnail",json={}).json()["confirmed"]
    assert client.post(f"/publications/{publication['id']}/refresh",json={}).json()["status"]=="PUBLISHED"


def test_tiktok_direct_requires_external_permission_and_explicit_consent(client,monkeypatch):
    pid=ready(client,"how-it-works")
    body={"confirm":True,"music_usage_confirmed":True,"title":"Gears #engineering","privacy_level":"SELF_ONLY",
          "disable_duet":True,"disable_stitch":True,"disable_comment":True,"brand_content_toggle":False,"brand_organic_toggle":False}
    assert client.post(f"/projects/{pid}/tiktok-direct",json=body).status_code==409
    monkeypatch.setattr(settings,"tiktok_direct_post_enabled",True)
    calls=[]
    def respond(request):
        calls.append(request)
        if "creator_info" in request.url.path:data={"privacy_level_options":["SELF_ONLY"],"max_video_post_duration_sec":90,"comment_disabled":True}
        elif request.method=="PUT":return httpx.Response(201)
        else:data={"publish_id":"direct-test","upload_url":"https://open-upload.tiktokapis.com/video/test"}
        return httpx.Response(200,json={"error":{"code":"ok"},"data":data})
    transport=httpx.Client(transport=httpx.MockTransport(respond))
    vault=MemoryVault();vault.put("tiktok",{"access_token":"test","expires_at":time.time()+3600,"scope":"user.info.basic,video.publish"})
    oauth=OAuth(client=transport,vault=vault)
    monkeypatch.setattr("factory.publishing.TikTok",lambda:TikTok(client=transport,oauth=oauth))
    assert client.post(f"/projects/{pid}/tiktok-direct",json={**body,"confirm":False}).status_code==422
    assert client.post(f"/projects/{pid}/tiktok-direct",json={**body,"privacy_level":"PUBLIC_TO_EVERYONE"}).status_code==422
    response=client.post(f"/projects/{pid}/tiktok-direct",json=body)
    assert response.status_code==200,response.text
    assert response.json()["status"]=="UPLOADED"
    request=next(r for r in calls if r.url.path.endswith("/video/init/"))
    assert json.loads(request.content)["post_info"]["is_aigc"] is True
    assert client.post(f"/projects/{pid}/tiktok-direct",json=body).status_code==422


def test_batch_reports_duplicates_without_losing_successes(client):
    idea={"channel_id":"wondernest","idea":"A small fox discovers the seasons"}
    response=client.post("/projects/batch",json={"ideas":[idea,idea,{**idea,"idea":"A little bird discovers a rainbow"}]})
    assert response.status_code==207,response.text
    result=response.json()
    assert len(result["projects"])==2 and len(result["errors"])==1
    assert len(client.get("/projects").json())==2
