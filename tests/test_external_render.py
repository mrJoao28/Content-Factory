import json
import os
import stat
import zipfile
from uuid import uuid4

import pytest
from content_factory_render.archive import atomic_json, identity, pack, sha, unpack
from content_factory_render.contract import InputPackage, Profile, ResultPackage
from content_factory_render.runner import Renderer, load_package
from factory.config import ROOT, settings
from factory.db import Session
from factory.external_render import TEMPLATE
from factory.models import ExternalRenderExport, ProductionJob, RenderArtifact, VideoProject, utcnow
from factory.queue import claim
from factory.render_release import RENDER_COMMIT
from factory.visual_schema import VisualBoard
from sqlalchemy import func, select
from test_render import sine


def board():
    return VisualBoard(duration=.5, scenes=[{'duration': .5, 'environment': 'engineering_studio',
        'characters': [], 'props': [{'prop_id': 'gear_pair'}], 'camera': [{'time': 0}], 'particles': 0}])


@pytest.fixture
def ready(client, monkeypatch):
    monkeypatch.setattr(settings, 'ai_provider', 'codex')
    monkeypatch.setattr('factory.visual_render.blender_info', lambda: pytest.fail('External preparation called local Blender'))
    response = client.post('/projects', json={'idea': 'Show two original gears turning in a 3D engineering studio',
        'channel_id': 'how-it-works', 'target_duration': 8,
        'visual': {'engine': 'blender_3d', 'execution_location': 'colab', 'external_hardware': 'CPU',
                   'environment': 'engineering_studio'}})
    assert response.status_code == 201, response.text
    project_id = response.json()['id']
    audio = settings.output_dir/'known.wav'
    sine(audio, seconds=.5)
    with Session.begin() as db:
        project = db.get(VideoProject, project_id)
        project.target_duration, project.width, project.height = .5, 64, 96
        project.storyboard = board().model_dump(mode='json')
        project.script = {'title': 'Gears', 'description': 'An illustrative mechanism', 'beats': ['Gears move'],
                          'sources': [], 'safety_notes': []}
        project.metadata_json = {'title': 'Gears', 'description': 'An illustration', 'tags': []}
        project.status = 'WAITING_FOR_EXTERNAL_RENDER'
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project_id))
        job.state = project.status
        job.checkpoint = {**job.checkpoint, 'creative_director': {'retained': True},
                          'script_writer': project.script, 'audio': str(audio)}
    return project_id


def export(client, project_id):
    response = client.post(f'/projects/{project_id}/external-render/export', json={'expected_revision': 1})
    assert response.status_code == 200, response.text
    with Session() as db:
        row = db.get(ExternalRenderExport, response.json()['export_id'])
        return InputPackage.model_validate(row.manifest), settings.output_dir/row.path


@pytest.mark.parametrize('name', ['../bad', '/absolute', 'C:/secret', '\\\\host\\share', 'audio/../x', 'a//b', 'x.py'])
def test_safe_allowlisted_archive(tmp_path, name):
    archive = tmp_path/'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as out:
        out.writestr(name, b'bad')
    with pytest.raises(ValueError):
        unpack(archive, tmp_path/'extracted', allowed={'manifest.json', 'audio/narration.wav'})
    assert not (tmp_path/'bad').exists()


def test_zip_symlinks_duplicates_and_bombs(tmp_path):
    for kind in ('symlink', 'duplicate', 'bomb', 'count'):
        archive = tmp_path/f'{kind}.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as out:
            if kind == 'symlink':
                info = zipfile.ZipInfo('link')
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                out.writestr(info, '/etc/passwd')
            elif kind == 'duplicate':
                out.writestr('A.json', '{}')
                out.writestr('a.json', '{}')
            elif kind == 'count':
                for i in range(257):
                    out.writestr(f'{i}.json', '{}')
            else:
                out.writestr('bomb', bytes(1_000_000))
        with pytest.raises(ValueError):
            unpack(archive, tmp_path/kind)


