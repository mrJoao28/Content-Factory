"""Editorial and measured music contracts; no generated code or arbitrary assets."""
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .schemas import Strict

MAX_DURATION = 3600


class LyricSection(Strict):
    kind: Literal['verse', 'chorus', 'bridge', 'intro', 'outro']
    duration: float = Field(ge=1, le=300)
    lines: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=16)


class MusicEvent(Strict):
    time: float = Field(ge=0, le=MAX_DURATION)
    end: float = Field(gt=0, le=MAX_DURATION)
    character_id: str = Field(min_length=1, max_length=80)
    action: Literal['idle', 'wave', 'smile', 'tilt', 'clap', 'sway', 'dance']


class Beat(Strict):
    time: float = Field(ge=0, le=MAX_DURATION)
    source: Literal['manual', 'provider_alignment', 'requested_grid']


class MusicSegment(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    title: str = Field(min_length=1, max_length=120)
    kind: Literal['song', 'instrumental', 'narration', 'dialogue', 'pause', 'unit']
    source_project_id: str | None = Field(default=None, pattern=r'^[a-f0-9-]{36}$')
    source_artifact_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    duration: float = Field(gt=0, le=600)
    text: str = Field(default='', max_length=8000)
    sections: list[LyricSection] = Field(default_factory=list, max_length=32)
    singer: Literal['offscreen', 'character', 'choir'] = 'offscreen'
    mouth_times: list[float] | None = Field(default=None, max_length=4000)
    character_id: str | None = Field(default=None, max_length=80)
    bpm_requested: int = Field(default=100, ge=40, le=200)
    meter: Literal['4/4', '3/4', '6/8'] = '4/4'
    instruments: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=lambda: ['piano', 'soft bells'], max_length=12)
    direction: str = Field(default='Warm original educational children music', max_length=1000)
    visible_action: str = Field(min_length=1, max_length=1500)
    events: list[MusicEvent] = Field(default_factory=list, max_length=64)
    beats: list[Beat] = Field(default_factory=list, max_length=2000)
    gain: float = Field(default=0.8, ge=0, le=1)
    instrumental_gain: float = Field(default=0.25, ge=0, le=1)
    effects_gain: float = Field(default=0.25, ge=0, le=1)
    fade_in: float = Field(default=0.05, ge=0, le=10)
    fade_out: float = Field(default=0.1, ge=0, le=10)
    ducking: bool = False

    @model_validator(mode='after')
    def timing(self):
        if sum(len(line) for section in self.sections for line in section.lines) > 12000:
            raise ValueError('Lyrics exceed the bounded 12000 characters per segment')
        if self.kind == 'unit' and (not self.source_project_id or not self.source_artifact_hash):
            raise ValueError('Compilation units require an existing reviewed project and exact video hash')
        if self.kind == 'unit' and (self.gain != .8 or self.instrumental_gain != .25 or self.effects_gain != .25
                or self.fade_in != .05 or self.fade_out != .1 or self.ducking or self.events
                or self.sections or self.text or self.mouth_times is not None):
            raise ValueError('Compilation units preserve reviewed content; edit and approve the source before changing its audio or animation')
        if self.kind == 'song' and (not self.sections or not any(s.lines for s in self.sections)):
            raise ValueError('A song needs original lyrics; lyrics are not generated singing')
        if self.sections and abs(sum(s.duration for s in self.sections)-self.duration) > .001:
            raise ValueError('Lyric sections must sum to the planned segment duration')
        if self.singer == 'character' and not self.character_id:
            raise ValueError('Choose the visible singer or use offscreen singing')
        if self.mouth_times is not None and any(not 0 <= t < self.duration for t in self.mouth_times):
            raise ValueError('Manual mouth markers must be relative to the segment and fit its duration')
        if self.fade_in+self.fade_out > self.duration:
            raise ValueError('Fades exceed segment duration')
        ends = {}
        for event in sorted(self.events, key=lambda e: e.time):
            if event.end <= event.time or event.end > self.duration or event.time < ends.get(event.character_id, 0):
                raise ValueError('Animation events must fit the segment without actor overlap')
            ends[event.character_id] = event.end
        if any(b.time >= self.duration for b in self.beats):
            raise ValueError('Beat marker outside segment')
        return self


class MusicPlan(Strict):
    format: Literal['animated_song', 'musical_story', 'musical_episode', 'compilation']
    audience: str = Field(default='Children ages 3-7', max_length=200)
    language: Literal['en-US'] = 'en-US'
    educational_goal: str = Field(min_length=3, max_length=1000)
    characters: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1, max_length=16)
    environment: str = Field(min_length=1, max_length=100)
    beginning: str = Field(min_length=1, max_length=1500)
    development: str = Field(min_length=1, max_length=1500)
    conclusion: str = Field(min_length=1, max_length=1500)
    segments: list[MusicSegment] = Field(min_length=1, max_length=256)

    @model_validator(mode='after')
    def unique_segments(self):
        if len(self.model_dump_json().encode()) > 1024*1024:
            raise ValueError('Music plan exceeds the explicit 1 MiB budget; use fewer markers or smaller units')
        if self.format == 'compilation' and any(s.kind != 'unit' for s in self.segments):
            raise ValueError('A compilation consists of explicit previously reviewed video units')
        if self.format != 'compilation' and any(s.kind == 'unit' for s in self.segments):
            raise ValueError('Choose compilation explicitly to reuse video units')
        if len({s.id for s in self.segments}) != len(self.segments):
            raise ValueError('Segment IDs must be unique')
        if sum(s.duration for s in self.segments) > MAX_DURATION:
            raise ValueError('Production exceeds the explicit 3600 second limit')
        return self

    def validate_duration(self, duration):
        if abs(sum(s.duration for s in self.segments)-duration) > .001:
            raise ValueError('Planned segments must match project duration; edit the plan or explicitly change duration')
        return self
