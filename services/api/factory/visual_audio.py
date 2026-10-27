"""Measured Piper narration/dialogue plus quiet original synthesized score and cues."""
import array
import json
import math
import shutil
import sys
import wave
from pathlib import Path

from .audio import Piper
from .config import settings
from .render import ffmpeg, probe
from .security import Cancelled, run
from .visual_errors import VoiceRequired


def voice_info():
    binary = shutil.which(settings.piper_path) if settings.piper_path else None
    model = Path(settings.piper_voice_path)
    config = Path(str(model)+".json")
    if not binary or not model.is_file() or model.suffix.lower() != ".onnx" or not config.is_file():
        raise VoiceRequired("Configure PIPER_PATH, an English ONNX voice and its .onnx.json, or import narration. No voice is downloaded automatically.")
    try:
        if config.stat().st_size > 262144:
            raise ValueError("Voice config exceeds 256 KiB")
        data = json.loads(config.read_text(encoding="utf-8"))
        code = data["language"]["code"]
        rate = data["audio"]["sample_rate"]
        if not code.startswith("en") or not 8000 <= rate <= 48000 or model.stat().st_size < 1024:
            raise ValueError("Unsupported voice")
        run([binary, "--help"], timeout=15)
    except (ValueError, KeyError, TypeError, AttributeError, OSError, RuntimeError) as exc:
        raise VoiceRequired("Piper voice configuration is invalid; choose a complete English voice and test it in Settings.") from exc
    return {"state": "CONFIGURED", "language": code, "sample_rate": rate, "model": model.name,
            "note": "Configuration verified; a completed voice test confirms synthesis."}


def audible_wav(path):
    """Bounded PCM validation; file duration alone does not establish speech/audio."""
    try:
        count, energy = 0, 0
        with wave.open(str(path), "rb") as source:
            if source.getsampwidth() != 2 or source.getnchannels() not in (1, 2):
                raise ValueError("Expected 16-bit Piper PCM")
            if not 0 < source.getnframes() <= source.getframerate()*600:
                raise ValueError("Invalid audio length")
            while chunk := source.readframes(4096):
                samples = array.array("h", chunk)
                if sys.byteorder != "little":
                    samples.byteswap()
                count += len(samples)
                energy += sum(sample*sample for sample in samples)
        if count == 0 or energy/count < (32767*10**(-60/20))**2:
            raise ValueError("Silent audio")
    except (ValueError, OSError, EOFError, wave.Error) as exc:
        raise VoiceRequired("Voice synthesis returned empty, silent or unsupported PCM audio. Test the English voice in Settings.") from exc


def score(board, path, cancel=lambda: False):
    """Generate PCM in small chunks; no video/audio-length arrays in memory."""
    rate = 22050
    cues, offset = [], 0
    for scene in board.scenes:
        for action in scene.actions:
            if action.kind == "walk":
                for i in range(int((action.end-action.start)*2.8)):
                    cues.append((offset+action.start+i/2.8, "step"))
            if action.kind in {"reach", "hold", "release", "surprise"}:
                cues.append((offset+action.start, "magic" if action.kind == "surprise" else "touch"))
        offset += scene.duration
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        for start in range(0, round(board.duration*rate), 4096):
            if cancel():
                raise Cancelled("Local score generation cancelled")
            active = [(when, kind) for when, kind in cues if when < (start+4096)/rate and when+.35 >= start/rate]
            samples = array.array("h")
            for index in range(start, min(start+4096, round(board.duration*rate))):
                t = index/rate
                fade = max(0, min(1, t/.6, (board.duration-t)/.8))
                value = .04*(math.sin(math.tau*261.63*t)+.5*math.sin(math.tau*329.63*t)+.3*math.sin(math.tau*392*t))
                for when, kind in active:
                    age = t-when
                    if 0 <= age < .35:
                        frequency = 92 if kind == "step" else 880+440*age if kind == "magic" else 300
                        value += (.035 if kind == "step" else .025)*math.sin(math.tau*frequency*age)*math.exp(-age*18)
                samples.append(round(max(-.9, min(.9, value*fade))*32767))
            if sys.byteorder != "little":
                samples.byteswap()
            wav.writeframes(samples.tobytes())
    return path


def scene_audio(board, directory, cancel=lambda: False):
    if not any(s.narration.strip() or s.dialogues for s in board.scenes):
        raise VoiceRequired("No speech planned. Add narration/dialogue or import recorded audio; music is not narration.")
    voice_info()
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, scene in enumerate(board.scenes):
        if cancel():
            raise Cancelled("Audio cancelled")
        clips = []
        if scene.narration.strip():
            clips.append((0, scene.narration, None))
        clips += [(line.start, line.text, line) for line in scene.dialogues]
        measured, end = [], 0
        for start, text, line in sorted(clips, key=lambda x: x[0]):
            speech = Piper().generate(text)
            audible_wav(speech)
            length = float(probe(speech)["format"]["duration"])
            if length < .05 or start < end or start+length > scene.duration+.01:
                raise VoiceRequired(f"3D scene {i+1}: speech does not fit without truncation/overlap. Shorten text or edit timing, then resume.")
            end = start+length
            measured.append((start, speech))
            if line and not line.mouth_times:
                line.mouth_times = [round(start+n*.18, 3) for n in range(min(40, int(length/.18)))]
        args = [ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono"]
        filters, streams = [], "[0:a]"
        for j, (start, speech) in enumerate(measured, 1):
            args += ["-i", speech]
            filters.append(f"[{j}:a]adelay={round(start*1000)}:all=1[a{j}]")
            streams += f"[a{j}]"
        filters.append(f"{streams}amix=inputs={len(measured)+1}:duration=first:normalize=0[out]")
        path = directory/f"scene-{i}.wav"
        run([*args, "-filter_complex", ";".join(filters), "-map", "[out]", "-t", scene.duration, "-ar", "22050", "-ac", "1", path])
        paths.append(path)
    combined = directory/"voice.wav"
    with wave.open(str(combined), "wb") as out:
        out.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        for path in paths:
            with wave.open(str(path), "rb") as source:
                while chunk := source.readframes(4096):
                    out.writeframes(chunk)
    music = score(board, directory/"original-score.wav", cancel=cancel)
    destination = directory/"mixed.wav"
    run([ffmpeg(), "-y", "-i", combined, "-i", music, "-filter_complex",
         "[0:a]loudnorm=I=-18:TP=-2:LRA=7[voice];[voice][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[out]",
         "-map", "[out]", destination], timeout=600)
    return destination
