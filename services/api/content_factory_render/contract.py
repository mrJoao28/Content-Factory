"""Versioned portable scene transport. No local machine settings are serialized."""
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .scene import Data, VisualBoard


class Profile(Data):
    quality: Literal['preview', 'final'] = 'preview'
    width: int = Field(ge=64, le=1920)
    height: int = Field(ge=64, le=1920)
    fps: Literal[24, 30] = 24
    samples: int = Field(ge=1, le=128)
    seed: int = Field(default=0, ge=0, le=2147483647)
    hardware: Literal['GPU', 'CPU', 'OPTIX', 'CUDA'] = 'GPU'

    @model_validator(mode='after')
    def dimensions(self):
        if self.width % 2 or self.height % 2:
            raise ValueError('Resolution must be even')
        return self


class FileHash(Data):
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    size: int = Field(ge=1, le=512*1024**2)


class InputPackage(Data):
    format: Literal['content-factory-input-v1'] = 'content-factory-input-v1'
    export_id: UUID
    project_id: UUID
    revision: int = Field(ge=1)
    render_commit: str = Field(pattern=r'^[a-f0-9]{40}$')
    template_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    board: VisualBoard
    profile: Profile
    audio: FileHash
    audio_path: Literal['audio/narration.wav'] = 'audio/narration.wav'

    @model_validator(mode='after')
    def timeline(self):
        self.board.validate_project(self.board.duration, self.profile.fps)
        return self


class ResultPackage(Data):
    format: Literal['content-factory-result-v1'] = 'content-factory-result-v1'
    export_id: UUID
    project_id: UUID
    revision: int = Field(ge=1)
    input_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    profile: Profile
    effective_backend: Literal['CPU', 'OPTIX', 'CUDA']
    execution_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    files: dict[Literal['video.mp4', 'thumbnail.png', 'report.json'], FileHash]

    @model_validator(mode='after')
    def backend(self):
        if self.profile.hardware != 'GPU' and self.effective_backend != self.profile.hardware:
            raise ValueError('Effective hardware differs from explicit selection')
        if self.profile.hardware == 'GPU' and self.effective_backend == 'CPU':
            raise ValueError('GPU export cannot fall back to CPU')
        if set(self.files) != {'video.mp4', 'thumbnail.png', 'report.json'}:
            raise ValueError('Result files missing')
        return self
