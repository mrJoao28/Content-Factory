"""Render two authored local demos. Does not call Codex or any publishing API.

FFmpeg Flite is used only for demo speech when Piper is not configured.
The production pipeline continues to use Piper or explicitly imported audio.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/api"))
from factory.config import settings
from factory.render import ffmpeg, frame, render, validate_video
from factory.schemas import Board
from factory.security import digest, run
from factory.templates import motion_template


def demo(channel):
    kids=channel=="wondernest"
    names=["observe","jump","magic"] if kids else ["gears","exploded","arrows"]
    lengths=[10,12,13] if kids else [20,20,25]
    narration=("A little robot found a glowing star in the garden. It looked so bright and beautiful. "
               "The robot wanted to take it home. Then a tiny friend arrived. "
               "Together they made a wish. The star filled their garden with light. "
               "Some discoveries are even better when we share them.") if kids else (
               "Here is a simplified animation of two gears. When one turns, its teeth push the teeth of the other. "
               "Two external gears rotate in opposite directions. "
               "A smaller gear turns more times than a larger gear over the same interval. "
               "This diagram is an illustration of a basic mechanism. It does not simulate contact forces or material behavior. "
               "The exploded view separates shapes so you can see each part. The arrows indicate motion. "
               "Always use verified engineering references for real machine design. Do not work on moving equipment.")
    folder=settings.output_dir/"demo"/channel
    folder.mkdir(parents=True,exist_ok=True)
    voice=folder/"narration.wav"
    # Static authored text only; not an animation prompt or arbitrary filter input.
    run([ffmpeg(),"-y","-f","lavfi","-i",f"flite=text='{narration}':voice=slt",
         "-af","apad","-t",str(sum(lengths)),"-ar","22050","-ac","1",voice],timeout=120)
    scenes=[]
    for name,duration in zip(names,lengths):
        scene=motion_template(name,duration).scenes[0]
        scene.narration=narration if not scenes else ""
        scenes.append(scene)
    board=Board(scenes=scenes)
    movie=folder/"video.mp4"
    started=time.monotonic()
    render(board,movie,width=360,height=640,fps=24,audio=voice)
    report=validate_video(movie,360,640,24,sum(lengths))
    report.update({"sha256":digest(movie),"render_seconds":time.monotonic()-started,"authored_demo":True,
                   "ai_generated":False,"narration_provider":"FFmpeg Flite demo only","published":False})
    (folder/"validation.json").write_text(json.dumps(report,indent=2))
    (folder/"storyboard.json").write_text(board.model_dump_json(indent=2))
    frame(board.scenes[0],2,360,640,{}).save(folder/"thumbnail.png")
    print(f"{channel}: {movie} ({movie.stat().st_size} bytes), checks={report['checks']}",flush=True)


if __name__=="__main__":
    for channel in ("wondernest","how-it-works"):
        demo(channel)
