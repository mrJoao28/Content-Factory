"""SQLite leased queue. BEGIN IMMEDIATE serializes claims across API/worker processes."""
import json
import threading
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, text

from .db import Session
from .models import JobEvent, ProductionJob, VideoProject, utcnow
from .security import Cancelled

ACTIVE = {"DRAFT", "SCRIPTING", "STORYBOARDING", "ASSET_CHECK", "AUDIO_GENERATION", "RENDERING", "TECHNICAL_VALIDATION"}
WAITING = {"WAITING_FOR_AUTH", "WAITING_FOR_ASSETS", "FAILED", "PAUSED"}


def event(project_id, stage, message, level="info"):
    with Session.begin() as db:
        db.add(JobEvent(project_id=project_id, stage=stage, message=message[:4000], level=level))


def enqueue(db, project):
    existing = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project.id,
                                                    ProductionJob.revision == project.revision))
    if existing:
        return existing
    job = ProductionJob(project_id=project.id, revision=project.revision)
    db.add(job)
    db.flush()
    return job


def claim(owner):
    with Session() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        now = utcnow()
        busy = db.scalar(select(ProductionJob.id).where(ProductionJob.owner.is_not(None),
                                                        ProductionJob.lease_until > now).limit(1))
        if busy:
            db.rollback()
            return None
        job = db.scalar(select(ProductionJob).where(ProductionJob.state.in_(ACTIVE),
                                                    ProductionJob.available_at <= now)
                        .order_by(ProductionJob.created_at).limit(1))
        if not job:
            db.rollback()
            return None
        job.owner = owner
        job.lease_until = now+timedelta(seconds=45)
        db.commit()
        return job.id


def controlled(job_id, owner):
    with Session() as db:
        job = db.get(ProductionJob, job_id)
        project = db.get(VideoProject, job.project_id) if job else None
        return (not job or job.owner != owner or job.state in {"CANCELLED", "PAUSED"} or
                not project or project.revision != job.revision)


def checkpoint(job_id, owner, stage, key=None, value=None):
    with Session.begin() as db:
        job = db.get(ProductionJob, job_id)
        if not job or job.owner != owner or job.state in {"CANCELLED", "PAUSED"}:
            raise Cancelled("Job no longer owned")
        project = db.get(VideoProject, job.project_id)
        if project.revision != job.revision:
            raise Cancelled("Project changed during production")
        if key:
            job.checkpoint = {**job.checkpoint, key: value}
        job.state = stage
        project.status = stage
        job.lease_until = utcnow()+timedelta(seconds=45)
    event(job.project_id, stage, key or stage)


class Worker:
    def __init__(self):
        self.owner = str(uuid4())
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True, name="factory-worker")
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=8)

    def heartbeat(self, job_id, finished):
        while not finished.wait(10):
            with Session.begin() as db:
                job = db.get(ProductionJob, job_id)
                if not job or job.owner != self.owner:
                    return
                job.lease_until = utcnow()+timedelta(seconds=45)

    def once(self):
        from .pipeline import produce
        from .security import ConfigurationRequired, TransientFailure
        job_id = claim(self.owner)
        if not job_id:
            return False
        done = threading.Event()
        pulse = threading.Thread(target=self.heartbeat, args=(job_id, done), daemon=True)
        pulse.start()
        try:
            produce(job_id, self.owner, cancel=lambda: self.stop.is_set() or controlled(job_id, self.owner))
        except Exception as exc:
            with Session.begin() as db:
                job = db.get(ProductionJob, job_id)
                project = db.get(VideoProject, job.project_id)
                if job.owner != self.owner:
                    return True
                if isinstance(exc, Cancelled):
                    if job.state not in {"CANCELLED", "PAUSED"}:
                        job.state = "DRAFT" if self.stop.is_set() else "CANCELLED"
                elif isinstance(exc, ConfigurationRequired):
                    job.state = "WAITING_FOR_AUTH" if "authentication" in str(exc).lower() else "WAITING_FOR_ASSETS"
                elif isinstance(exc, TransientFailure) and job.attempts < 3:
                    job.attempts += 1
                    job.state = "DRAFT"
                    job.available_at = utcnow()+timedelta(seconds=min(300, 5*2**job.attempts))
                else:
                    job.state = "FAILED"
                # Exceptions contain only controlled messages; never response bodies or tokens.
                job.error = str(exc)[:1000] if isinstance(exc, (ConfigurationRequired, Cancelled, ValueError, TransientFailure)) else type(exc).__name__+": check local tool configuration"
                if project.revision == job.revision:
                    project.status = job.state
                db.add(JobEvent(project_id=project.id, stage=job.state, level="error", message=job.error))
        finally:
            done.set()
            pulse.join(timeout=2)
            with Session.begin() as db:
                job = db.get(ProductionJob, job_id)
                if job and job.owner == self.owner:
                    job.owner = None
                    job.lease_until = None
        return True

    def loop(self):
        while not self.stop.is_set():
            try:
                worked = self.once()
            except Exception as exc:
                event(None, "worker", type(exc).__name__, "error")
                worked = False
            if not worked:
                self.stop.wait(1)


if __name__ == "__main__":
    worker = Worker()
    try:
        worker.loop()
    except KeyboardInterrupt:
        worker.close()
