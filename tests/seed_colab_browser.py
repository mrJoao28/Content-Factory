"""E2E-only external-render fixture. Refuses non-isolated databases."""
import json
import math
import struct
import sys
import wave

from content_factory_render.archive import atomic_json, identity, pack, sha
from content_factory_render.contract import InputPackage, ResultPackage
from factory.config import ROOT, settings
from factory.db import Session
from factory.models import ExternalRenderExport, JobEvent, ProductionJob, RenderArtifact, VideoProject
from factory.render import ffmpeg
from factory.security import run
from sqlalchemy import delete, select

if '/data/e2e-' not in settings.database_url.replace('\\', '/'):
    raise SystemExit('E2E fixture requires a dedicated e2e database')
mode, project_id = sys.argv[1:]
if mode == 'cleanup':
    with Session.begin() as db:
        for entity in (ExternalRenderExport, RenderArtifact, ProductionJob, JobEvent):
            db.execute(delete(entity).where(entity.project_id == project_id))
        db.execute(delete(VideoProject).where(VideoProject.id == project_id))
    raise SystemExit(0)
if mode == 'prepare':
    audio = settings.output_dir/'colab-fixture.wav'
    with wave.open(str(audio), 'wb') as output:
        output.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
        output.writeframes(b''.join(struct.pack('<h', int(7000*math.sin(2*math.pi*440*i/22050))) for i in range(11025)))
    with Session.begin() as db:
        project = db.get(VideoProject, project_id)
        project.width, project.height, project.target_duration = 64, 96, .5
        project.storyboard = {'duration': .5, 'scenes': [{'duration': .5, 'environment': 'engineering_studio',
                'props': [{'prop_id': 'gear_pair'}], 'characters': [], 'camera': [{'time': 0}], 'particles': 0}]}
        project.script = {'title': 'Browser fixture', 'description': 'Controlled fixture', 'beats': ['Gears turn']}
        project.metadata_json = {'title': 'Browser fixture', 'description': 'Controlled fixture', 'tags': []}
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project_id))
        job.checkpoint = {**job.checkpoint, 'creative_director': {'summary': 'Preserved fixture'},
                          'script_writer': project.script, 'audio': str(audio)}
else:
    with Session() as db:
        row = db.scalar(select(ExternalRenderExport).where(ExternalRenderExport.project_id == project_id,
                                                          ExternalRenderExport.state == 'EXPORTED'))
        package = InputPackage.model_validate(row.manifest)
    directory = ROOT/'output/e2e-colab-return'
    directory.mkdir(exist_ok=True)
    movie, thumbnail = directory/'video.mp4', directory/'thumbnail.png'
    # Controlled test boundary, not a production renderer. Real Blender round-trip has a separate test.
    run([ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=64x96:r=24:d=0.5',
         '-i', settings.output_dir/'colab-fixture.wav', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
         '-c:a', 'aac', '-t', '0.5', movie], timeout=60)
    run([ffmpeg(), '-v', 'error', '-y', '-i', movie, '-frames:v', '1', thumbnail], timeout=60)
    atomic_json(directory/'report.json', {'test_fixture': True})
    paths = {n: directory/n for n in ('video.mp4', 'thumbnail.png', 'report.json')}
    result = ResultPackage(export_id=package.export_id, project_id=package.project_id, revision=package.revision,
        input_hash=identity(package.model_dump(mode='json')), profile=package.profile, effective_backend='CPU',
        execution_hash='a'*64, files={n: {'sha256': sha(p), 'size': p.stat().st_size} for n, p in paths.items()})
    atomic_json(directory/'result.json', result.model_dump(mode='json'))
    archive = directory/'return.zip'
    pack(archive, {**paths, 'result.json': directory/'result.json'})
    print(json.dumps({'file': str(archive)}))
