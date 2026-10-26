from datetime import datetime
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class State(StrEnum):
    DRAFT = "DRAFT"
    SCRIPTING = "SCRIPTING"
    STORYBOARDING = "STORYBOARDING"
    ASSET_CHECK = "ASSET_CHECK"
    AUDIO_GENERATION = "AUDIO_GENERATION"
    RENDERING = "RENDERING"
    TECHNICAL_VALIDATION = "TECHNICAL_VALIDATION"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVED = "APPROVED"
    DRIVE_UPLOAD = "DRIVE_UPLOAD"
    PUBLICATION_PREPARATION = "PUBLICATION_PREPARATION"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    WAITING_FOR_AUTH = "WAITING_FOR_AUTH"
    WAITING_FOR_ASSETS = "WAITING_FOR_ASSETS"
    WAITING_FOR_PLATFORM_APPROVAL = "WAITING_FOR_PLATFORM_APPROVAL"
    READY_FOR_MANUAL_POST = "READY_FOR_MANUAL_POST"


class ProjectCreate(Strict):
    idea: str = Field(min_length=5, max_length=8000)
    channel_id: Literal["wondernest", "how-it-works"] | None = None
    series_id: str | None = None
    content_type: Literal["short", "episode", "explainer"] = "short"
    target_duration: float | None = Field(default=None, ge=20, le=600)

    @model_validator(mode="after")
    def duration(self):
        if self.target_duration is None:
            self.target_duration = 480 if self.content_type == "episode" else 75 if self.channel_id == "how-it-works" else 35
        if self.content_type == "episode" and not 360 <= self.target_duration <= 600:
            raise ValueError("Episodes require 360-600 seconds")
        if self.channel_id == "how-it-works" and not 65 <= self.target_duration <= 90:
            raise ValueError("Engineering videos require 65-90 seconds")
        if self.channel_id == "wondernest" and self.content_type == "short" and not 20 <= self.target_duration <= 40:
            raise ValueError("Kids Shorts require 20-40 seconds")
        return self


class Keyframe(Strict):
    time: float = Field(ge=0, le=600)
    x: float = Field(default=.5, ge=-2, le=3)
    y: float = Field(default=.5, ge=-2, le=3)
    scale: float = Field(default=1, ge=.01, le=4)
    rotation: float = Field(default=0, ge=-3600, le=3600)
    opacity: float = Field(default=1, ge=0, le=1)
    expression: Literal["happy", "surprised", "curious", "sad"] = "happy"
    easing: Literal["linear", "smooth", "in", "out"] = "smooth"


class ExpressionAsset(Strict):
    expression: Literal["happy", "surprised", "curious", "sad"]
    asset_id: str = Field(min_length=1, max_length=100)


class Layer(Strict):
    kind: Literal["circle", "rectangle", "arrow", "gear", "robot", "star", "text", "image", "particles"]
    asset_id: str | None = None
    expression_assets: list[ExpressionAsset] = Field(default_factory=list, max_length=4)
    essential: bool = True
    color: str = Field(default="#64e8cf", pattern=r"^#[0-9a-fA-F]{6}$")
    text: str = Field(default="", max_length=250)
    size: float = Field(default=.2, ge=.01, le=1)
    depth: float = Field(default=1, ge=0, le=2)
    keyframes: list[Keyframe] = Field(min_length=1, max_length=64)

    @field_validator("keyframes")
    @classmethod
    def sorted_frames(cls, frames):
        if any(a.time >= b.time for a, b in zip(frames, frames[1:])):
            raise ValueError("Keyframe times must strictly increase")
        return frames

    @model_validator(mode="after")
    def image_asset(self):
        if self.kind == "image" and not self.asset_id:
            raise ValueError("Image layers require asset_id")
        return self


class Camera(Strict):
    pan_x: float = Field(default=0, ge=-1, le=1)
    pan_y: float = Field(default=0, ge=-1, le=1)
    zoom: float = Field(default=1, ge=1, le=2)


class Scene(Strict):
    duration: float = Field(ge=.25, le=60)
    background: str = Field(default="#132139", pattern=r"^#[0-9a-fA-F]{6}$")
    narration: str = Field(default="", max_length=4000)
    layers: list[Layer] = Field(max_length=32)
    camera: Camera = Field(default_factory=Camera)
    transition: Literal["cut", "fade", "magic"] = "fade"


class Board(Strict):
    scenes: list[Scene] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def bounds(self):
        if sum(s.duration for s in self.scenes) > 601:
            raise ValueError("Maximum total duration is 600s")
        return self


class Source(Strict):
    url: str = Field(pattern=r"^https://", max_length=2000)
    claim: str = Field(min_length=3, max_length=2000)
    evidence: str = Field(default="", max_length=4000)


class Script(Strict):
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(max_length=5000)
    beats: list[str] = Field(min_length=1, max_length=100)
    sources: list[Source] = Field(default_factory=list, max_length=30)
    safety_notes: list[str] = Field(default_factory=list, max_length=30)


class AgentResult(Strict):
    summary: str = Field(max_length=8000)
    flags: list[str] = Field(default_factory=list, max_length=50)


class Metadata(Strict):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=5000)
    tags: list[str] = Field(max_length=30)


class ProjectEdit(Strict):
    script: Script | None = None
    storyboard: Board | None = None
    metadata: Metadata | None = None


class SeriesCreate(Strict):
    channel_id: Literal["wondernest", "how-it-works"]
    name: str = Field(min_length=2, max_length=100)
    style: dict = Field(default_factory=dict)


class CharacterCreate(Strict):
    series_id: str | None = None
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=3000)
    expressions: dict[str, str] = Field(default_factory=dict)


class Review(Strict):
    approved: bool
    notes: str = Field(min_length=3, max_length=4000)
    artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_sources_checked: bool = False


class Schedule(Strict):
    scheduled_at: datetime
    timezone: str = "America/Manaus"
    mode: Literal["manual", "youtube"] = "manual"

    @field_validator("scheduled_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Include an explicit timezone offset")
        return value

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        try:
            ZoneInfo(value)
        except KeyError as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class ManualPublication(Strict):
    url: str = Field(max_length=2000)


class PublishRequest(Strict):
    confirm: bool
    privacy: Literal["private", "unlisted", "public"] = "private"


class DirectPost(Strict):
    confirm: bool
    music_usage_confirmed: bool
    title: str = Field(max_length=2200)
    privacy_level: Literal["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"]
    disable_duet: bool
    disable_stitch: bool
    disable_comment: bool
    brand_content_toggle: bool
    brand_organic_toggle: bool

    @field_validator("title")
    @classmethod
    def utf16_length(cls, value):
        if len(value.encode("utf-16-le"))//2 > 2200:
            raise ValueError("TikTok caption exceeds 2200 UTF-16 code units")
        return value


class BatchCreate(Strict):
    ideas: list[ProjectCreate] = Field(min_length=1, max_length=25)


class AudioCue(Strict):
    asset_id: str = Field(min_length=1, max_length=100)
    time: float = Field(ge=0, le=600)
    volume: float = Field(default=.5, ge=0, le=1)


class AudioMix(Strict):
    music_asset_id: str | None = None
    music_volume: float = Field(default=.12, ge=0, le=.5)
    narration_volume: float = Field(default=1, ge=.1, le=2)
    effects: list[AudioCue] = Field(default_factory=list, max_length=32)
