"""Reproducible real local rendering. No ChatGPT requests, paid services or simulated video."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/api"))

from factory.config import settings  # noqa: E402
from factory.render import probe, validate_video  # noqa: E402
from factory.security import ConfigurationRequired  # noqa: E402
from factory.visual_audio import scene_audio, score  # noqa: E402
from factory.visual_demos import demo  # noqa: E402
from factory.visual_render import render_3d  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("demo", choices=["slice", "dino", "milo", "engineering"])
    parser.add_argument("--render", action="store_true", help="Run real Blender + FFmpeg, default only writes the authored plan")
    parser.add_argument("--quality", choices=["preview", "final"], default="preview")
    parser.add_argument("--resolution", choices=["180x320", "360x640", "720x1280", "1080x1920"], default="360x640")
    parser.add_argument("--audio", type=Path, help="Optional recorded narration matching the exact duration")
    args = parser.parse_args()
    board = demo(args.demo)
    folder = settings.output_dir / "3d-demos" / args.demo
    folder.mkdir(parents=True, exist_ok=True)
    plan = folder / "storyboard.json"
    plan.write_text(board.model_dump_json(indent=2), encoding="utf-8")
    print("Authored plan (not a rendered video):", plan)
    if not args.render:
        return
    # Fail on missing Blender before synthesizing voice or generating temporary files.
    from factory.visual_render import blender_info
    blender_info()
    audio = args.audio.resolve() if args.audio else None
    if audio:
        if abs(float(probe(audio)["format"]["duration"])-board.duration) > .1:
            raise ValueError("Recorded audio must match demo duration within 0.1 second")
    elif args.demo in {"slice", "engineering"}:
        audio = score(board, folder/"original-score.wav")
    else:
        audio = scene_audio(board, folder/"audio")
    width, height = map(int, args.resolution.split("x"))
    movie = folder / "video.mp4"
    report = render_3d(board, movie, width=width, height=height, fps=24, quality=args.quality,
                       audio=audio, progress=lambda data: print(json.dumps(data), flush=True))
    report["technical"] = validate_video(movie, width, height, 24, board.duration)
    (folder/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Persist the measured, approximate mouth timings actually used.
    plan.write_text(board.model_dump_json(indent=2), encoding="utf-8")
    print("Actual MP4:", movie, "Visual and listening review still required.")


if __name__ == "__main__":
    try:
        main()
    except (ConfigurationRequired, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