def test_export_idempotent_portable_waiting_and_guards(client, ready, tmp_path):
    package, archive = export(client, ready)
    again, same = export(client, ready)
    assert package == again and same == archive
    extracted = tmp_path/'linux'
    loaded = load_package(archive, extracted, trusted_commit=RENDER_COMMIT, template=TEMPLATE)
    assert loaded == package
    assert {str(p.relative_to(extracted)).replace('\\', '/') for p in extracted.rglob('*') if p.is_file()} == {'manifest.json', 'audio/narration.wav'}
    raw = (extracted/'manifest.json').read_text()
    for forbidden in ('C:', 'token', 'credential', 'generated_path', 'blender.exe', '_ai_selection', 'retained'):
        assert forbidden not in raw
    assert claim('should-not-claim') is None
    assert client.post(f'/projects/{ready}/jobs/resume', json={}).status_code == 409
    assert client.post(f'/projects/{ready}/external-render/export', json={'expected_revision': 2}).status_code == 409
    assert client.post(f'/projects/{ready}/external-render/import', content=b'bad', headers={'Content-Type': 'application/zip'}).status_code == 422
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == ready))
        before = dict(job.checkpoint)
        job.owner, job.lease_until = 'active-render', utcnow().replace(year=2099)
    assert client.post(f'/projects/{ready}/render-location', json={'expected_revision': 1, 'execution_location': 'local'}).status_code == 409
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == ready))
        job.owner, job.lease_until = None, None
    response = client.post(f'/projects/{ready}/render-location', json={'expected_revision': 1, 'execution_location': 'local'})
    assert response.status_code == 200
    with Session() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == ready))
        assert job.checkpoint['creative_director'] == before['creative_director']
        assert job.checkpoint['script_writer'] == before['script_writer']
        assert job.checkpoint['_render_prepared'] is True


def test_cpu_fallback_is_never_accepted():
    profile = Profile(width=64, height=96, samples=8, hardware='GPU')
    with pytest.raises(ValueError, match='fall back'):
        ResultPackage(export_id=uuid4(), project_id=uuid4(), revision=1, input_hash='0'*64, profile=profile,
                      effective_backend='CPU', execution_hash='1'*64,
                      files={n: {'sha256': '2'*64, 'size': 1} for n in ['video.mp4', 'thumbnail.png', 'report.json']})


@pytest.mark.parametrize('reason', ['stale', 'unknown', 'profile', 'cancelled', 'superseded'])
def test_return_rejects_wrong_export_before_media_processing(client, ready, tmp_path, monkeypatch, reason):
    package, _ = export(client, ready)
    profile = package.profile.model_copy()
    export_id = package.export_id
    revision = package.revision
    if reason == 'stale':
        revision += 1
    elif reason == 'unknown':
        export_id = uuid4()
    elif reason == 'profile':
        profile.samples += 1
    elif reason == 'cancelled':
        assert client.post(f'/projects/{ready}/jobs/cancel', json={}).status_code == 200
    else:
        assert client.post(f'/projects/{ready}/render-location', json={
            'expected_revision': 1, 'execution_location': 'local'}).status_code == 200
    paths = {}
    for name in ('video.mp4', 'thumbnail.png', 'report.json'):
        path = tmp_path/name
        path.write_bytes(b'controlled invalid media, never decoded for a rejected transfer')
        paths[name] = path
    result = ResultPackage(export_id=export_id, project_id=ready, revision=revision,
        input_hash=identity(package.model_dump(mode='json')), profile=profile, effective_backend='CPU',
        execution_hash='1'*64, files={n: {'sha256': sha(p), 'size': p.stat().st_size} for n, p in paths.items()})
    atomic_json(tmp_path/'result.json', result.model_dump(mode='json'))
    archive = tmp_path/'return.zip'
    pack(archive, {**paths, 'result.json': tmp_path/'result.json'})
    monkeypatch.setattr('factory.external_render.validate_video', lambda *_: pytest.fail('Invalid selection reached media decode'))
    response = client.post(f'/projects/{ready}/external-render/import', content=archive.read_bytes(),
                           headers={'Content-Type': 'application/zip'})
    assert response.status_code == 409, response.text


