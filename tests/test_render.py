import math
import struct
import wave

import pytest
from pydantic import ValidationError

from factory.render import ffmpeg, ffprobe, frame, interpolate, render, validate_video
from factory.schemas import Board, Layer
from factory.security import Cancelled, ConfigurationRequired


def board():
    return Board.model_validate({"scenes":[{"duration":2,"background":"#132139","narration":"A friendly robot waves.","layers":[
        {"kind":"robot","color":"#64e8cf","size":.5,"keyframes":[{"time":0,"x":.2,"y":.5},{"time":2,"x":.8,"y":.5,"rotation":20,"expression":"surprised"}]},
        {"kind":"particles","color":"#ffe294","size":.6,"keyframes":[{"time":0}]}]}]})


def sine(path,seconds=2):
    with wave.open(str(path),"wb") as stream:
        stream.setparams((1,2,22050,0,"NONE","not compressed"))
        stream.writeframes(b"".join(struct.pack("<h",int(5000*math.sin(2*math.pi*440*n/22050))) for n in range(int(seconds*22050))))


def test_keyframe_animation_and_alpha():
    scene=board().scenes[0]
    assert interpolate(scene.layers[0],1)["x"] == pytest.approx(.5)
    assert frame(scene,.5,160,284,{ }).tobytes() != frame(scene,1.5,160,284,{}).tobytes()


@pytest.mark.parametrize("layer", [
    {"kind":"shell","keyframes":[{"time":0}]},
    {"kind":"circle","keyframes":[{"time":1},{"time":0}]},
    {"kind":"circle","size":5000,"keyframes":[{"time":0}]},
    {"kind":"image","keyframes":[{"time":0}]},
    {"kind":"circle","keyframes":[{"time":0,"x":float("nan")}]},
])
def test_animation_schema_rejects_unsafe_or_unbounded_data(layer):
    with pytest.raises(ValidationError):
        Layer.model_validate(layer)


def test_render_requires_real_narration(tmp_path):
    with pytest.raises(ConfigurationRequired):
        render(board(),tmp_path/"video.mp4",width=160,height=284)


def test_real_ffmpeg_render_and_probe(tmp_path):
    try:
        ffmpeg();ffprobe()
    except ConfigurationRequired as exc:
        pytest.skip(str(exc))
    audio=tmp_path/"voice.wav"
    sine(audio)
    path=tmp_path/"video.mp4"
    render(board(),path,width=160,height=284,fps=24,audio=audio)
    report=validate_video(path,160,284,24,2)
    assert all(report["checks"].values())
    assert path.stat().st_size>1000
    with pytest.raises(Cancelled):
        render(board(),tmp_path/"cancelled.mp4",width=160,height=284,fps=24,audio=audio,cancel=lambda:True)
    assert not (tmp_path/"cancelled.partial.mp4").exists()


def test_missing_essential_asset_blocks_frame():
    scene=Board.model_validate({"scenes":[{"duration":1,"layers":[{"kind":"image","asset_id":"missing","keyframes":[{"time":0}]}]}]}).scenes[0]
    with pytest.raises(ConfigurationRequired):
        frame(scene,.5,160,284,{})



def test_real_audio_mix_with_music_and_timed_effect(tmp_path):
    from factory.audio import mix_tracks
    from factory.render import probe
    from factory.schemas import AudioMix
    try:ffmpeg();ffprobe()
    except ConfigurationRequired as exc:pytest.skip(str(exc))
    voice=tmp_path/"voice.wav";music=tmp_path/"music.wav";effect=tmp_path/"effect.wav"
    sine(voice,2);sine(music,.5);sine(effect,.2)
    mix=AudioMix(music_asset_id="music",music_volume=.1,effects=[{"asset_id":"effect","time":.8,"volume":.2}])
    output=tmp_path/"mixed.wav"
    mix_tracks(voice,output,2,mix,{"music":music,"effect":effect})
    assert abs(float(probe(output)["format"]["duration"])-2)<.1
    assert output.read_bytes()!=voice.read_bytes()
