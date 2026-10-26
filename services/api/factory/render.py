"""Bounded 2.5D compositor: one RGBA frame in memory, H.264/AAC output."""

import json
import math
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import settings
from .schemas import Board, Layer
from .security import Cancelled, ConfigurationRequired, run, safe_path


def ffmpeg():
    found = shutil.which(settings.ffmpeg_path)
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise ConfigurationRequired("Install FFmpeg or imageio-ffmpeg; see docs/SETUP_WINDOWS.md") from exc


def ffprobe():
    found = shutil.which(settings.ffprobe_path)
    if not found:
        raise ConfigurationRequired("FFprobe is required for final technical approval")
    return found


def font(size):
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def interpolate(layer: Layer, t):
    frames = layer.keyframes
    left = right = frames[0]
    for frame in frames:
        if frame.time <= t:
            left = frame
        if frame.time >= t:
            right = frame
            break
    else:
        right = frames[-1]
    p = 0 if left.time == right.time else min(1, max(0, (t - left.time) / (right.time - left.time)))
    if right.easing == "smooth":
        p = p * p * (3 - 2 * p)
    elif right.easing == "in":
        p = p * p
    elif right.easing == "out":
        p = 1 - (1 - p) ** 2
    values = {
        name: getattr(left, name) + (getattr(right, name) - getattr(left, name)) * p
        for name in ("x", "y", "scale", "rotation", "opacity")
    }
    values["expression"] = left.expression if p < 0.5 else right.expression
    return values