def test_external_upload_retains_host_origin_header_and_size_protection(client, ready):
    path = f'/projects/{ready}/external-render/import'
    assert client.post(path, content=b'bad', headers={'Content-Type': 'application/zip', 'Origin': 'https://evil.example'}).status_code == 403
    assert client.post(path, content=b'bad', headers={'Content-Type': 'application/zip', 'Host': 'evil.example'}).status_code == 400
    assert client.post(path, content=b'bad', headers={'Content-Type': 'application/zip', 'Content-Length': str(257*1024**2)}).status_code == 413
    assert client.post(path, content=b'bad', headers={'Content-Type': 'text/plain'}).status_code == 415


def test_input_audio_tampering_and_untrusted_release(client, ready, tmp_path):
    package, archive = export(client, ready)
    with pytest.raises(ValueError, match='trusted'):
        load_package(archive, tmp_path/'wrong-release', trusted_commit='0'*40, template=TEMPLATE)
    with zipfile.ZipFile(archive) as source:
        raw = source.read('manifest.json')
    altered = tmp_path/'tampered.zip'
    with zipfile.ZipFile(altered, 'w') as output:
        output.writestr('manifest.json', raw)
        output.writestr('audio/narration.wav', b'not the registered audio')
    with pytest.raises(ValueError, match='integrity'):
        load_package(altered, tmp_path/'altered', trusted_commit=RENDER_COMMIT, template=TEMPLATE)


def test_checkpoint_restore_verifies_shards(tmp_path):
    from PIL import Image
    renderer = object.__new__(Renderer)
    renderer.package = type('Package', (), {'profile': Profile(width=64, height=96, samples=8)})()
    renderer.config, renderer.cache_id, renderer.total = {'backend': 'CUDA'}, 'a'*64, 2
    renderer.folder = tmp_path/'local'
    renderer.folder.mkdir()
    renderer.report = {'backend': 'CUDA'}
    for i in (1, 2):
        Image.new('RGB', (64, 96), (100, i, 50)).save(renderer.folder/f'{i:06}.png')
    renderer.save_checkpoint(tmp_path/'drive', [1, 2])
    saved = next((tmp_path/'drive'/renderer.cache_id).glob('*.zip'))
    before = (sha(saved), saved.stat().st_mtime_ns)
    renderer.save_checkpoint(tmp_path/'drive', [1, 2])
    assert (sha(saved), saved.stat().st_mtime_ns) == before
    renderer.folder = tmp_path/'new-session'
    renderer.folder.mkdir()
    assert renderer.restore(tmp_path/'drive') == 2
    # Incomplete shard without an index never counts as saved.
    (tmp_path/'drive'/renderer.cache_id/'unfinished.partial').write_bytes(b'bad')
    assert renderer.restore(tmp_path/'drive') == 2
    index = next((tmp_path/'drive'/renderer.cache_id).glob('*.json'))
    index.with_suffix('.zip').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='corrupt'):
        renderer.restore(tmp_path/'drive')
    renderer.cache_id = 'b'*64
    renderer.folder = tmp_path/'other-backend'
    renderer.folder.mkdir()
    assert renderer.restore(tmp_path/'drive') == 0


def test_worker_external_boundary_retains_checkpoints_and_releases_lease(client, ready, monkeypatch):
    from factory.queue import Worker
    monkeypatch.setattr('factory.pipeline.get_provider', lambda *_: pytest.fail('Prepared export invoked AI'))
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == ready))
        job.state = 'DRAFT'
        job.checkpoint = {**job.checkpoint, '_render_prepared': True}
    assert Worker().once()
    with Session() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == ready))
        assert job.state == 'WAITING_FOR_EXTERNAL_RENDER'
        assert job.owner is None and job.lease_until is None and job.attempts == 0
        assert job.checkpoint['creative_director'] == {'retained': True}
        assert job.checkpoint['script_writer']['title'] == 'Gears'
    assert claim('second-worker') is None


