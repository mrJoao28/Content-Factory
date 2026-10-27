from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")
    app_env: Literal["development", "production", "test"] = "development"
    app_host: str = "127.0.0.1"
    api_port: int = 8000
    web_port: int = 3000
    database_url: str = "sqlite:///./data/content_factory.db"
    storage_root: Path = ROOT / "data"
    output_dir: Path = ROOT / "output"
    assets_dir: Path = ROOT / "assets"
    default_timezone: str = "America/Manaus"
    ai_provider: Literal["chatgpt", "codex"] | None = None
    chatgpt_login_timeout_seconds: int = Field(default=300, ge=1, le=600)
    chatgpt_stream_max_bytes: int = Field(default=16_777_216, ge=16_384, le=134_217_728)
    chatgpt_event_max_bytes: int = Field(default=2_097_152, ge=1024, le=8_388_608)
    chatgpt_text_max_bytes: int = Field(default=1_048_576, ge=1024, le=4_194_304)
    chatgpt_timeout_seconds: float | None = Field(default=None, ge=1, le=1800)
    codex_auth_mode: Literal["chatgpt"] = "chatgpt"
    codex_provider: Literal["auto", "cli", "sdk"] = "auto"
    codex_path: str = "codex"
    codex_timeout_seconds: int = 300
    codex_max_concurrent_jobs: int = Field(default=1, ge=1, le=1)
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    blender_path: str = ""
    piper_path: str = ""
    piper_voice_path: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://127.0.0.1:8000/auth/google/callback"
    google_drive_folder_id: str = ""
    youtube_channel_id: str = ""
    tiktok_direct_post_enabled: bool = False
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = "http://127.0.0.1:8000/auth/tiktok/callback"
    render_max_concurrent: int = Field(default=1, ge=1, le=1)
    render_default_width: int = 720
    render_default_height: int = 1280
    render_default_fps: int = Field(default=24, ge=23, le=30)
    auto_publish: bool = False
    require_human_approval: bool = True
    max_upload_mb: int = 100

    def prepare(self):
        for name in ("storage_root", "output_dir", "assets_dir"):
            path = getattr(self, name)
            if not path.is_absolute():
                path = ROOT / path
            path.mkdir(parents=True, exist_ok=True)
            setattr(self, name, path.resolve())
        if self.database_url.startswith("sqlite:///./"):
            self.database_url = "sqlite:///" + str(ROOT / self.database_url.removeprefix("sqlite:///./"))
        if (
            self.render_default_width % 2
            or self.render_default_height % 2
            or not 360 <= self.render_default_width <= 1080
            or not 640 <= self.render_default_height <= 1920
            or abs(self.render_default_width / self.render_default_height - 9 / 16) > 0.001
        ):
            raise ValueError("Default vertical resolution must be even, 9:16, between 360x640 and 1080x1920")
        if self.auto_publish:
            raise ValueError("Automatic timer-based publication is not enabled in this version")
        if self.app_host != "127.0.0.1":
            raise ValueError("Only the loopback interface is supported")
        return self


settings = Settings().prepare()
