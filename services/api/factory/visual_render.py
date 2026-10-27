"""Local CPU Blender renderer. Frame cache belongs to exact, versioned inputs."""

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from filelock import FileLock, Timeout
from PIL import Image

from .config import ROOT, settings
from .render import ffmpeg
from .security import Cancelled, digest, run
from .visual_errors import VisualRequired
from .visual_schema import VisualBoard

SCRIPT = ROOT / "templates/blender/factory_scene.py"
SUPPORTED_BLENDER_SERIES = {(4, 5), (5, 2)}


def blender_info():
    binary = shutil.which(settings.blender_path) if settings.blender_path else shutil.which("blender")
    if not binary:
        raise VisualRequired("Blender 4.5 or 5.2 LTS is missing. Set BLENDER_PATH to blender.exe; 3D never falls back to 2D.")
    result = run([binary, "--version"], timeout=20).decode(errors="replace")
    version = re.search(r"Blender (\d+\.\d+\.\d+)", result)
    if not version or tuple(map(int, version[1].split(".")[:2])) not in SUPPORTED_BLENDER_SERIES:
        raise VisualRequired("This trusted template supports Blender 4.5 and 5.2 LTS. Configure a supported series before rendering.")
    return {"binary": str(Path(binary).resolve()), "version": version[1], "engine": "CYCLES", "device": "CPU"}


def cancel_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        import signal
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def checked_process(args, *, cancel, timeout, on_frame=lambda n: None, kind="renderer"):
    """Drain stdout without retaining Blender logs or leaking prompts/file contents."""
    messages = queue.Queue(maxsize=64)
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, shell=False, **flags)

    def drain():
        while line := process.stdout.readline(4096):
            if re.fullmatch(rb"FACTORY_FRAME \d+\s*", line):
                try:
                    messages.put_nowait(int(line.split()[1]))
                except queue.Full:
                    pass  # Directory scan remains the authoritative frame count.

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    started = time.monotonic()
    try:
        while True:
            if cancel():
                raise Cancelled("Local render cancelled; verified frames are retained for this revision")
            if time.monotonic()-started > timeout:
                raise VisualRequired("Local render timeout. Resume cached frames or explicitly choose a lighter profile.", "timeout")
            try:
                on_frame(messages.get(timeout=.1))
            except queue.Empty:
                pass
            if process.poll() is not None and not reader.is_alive() and messages.empty():
                break
        if process.returncode:
            raise VisualRequired(f"Local {kind} process failed (exit {process.returncode}). Check memory, disk and tool compatibility; no video was approved.", kind)
    finally:
        cancel_process(process)
        reader.join(timeout=2)
        process.stdout.close()


def input_manifest(board, *, width, height, fps, quality, revision, audio, info):
    board.validate_project(board.duration, fps)
    return {"board": board.model_dump(mode="json"), "width": width, "height": height, "fps": fps,
            "quality": quality, "revision": revision, "threads": settings.blender_threads,
            "template_sha256": digest(SCRIPT), "blender": info, "audio_sha256": digest(audio)}


def fingerprint(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def valid_frame(path, width, height):
    try:
        with Image.open(path) as image:
            if image.size != (width, height) or image.format != "PNG":
                return False
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def render_3d(board: VisualBoard, destination, *, width, height, fps, audio, quality="preview",
              revision=1, cancel=lambda: False, progress=lambda data: None):
    info = blender_info()
    if not 64 <= width <= 1920 or not 64 <= height <= 1920 or width % 2 or height % 2:
        raise ValueError("3D resolution must be even and bounded to 1920 pixels")
    if fps not in (24, 30) or quality not in ("preview", "final"):
        raise ValueError("Unsupported render FPS/quality")
    manifest = input_manifest(board, width=width, height=height, fps=fps, quality=quality,
                              revision=revision, audio=audio, info=info)
    cache_id = fingerprint(manifest)
    folder = Path(destination).parent / "frames" / cache_id
    folder.mkdir(parents=True, exist_ok=True)
    total = round(board.duration*fps)
    # Conservative uncompressed RGB footprint plus working space, finite per-render limit.
    estimate = total*width*height*3 + 64*1024**2
    if estimate > settings.blender_disk_budget_mb*1024**2:
        raise VisualRequired("3D frame estimate exceeds BLENDER_DISK_BUDGET_MB; choose Preview or explicitly increase the disk budget.", "disk")
    lock = FileLock(str(settings.storage_root / "blender-render.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout as exc:
        raise VisualRequired("Another local 3D render is active. Retry when its render lease is released.") from exc
    started = time.monotonic()
    try:
        complete = set()
        for i in range(1, total+1):
            if cancel():
                raise Cancelled("Render cancelled")
            path = folder / f"{i:06}.png"
            if path.exists():
                if valid_frame(path, width, height):
                    complete.add(i)
                else:
                    path.unlink()  # Exact cache-owned invalid frame only, no recursive cleanup.
        remaining = (total-len(complete))*width*height*3+64*1024**2
        if shutil.disk_usage(folder).free < remaining:
            raise VisualRequired("Insufficient free disk space for 3D frames. Choose Preview or free space before resuming.", "disk")
        payload = folder / "manifest.json"
        temp = payload.with_suffix(".tmp")
        temp.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
        temp.replace(payload)
        initial = len(complete)

        def report(frame):
            if 1 <= frame <= total:
                complete.add(frame)
            elapsed = time.monotonic()-started
            rendered = len(complete)-initial
            progress({"stage": "frames", "completed": len(complete), "total": total,
                      "elapsed_seconds": round(elapsed, 1),
                      "eta_seconds": round(elapsed/rendered*(total-len(complete))) if rendered >= 8 else None})

        progress({"stage": "scene_preparation", "completed": initial, "total": total, "engine": "CYCLES CPU"})
        if initial != total:
            checked_process([info["binary"], "--background", "--factory-startup", "--disable-autoexec",
                             "--threads", settings.blender_threads, "--python-exit-code", "1",
                             "--python", SCRIPT, "--", payload], cancel=cancel,
                            timeout=settings.blender_timeout_seconds, on_frame=report, kind="blender")
        if not all(valid_frame(folder/f"{i:06}.png", width, height) for i in range(1, total+1)):
            raise VisualRequired("Blender did not produce every valid frame; resume the same revision to repair the cache.")
        progress({"stage": "composition", "completed": total, "total": total})
        partial = Path(destination).with_name("video.partial.mp4")
        try:
            checked_process([ffmpeg(), "-nostdin", "-v", "error", "-y", "-framerate", fps, "-start_number", 1,
                             "-i", folder / "%06d.png", "-i", audio, "-map", "0:v", "-map", "1:a",
                             "-c:v", "libx264", "-threads", settings.blender_threads, "-pix_fmt", "yuv420p",
                             "-c:a", "aac", "-af", "alimiter=limit=0.95", "-t", board.duration,
                             "-movflags", "+faststart", partial], cancel=cancel, timeout=1800, kind="codec")
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
        shutil.copyfile(folder / "000001.png", Path(destination).parent / "thumbnail.png")
        report(total)
        return {"engine": "blender_3d", "renderer": "CYCLES CPU", "blender_version": info["version"],
                "input_hash": cache_id, "manifest": str(payload.relative_to(Path(destination).parent)),
                "frames": total, "resumed_frames": initial, "elapsed_seconds": round(time.monotonic()-started, 3)}
    finally:
        lock.release()