def sprite(layer, side, expression, assets, t):
    side = max(4, side)
    im = Image.new("RGBA", (side, side))
    d = ImageDraw.Draw(im)
    c = layer.color
    pad = max(2, side // 20)
    bounds = (pad, pad, side - pad, side - pad)
    if layer.kind == "image":
        expression_id = next(
            (x.asset_id for x in layer.expression_assets if x.expression == expression), layer.asset_id
        )
        path = assets.get(expression_id)
        if not path:
            if layer.essential:
                raise ConfigurationRequired(f"Missing essential asset: {layer.asset_id}")
            return im
        with Image.open(path) as source:
            source = source.convert("RGBA")
            source.thumbnail((side, side))
            im.alpha_composite(source, ((side - source.width) // 2, (side - source.height) // 2))
    elif layer.kind == "circle":
        d.ellipse(bounds, fill=c)
    elif layer.kind == "rectangle":
        d.rounded_rectangle(bounds, radius=side // 8, fill=c)
    elif layer.kind == "arrow":
        d.polygon(
            [
                (pad, side * 0.4),
                (side * 0.65, side * 0.4),
                (side * 0.65, side * 0.2),
                (side - pad, side * 0.5),
                (side * 0.65, side * 0.8),
                (side * 0.65, side * 0.6),
                (pad, side * 0.6),
            ],
            fill=c,
        )
    elif layer.kind in ("star", "gear"):
        n = 10 if layer.kind == "star" else 40
        points = []
        for i in range(n):
            angle = i * math.tau / n - math.pi / 2
            r = side * (0.46 if i % 2 == 0 else 0.23 if layer.kind == "star" else 0.37)
            points.append((side / 2 + math.cos(angle) * r, side / 2 + math.sin(angle) * r))
        d.polygon(points, fill=c)
        if layer.kind == "gear":
            d.ellipse((side * 0.39, side * 0.39, side * 0.61, side * 0.61), fill="#132139")
    elif layer.kind == "robot":
        d.rounded_rectangle((side * 0.12, side * 0.2, side * 0.88, side * 0.72), radius=side // 9, fill=c)
        d.rounded_rectangle((side * 0.27, side * 0.73, side * 0.73, side * 0.94), radius=side // 20, fill=c)
        for x in (0.34, 0.66):
            d.ellipse((side * (x - 0.07), side * 0.35, side * (x + 0.07), side * 0.49), fill="#132139")
        if expression == "surprised":
            d.ellipse((side * 0.44, side * 0.53, side * 0.56, side * 0.66), fill="#132139")
        else:
            d.arc(
                (side * 0.34, side * 0.46, side * 0.66, side * 0.65),
                0,
                180,
                fill="#132139",
                width=max(2, side // 30),
            )
        d.line((side * 0.5, side * 0.2, side * 0.5, side * 0.07), fill=c, width=max(2, side // 30))
        d.ellipse((side * 0.45, side * 0.02, side * 0.55, side * 0.12), fill="#ffe294")
    elif layer.kind == "text":
        lines = textwrap.wrap(layer.text, width=20)
        d.multiline_text(
            (side / 2, side / 2),
            "\n".join(lines),
            fill=c,
            font=font(max(10, side // 10)),
            anchor="mm",
            align="center",
            spacing=6,
        )
    elif layer.kind == "particles":
        for i in range(18):
            x = (i * 67 + math.sin(t + i) * side * 0.08) % side
            y = (i * 41 - t * side * 0.12) % side
            r = 2 + i % 4
            d.ellipse((x - r, y - r, x + r, y + r), fill=c)
    return im


def frame(scene, t, width, height, assets):
    im = Image.new("RGBA", (width, height), scene.background)
    progress = t / scene.duration
    for layer in scene.layers:
        values = interpolate(layer, t)
        zoom = 1 + (scene.camera.zoom - 1) * progress
        side = min(4096, int(min(width, height) * layer.size * values["scale"] * zoom))
        item = sprite(layer, side, values["expression"], assets, t)
        item = item.rotate(values["rotation"], resample=Image.Resampling.BICUBIC, expand=True)
        if values["opacity"] < 1:
            item.putalpha(item.getchannel("A").point(lambda a: int(a * values["opacity"])))
        x = ((values["x"] - 0.5) * zoom + 0.5) * width - scene.camera.pan_x * width * progress * layer.depth
        y = ((values["y"] - 0.5) * zoom + 0.5) * height - scene.camera.pan_y * height * progress * layer.depth
        im.alpha_composite(item, (int(x - item.width / 2), int(y - item.height / 2)))
    # Fade through the background at scene boundaries. No extra duration is introduced.
    if scene.transition in ("fade", "magic"):
        alpha = min(1, t / 0.22, (scene.duration - t) / 0.22)
        if alpha < 1:
            im = Image.blend(Image.new("RGBA", im.size, scene.background), im, max(0, alpha))
    return im.convert("RGB")


def render(
    board: Board,
    destination: Path,
    *,
    width=720,
    height=1280,
    fps=24,
    audio=None,
    assets=None,
    cancel=lambda: False,
    progress=lambda x: None,
):
    if width % 2 or height % 2 or not (64 <= width <= 1920 and 64 <= height <= 1920 and 1 <= fps <= 30):
        raise ValueError("Invalid render dimensions or frame rate")
    if not audio or not Path(audio).is_file():
        raise ConfigurationRequired("Import narration or configure Piper before rendering")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".partial.mp4")
    duration = sum(round(s.duration * fps) / fps for s in board.scenes)
    args = [
        ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-af",
        "apad,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-threads",
        "2",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(temp),
    ]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=errors,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            total = sum(round(s.duration * fps) for s in board.scenes)
            count = 0
            for scene in board.scenes:
                for n in range(round(scene.duration * fps)):
                    if cancel():
                        raise Cancelled("Render cancelled")
                    process.stdin.write(frame(scene, n / fps, width, height, assets or {}).tobytes())
                    count += 1
                    if count % fps == 0:
                        progress(round(count / total * 100))
            process.stdin.close()
            if process.wait(timeout=120):
                raise RuntimeError("FFmpeg failed to encode video")
            temp.replace(destination)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            temp.unlink(missing_ok=True)
    return destination


def probe(path):
    return json.loads(run([ffprobe(), "-v", "error", "-show_streams", "-show_format", "-of", "json", path]))


def validate_video(path, width, height, fps, duration):
    data = probe(path)
    video = next((x for x in data["streams"] if x["codec_type"] == "video"), {})
    audio = next((x for x in data["streams"] if x["codec_type"] == "audio"), {})
    rate = video.get("avg_frame_rate", "0/1").split("/")
    checks = {
        "h264": video.get("codec_name") == "h264",
        "aac": audio.get("codec_name") == "aac",
        "resolution": (video.get("width"), video.get("height")) == (width, height),
        "fps": abs(int(rate[0]) / max(1, int(rate[1])) - fps) < 0.1,
        "duration": abs(float(data["format"]["duration"]) - duration) < 0.5,
    }
    # Decode the entire stream. -xerror turns corrupt packet/decode warnings into failures.
    run([ffmpeg(), "-v", "error", "-xerror", "-i", path, "-f", "null", "-"], timeout=1800)
    checks["decode"] = True
    # loudnorm JSON reports measured loudness without trusting encoder metadata.
    result = subprocess.run(
        [
            ffmpeg(),
            "-hide_banner",
            "-i",
            str(path),
            "-vn",
            "-af",
            "loudnorm=I=-16:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        timeout=1800,
        shell=False,
    )
    text = result.stderr.decode(errors="replace")
    try:
        levels = json.loads(text[text.rfind("{") : text.rfind("}") + 1])
        checks["audible"] = -35 <= float(levels["input_i"]) <= -8
        checks["peak"] = float(levels["input_tp"]) <= 0
    except (ValueError, KeyError):
        checks["audible"] = False
    if not all(checks.values()):
        raise ValueError(f"Technical validation failed: {checks}")
    return {"checks": checks, "media": data}


def blend_audio(narration, destination, *, music=None, effects=None, music_volume=0.12):
    args = [ffmpeg(), "-y", "-i", str(narration)]
    inputs = [music] if music else []
    inputs += list(effects or [])
    for path in inputs:
        args += ["-i", str(path)]
    if inputs:
        filters = [f"[1:a]volume={min(0.5, max(0, music_volume))}[music]"] if music else []
        streams = "[0:a]" + ("[music]" if music else "")
        streams += "".join(f"[{i}:a]" for i in range(2 if music else 1, len(inputs) + 1))
        filters += [f"{streams}amix=inputs={len(inputs) + 1}:duration=first:normalize=0[out]"]
        args += ["-filter_complex", ";".join(filters), "-map", "[out]"]
    args += ["-ac", "1", "-ar", "22050", str(destination)]
    run(args, timeout=1800)
    return destination


def render_blender(template_name, output):
    # Only repository-owned scripts. Never execute AI- or user-supplied Python.
    allowed = {"mechanism": "mechanism.py"}
    if template_name not in allowed or not settings.blender_path:
        raise ConfigurationRequired("Configure Blender and choose a trusted template")
    script = safe_path(Path(__file__).resolve().parents[3] / "templates/blender", allowed[template_name])
    run(
        [settings.blender_path, "--background", "--factory-startup", "--python", script, "--", str(output)],
        timeout=1800,
    )
