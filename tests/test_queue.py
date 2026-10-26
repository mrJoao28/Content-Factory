from datetime import timedelta

import pytest
from sqlalchemy import select

from factory.db import Session
from factory.models import ProductionJob, VideoProject, utcnow
from factory.queue import Worker, checkpoint, claim, controlled, enqueue
from factory.security import Cancelled, ConfigurationRequired, TransientFailure


def test_atomic_claim_recovery_and_idempotence(project):
    with Session.begin() as db:
        p = db.get(VideoProject, project["id"])
        first = enqueue(db,p)
        second = enqueue(db,p)
        assert first.id == second.id
    job_id = claim("worker-a")
    assert job_id
    assert claim("worker-b") is None
    assert controlled(job_id,"worker-b")
    checkpoint(job_id,"worker-a","SCRIPTING","director",{"summary":"Saved"})
    with Session.begin() as db:
        db.get(ProductionJob,job_id).lease_until = utcnow()-timedelta(seconds=1)
    assert claim("worker-b") == job_id
    with Session() as db:
        assert db.get(ProductionJob,job_id).checkpoint["director"]["summary"] == "Saved"
    with pytest.raises(Cancelled):
        checkpoint(job_id,"worker-a","RENDERING")


def test_pause_cancel_and_resume(client,project):
    pid=project["id"]
    assert client.post(f"/projects/{pid}/jobs/pause",json={}).json()["state"] == "PAUSED"
    assert claim("worker-a") is None
    assert client.post(f"/projects/{pid}/jobs/resume",json={}).json()["state"] == "DRAFT"
    jid=claim("worker-a")
    assert client.patch(f"/projects/{pid}",json={"metadata":{"title":"Title","description":"","tags":[]}}).status_code == 409
    assert client.post(f"/projects/{pid}/jobs/cancel",json={}).json()["state"] == "CANCELLED"
    assert controlled(jid,"worker-a")


@pytest.mark.parametrize("error,state,attempts",[(ConfigurationRequired("ChatGPT authentication required"),"WAITING_FOR_AUTH",0),
    (ConfigurationRequired("Missing voice"),"WAITING_FOR_ASSETS",0),(TransientFailure("Limit reached"),"DRAFT",1),
    (ValueError("Invalid duration"),"FAILED",0)])
def test_worker_failure_states(project,monkeypatch,error,state,attempts):
    import factory.pipeline
    def fail(*args,**kwargs):
        raise error
    monkeypatch.setattr(factory.pipeline,"produce",fail)
    assert Worker().once()
    with Session() as db:
        job=db.scalar(select(ProductionJob).where(ProductionJob.project_id==project["id"]))
        assert job.state==state and job.attempts==attempts
        assert job.owner is None and job.lease_until is None
        if attempts:
            assert job.available_at.replace(tzinfo=utcnow().tzinfo)>utcnow()
