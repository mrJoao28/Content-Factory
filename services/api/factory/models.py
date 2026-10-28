from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Entity:
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserSettings(Entity, Base):
    __tablename__ = "user_settings"
    values: Mapped[dict] = mapped_column(JSON, default=dict)


class Channel(Entity, Base):
    __tablename__ = "channels"
    name: Mapped[str] = mapped_column(String, unique=True)
    platform: Mapped[str]
    made_for_kids: Mapped[bool] = mapped_column(Boolean, default=False)
    goals: Mapped[dict] = mapped_column(JSON, default=dict)


class Series(Entity, Base):
    __tablename__ = "series"
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    name: Mapped[str]
    style: Mapped[dict] = mapped_column(JSON, default=dict)


class Character(Entity, Base):
    __tablename__ = "characters"
    series_id: Mapped[str | None] = mapped_column(ForeignKey("series.id"), nullable=True)
    name: Mapped[str]
    description: Mapped[str] = mapped_column(Text, default="")
    expressions: Mapped[dict] = mapped_column(JSON, default=dict)


class SceneAsset(Entity, Base):
    __tablename__ = "scene_assets"
    name: Mapped[str]
    kind: Mapped[str]
    path: Mapped[str]
    sha256: Mapped[str] = mapped_column(String, unique=True)
    license: Mapped[str] = mapped_column(Text)


class VideoProject(Entity, Base):
    __tablename__ = "video_projects"
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    series_id: Mapped[str | None] = mapped_column(ForeignKey("series.id"), nullable=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(Text, default="")
    idea: Mapped[str] = mapped_column(Text)
    idea_hash: Mapped[str] = mapped_column(String, unique=True)
    language: Mapped[str] = mapped_column(default="en-US")
    platform: Mapped[str]
    content_type: Mapped[str] = mapped_column(default="short")
    target_duration: Mapped[float] = mapped_column(Float)
    aspect_ratio: Mapped[str] = mapped_column(default="9:16")
    width: Mapped[int] = mapped_column(Integer, default=720)
    height: Mapped[int] = mapped_column(Integer, default=1280)
    fps: Mapped[int] = mapped_column(Integer, default=24)
    script: Mapped[dict] = mapped_column(JSON, default=dict)
    storyboard: Mapped[dict] = mapped_column(JSON, default=dict)
    music_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    music_state: Mapped[dict] = mapped_column(JSON, default=dict)
    visual_config: Mapped[dict] = mapped_column(JSON, default=lambda: {"engine": "compositor_2d"})
    assets: Mapped[list] = mapped_column(JSON, default=list)
    narration: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    status: Mapped[str] = mapped_column(default="DRAFT")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    approved_hash: Mapped[str | None] = mapped_column(nullable=True)


class VideoScene(Entity, Base):
    __tablename__ = "video_scenes"
    project_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"))
    start_time: Mapped[float] = mapped_column(Float)
    duration: Mapped[float] = mapped_column(Float)
    background: Mapped[str]
    characters: Mapped[list] = mapped_column(JSON, default=list)
    props: Mapped[list] = mapped_column(JSON, default=list)
    animation_commands: Mapped[list] = mapped_column(JSON, default=list)
    camera_commands: Mapped[dict] = mapped_column(JSON, default=dict)
    narration: Mapped[str] = mapped_column(Text, default="")
    sound_effects: Mapped[list] = mapped_column(JSON, default=list)
    transition: Mapped[str] = mapped_column(default="fade")


class ScriptVersion(Entity, Base):
    __tablename__ = "script_versions"
    project_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"))
    revision: Mapped[int]
    content: Mapped[dict] = mapped_column(JSON)


class MusicVersion(Entity, Base):
    __tablename__ = "music_versions"
    project_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"))
    revision: Mapped[int]
    content: Mapped[dict] = mapped_column(JSON)
    takes: Mapped[dict] = mapped_column(JSON, default=dict)


class Storyboard(Entity, Base):
    __tablename__ = "storyboards"
    project_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"))
    revision: Mapped[int]
    content: Mapped[dict] = mapped_column(JSON)


class ProductionJob(Entity, Base):
    __tablename__ = "production_jobs"
    __table_args__ = (UniqueConstraint("project_id", "revision", name="uq_job_revision"),)
    project_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"))
    revision: Mapped[int]
    state: Mapped[str] = mapped_column(default="DRAFT")
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)


class JobEvent(Base):
    __tablename__ = "job_events"
    project_id: Mapped[str | None] = mapped_column(ForeignKey("video_projects.id"), nullable=True)
    level: Mapped[str] = mapped_column(default="info")
    stage: Mapped[str]
    message: Mapped[str] = mapped_column(Text)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RenderArtifact(Entity, Base):
    __tablename__ = "render_artifacts"
    project_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"))
    revision: Mapped[int]
    path: Mapped[str]
    sha256: Mapped[str]
    probe: Mapped[dict] = mapped_column(JSON)
    render_seconds: Mapped[float] = mapped_column(Float)


class QualityReview(Entity, Base):
    __tablename__ = "quality_reviews"
    project_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"))
    artifact_hash: Mapped[str]
    approved: Mapped[bool] = mapped_column(Boolean)
    notes: Mapped[str] = mapped_column(Text)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)


class ExternalRenderExport(Entity, Base):
    __tablename__ = "external_render_exports"
    project_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"), index=True)
    revision: Mapped[int]
    semantic_hash: Mapped[str] = mapped_column(index=True)
    manifest: Mapped[dict] = mapped_column(JSON)
    path: Mapped[str]
    state: Mapped[str] = mapped_column(default="EXPORTED")
    artifact_hash: Mapped[str | None] = mapped_column(nullable=True)


class PublishingSchedule(Entity, Base):
    __tablename__ = "publishing_schedules"
    project_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"), unique=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str]
    mode: Mapped[str] = mapped_column(default="manual")
    status: Mapped[str] = mapped_column(default="PLANNED")


class PlatformConnection(Entity, Base):
    __tablename__ = "platform_connections"
    platform: Mapped[str] = mapped_column(unique=True)
    account_id: Mapped[str] = mapped_column(default="")
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(default="AUTH_REQUIRED")


class PlatformPublication(Entity, Base):
    __tablename__ = "platform_publications"
    __table_args__ = (UniqueConstraint("project_id", "platform", "artifact_hash", name="uq_publication"),)
    project_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"))
    platform: Mapped[str]
    artifact_hash: Mapped[str]
    remote_id: Mapped[str] = mapped_column(default="")
    url: Mapped[str] = mapped_column(default="")
    status: Mapped[str]
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class AnalyticsSnapshot(Entity, Base):
    __tablename__ = "analytics_snapshots"
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    source: Mapped[str]
    metrics: Mapped[dict] = mapped_column(JSON)