def test_preparation_reaches_external_boundary_without_local_blender(client, ready, monkeypatch):
    """Real pipeline/worker/routes, controlled text provider and real imported measured audio."""
    import shutil
    from contextlib import nullcontext

    from factory.queue import Worker
    from factory.schemas import AgentResult

    class TextBoundary:
        def generate(self, role, context, response_type, **kwargs):
            assert response_type is AgentResult
            return AgentResult(summary='Controlled text-provider fixture', flags=[])

        def persistence_guard(self):
            return nullcontext()

    monkeypatch.setattr('factory.pipeline.get_provider', lambda *_: TextBoundary())
    shutil.copyfile(settings.output_dir/'known.wav', settings.storage_root/'imported.wav')
    with Session.begin() as db:
        project = db.get(VideoProject, ready)
        project.narration = {'path': 'imported.wav'}
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == ready))
        job.state = 'DRAFT'
        job.checkpoint = {**job.checkpoint, 'creative_director': {'summary': 'Preserved concept'}}
    assert Worker().once()
    with Session() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == ready))
        assert job.state == 'WAITING_FOR_EXTERNAL_RENDER', job.error
        assert job.checkpoint['_render_prepared'] is True
        assert job.owner is None and job.lease_until is None
        assert job.checkpoint['script_writer']['title'] == 'Gears'
    package, _ = export(client, ready)
    assert package.board.duration == .5


def test_cancel_terminates_renderer_subprocess():
    import sys

    from content_factory_render.runner import execute
    with pytest.raises(InterruptedError):
        execute([sys.executable, '-c', 'import time; time.sleep(20)'], timeout=2, cancel=lambda: True)


def test_source_hash_is_portable_between_checkouts(tmp_path):
    from content_factory_render.archive import source_sha
    windows, linux = tmp_path/'windows.py', tmp_path/'linux.py'
    windows.write_bytes(b'print(1)\r\n')
    linux.write_bytes(b'print(1)\n')
    assert source_sha(windows) == source_sha(linux)


def test_real_blender_export_render_import(client, ready, tmp_path):
    binary = os.environ.get('FACTORY_TEST_BLENDER')
    if not binary:
        pytest.skip('Explicit isolated Blender smoke opt-in required')
    package, archive = export(client, ready)
    extracted = tmp_path/'package'
    load_package(archive, extracted, trusted_commit=RENDER_COMMIT, template=TEMPLATE)
    from factory.render import ffmpeg
    runner = Renderer(package, extracted, tmp_path/'frames', blender=binary, template=TEMPLATE,
                      ffmpeg=ffmpeg(), backend='CPU', threads=1, timeout=900)
    observed = runner.batch(1, 12)
    assert observed['device']['backend'] == 'CPU'
    runner.save_checkpoint(tmp_path/'drive', range(1, 13))
    result = runner.finish(tmp_path/'result.zip')
    response = client.post(f'/projects/{ready}/external-render/import', content=result.read_bytes(),
                           headers={'Content-Type': 'application/zip'})
    assert response.status_code == 200, response.text
    assert response.json()['state'] == 'HUMAN_REVIEW'
    again = client.post(f'/projects/{ready}/external-render/import', content=result.read_bytes(),
                        headers={'Content-Type': 'application/zip'})
    assert again.status_code == 200 and again.json()['duplicate'] is True
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(RenderArtifact)) == 1
        assert db.get(VideoProject, ready).approved_hash is None
    evidence = ROOT/'output/colab-validation'
    evidence.mkdir(parents=True, exist_ok=True)
    for name, source in {'input.zip': archive, 'result.zip': result, 'video.mp4': runner.folder/'video.mp4',
                          'thumbnail.png': runner.folder/'thumbnail.png'}.items():
        import shutil
        shutil.copyfile(source, evidence/name)
    atomic_json(evidence/'measurement.json', observed)
    print(json.dumps(observed))
