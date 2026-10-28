import hashlib
import shutil
from pathlib import Path

from .config import settings
from .render import ffmpeg, probe
from .security import ConfigurationRequired, run


class Piper:
    def generate(self, text, *, speed=1.0, cancel=None):
        executable = shutil.which(settings.piper_path) if settings.piper_path else None
        voice = Path(settings.piper_voice_path)
        if not executable or not voice.is_file():
            raise ConfigurationRequired(
                "Configure PIPER_PATH and an English PIPER_VOICE_PATH, or import narration"
            )
        if not 0.5 <= speed <= 2:
            raise ValueError("Speed must be 0.5-2")
        key = hashlib.sha256(
            (text + str(voice.resolve()) + str(voice.stat().st_mtime_ns) + str(speed)).encode()
        ).hexdigest()
        path = settings.storage_root / "audio" / (key + ".wav")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temp = path.with_suffix(".partial.wav")
            try:
                execute = run
                if cancel is not None:
                    from functools import partial

                    from .music_audio import process
                    execute = partial(process, cancel=cancel)
                execute(
                    [executable, "--model", voice, "--output_file", temp, "--length_scale", str(1 / speed)],
                    input=text.encode(),
                    timeout=600,
                )
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
        return path

    def scenes(self, board, directory, cancel=lambda: False):
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, scene in enumerate(board.scenes):
            if cancel():
                from .security import Cancelled

                raise Cancelled("Audio cancelled")
            speech = self.generate(scene.narration) if scene.narration.strip() else None
            path = directory / f"scene-{i}.wav"
            if speech:
                length = float(probe(speech)["format"]["duration"])
                if length > scene.duration + 0.1:
                    raise ConfigurationRequired(
                        f"Scene {i + 1}: narration ({length:.1f}s) exceeds scene duration"
                    )
                args = ["-i", str(speech), "-af", "apad"]
            else:
                args = ["-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono"]
            run([ffmpeg(), "-y", *args, "-t", str(scene.duration), "-ac", "1", "-ar", "22050", path])
            paths.append(path)
        # All generated scene WAV files have identical PCM parameters.
        import wave

        combined = directory / "narration.wav"
        with wave.open(str(combined), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(22050)
            for path in paths:
                with wave.open(str(path), "rb") as source:
                    out.writeframes(source.readframes(source.getnframes()))
        return combined


def mix_tracks(narration, destination, duration, mix, assets):
    args = [ffmpeg(), "-y", "-i", str(narration)]
    filters = [f"[0:a]volume={mix.narration_volume}[voice]"]
    streams, count = "[voice]", 1
    if mix.music_asset_id:
        args += ["-stream_loop", "-1", "-i", str(assets[mix.music_asset_id])]
        filters += [f"[{count}:a]volume={mix.music_volume}[music]"]
        streams += "[music]"
        count += 1
    for i, cue in enumerate(mix.effects):
        if cue.time >= duration:
            raise ValueError("Sound effect starts after the video ends")
        args += ["-i", str(assets[cue.asset_id])]
        filters += [f"[{count}:a]adelay={round(cue.time * 1000)}:all=1,volume={cue.volume}[fx{i}]"]
        streams += f"[fx{i}]"
        count += 1
    filters += [f"{streams}amix=inputs={count}:duration=first:normalize=0[out]"]
    args += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-t",
        str(duration),
        "-ac",
        "1",
        "-ar",
        "22050",
        str(destination),
    ]
    run(args, timeout=1800)
    return destination
