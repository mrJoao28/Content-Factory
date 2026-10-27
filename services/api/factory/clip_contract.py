"""Future extension contract only. No paid service is registered or called implicitly."""
from pathlib import Path
from typing import Callable, Protocol

from pydantic import Field

from .visual_schema import Data


class ClipRequest(Data):
    model: str = Field(min_length=1, max_length=100)
    duration: float = Field(gt=0, le=60)
    description: str = Field(min_length=5, max_length=4000)
    confirmed_max_cost: float = Field(ge=0, le=1000)


class ClipReceipt(Data):
    service: str
    external_id: str
    duration: float = Field(gt=0, le=60)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: str = Field(min_length=3, max_length=2000)
    provenance: str = Field(min_length=3, max_length=2000)


class ExternalClips(Protocol):
    """Future adapters must validate downloaded MP4s, disclose costs and preserve provenance."""
    def available(self) -> bool: ...
    def quote(self, request: ClipRequest) -> dict: ...
    def generate(self, request: ClipRequest, destination: Path,
                 cancel: Callable[[], bool]) -> ClipReceipt: ...
