"""Controlled audio fixtures are not evidence of real singing generation."""
import copy
import io
import wave

import httpx
import pytest
from factory.config import settings
from factory.db import Session
from factory.models import ExternalRenderExport, ProductionJob, VideoProject, utcnow
from factory.music_schema import MusicPlan, MusicSegment
from factory.queue import Worker, claim
from factory.security import Cancelled, digest
from sqlalchemy import select
from test_render import sine


def plan(duration=8):
    return {'format': 'musical_story', 'educational_goal': 'Share flowers with a friend',
        'characters': ['dino'], 'environment': 'magic_forest', 'beginning': 'Dino finds a flower',
        'development': 'He offers it to a friend', 'conclusion': 'Sharing makes both smile',
        'segments': [{'id': 'share', 'title': 'A flower for you', 'kind': 'song', 'duration': duration,
            'visible_action': 'Dino sways, then waves to a friend', 'sections': [
                {'kind': 'verse', 'duration': duration/2, 'lines': ['One little flower, bright in the sun']},
                {'kind': 'chorus', 'duration': duration/2, 'lines': ['Share a little kindness, smiles for everyone']}]}]}


@pytest.fixture
def musical(client):
    response = client.post('/projects', json={'idea': 'An original musical story about sharing flowers',
        'channel_id': 'wondernest', 'target_duration': 8, 'musical_format': 'musical_story',
        'visual': {'engine': 'blender_3d', 'execution_location': 'colab', 'external_hardware': 'CPU'}})
    assert response.status_code == 201, response.text
    return response.json()


def save(client, project, data=None, revision=None, **kwargs):
    response = client.patch(f"/projects/{project['id']}/music", json={
        'revision': revision or project['revision'], 'plan': data or plan(), **kwargs})
    assert response.status_code == 200, response.text
    return response.json()['revision']


def test_variable_duration_and_markers():
    value = plan(35)
    value['segments'] *= 2
    value['segments'][1] = copy.deepcopy(value['segments'][1])
    value['segments'][1]['id'] = 'again'
    result = MusicPlan.model_validate(value).validate_duration(70)
    with pytest.raises(ValueError, match='match project'):
        result.validate_duration(35)
    invalid = plan()
    invalid['segments'][0]['beats'] = [{'time': 8, 'source': 'manual'}]
    with pytest.raises(ValueError, match='Beat marker'):
        MusicPlan.model_validate(invalid)
    invalid = plan()
    invalid['segments'][0]['events'] = [dict(time=0, end=4, character_id='dino', action='sway'),
                                      dict(time=3, end=5, character_id='dino', action='clap')]
    with pytest.raises(ValueError, match='overlap'):
        MusicPlan.model_validate(invalid)


def test_music_uses_queue_and_real_instrumental(client, musical):
    assert musical['status'] == 'WAITING_FOR_MUSIC'
    assert claim('no-auto-generation') is None
    revision = save(client, musical)
    response = client.post(f"/projects/{musical['id']}/music/operations", json={
        'revision': revision, 'kind': 'instrumental', 'segment_id': 'share'})
    assert response.status_code == 202, response.text
    assert Worker().once()
    current = client.get(f"/projects/{musical['id']}/music").json()
    assert current['audio']['takes']['share']['instrumental']['duration'] == 8
    assert current['timeline'][0]['state'] == 'audio_required'  # instrumental is not singing
    response = client.post(f"/projects/{musical['id']}/music/operations", json={
        'revision': current['revision'], 'kind': 'mix'})
    assert response.status_code == 422


def test_import_mix_preview_and_colab_use_identical_audio(client, musical, tmp_path):
    revision = save(client, musical)
    audio = tmp_path/'fixture.wav'
    sine(audio, seconds=8)
    source_hash = digest(audio)
    response = client.post(f"/projects/{musical['id']}/music/share/import", params={
        'revision': revision, 'rights': 'Test synthesized tone, not singing', 'role': 'premixed'},
        files={'file': ('fixture.wav', audio.read_bytes(), 'audio/wav')})
    assert response.status_code == 200, response.text
    revision = response.json()['revision']
    assert client.post(f"/projects/{musical['id']}/music/operations", json={
        'revision': revision, 'kind': 'mix'}).status_code == 202
    assert Worker().once()
    current = client.get(f"/projects/{musical['id']}/music").json()
    assert current['final'], client.get(f"/projects/{musical['id']}").text
    preview = client.get(f"/projects/{musical['id']}/narration")
    with wave.open(io.BytesIO(preview.content)) as output:
        assert output.getsampwidth() == 2 and output.getnframes()/output.getframerate() == 8
    from factory.external_render import prepared
    with Session.begin() as db:
        project = db.get(VideoProject, musical['id'])
        project.storyboard = {'duration': 8, 'scenes': [{'duration': 8, 'environment': 'magic_forest',
            'characters': [{'character_id': 'dino', 'asset_version': 'dino-v1'}], 'camera': [{'time': 0}]}]}
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project.id,
                                                   ProductionJob.revision == revision))
        job.checkpoint = {**job.checkpoint, 'audio': 'obsolete-file.wav'}
        _, _, final = prepared(project, job)
        assert final.read_bytes() == preview.content
        assert digest(final) == current['final']['sha256'] != source_hash
        project.status = job.state = 'WAITING_FOR_EXTERNAL_RENDER'
    exported = client.post(f"/projects/{musical['id']}/external-render/export", json={'expected_revision': revision})
    assert exported.status_code == 200, exported.text
    replacement = plan()
    replacement['segments'][0]['sections'][0]['lines'] = ['A new original verse']
    save(client, musical, replacement, revision=revision)
    with Session() as db:
        row = db.get(ExternalRenderExport, exported.json()['export_id'])
        assert row.state == 'SUPERSEDED'
    assert client.get(f"/projects/{musical['id']}/music").json()['audio']['takes']['share'] == {}


def test_timing_conflict_and_active_lease_guard(client, musical, tmp_path):
    revision = save(client, musical)
    audio = tmp_path/'wrong.wav'
    sine(audio, seconds=9)
    response = client.post(f"/projects/{musical['id']}/music/share/import", params={
        'revision': revision, 'rights': 'Test fixture', 'role': 'premixed'},
        files={'file': ('fixture.wav', audio.read_bytes(), 'audio/wav')})
    assert response.status_code == 200
    current = client.get(f"/projects/{musical['id']}/music").json()
    assert current['timeline'][0]['state'] == 'duration_conflict'
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == musical['id'],
                                                   ProductionJob.revision == current['revision']))
        job.owner, job.lease_until = 'busy', utcnow().replace(year=2099)
    assert client.patch(f"/projects/{musical['id']}/music", json={
        'revision': current['revision'], 'plan': plan()}).status_code == 409


def test_singing_adapter_official_request_no_retry(monkeypatch, tmp_path):
    from factory.music_audio import sing
    monkeypatch.setattr('factory.music_audio.Vault.get', lambda self, slot: {'api_key': 'private-test-value'})
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(429, json={'detail': 'private provider response'})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match='confirmation'):
            sing(MusicSegment.model_validate(plan()['segments'][0]), tmp_path, confirmed=False, client=client)
        with pytest.raises(Exception, match='usage limit'):
            sing(MusicSegment.model_validate(plan()['segments'][0]), tmp_path, confirmed=True, client=client)
    finally:
        import asyncio
        asyncio.run(client.aclose())
    assert len(requests) == 1
    import json
    body = json.loads(requests[0].content)
    assert str(requests[0].url).startswith('https://api.elevenlabs.io/v1/music?')
    assert body['model_id'] == 'music_v2_5'
    assert plan()['segments'][0]['sections'][1]['lines'][0] in body['composition_plan']['chunks'][1]['text']
    assert 'sections' not in body['composition_plan']


def test_cancel_local_instrumental(tmp_path):
    from factory.music_audio import instrumental
    path = tmp_path/'music.wav'
    with pytest.raises(Cancelled):
        instrumental(MusicSegment.model_validate(plan()['segments'][0]), path, cancel=lambda: True)
    assert not path.exists() and not path.with_suffix('.partial.wav').exists()


def test_secret_validation_does_not_echo_credentials(client):
    response = client.post('/music/elevenlabs', json={'api_key': 'secret'})
    assert response.status_code == 422 and 'secret' not in response.text


def test_singing_cancels_while_waiting_for_response(monkeypatch, tmp_path):
    import asyncio
    import time
    from factory.music_audio import sing
    monkeypatch.setattr('factory.music_audio.Vault.get', lambda *_: {'api_key': 'private-test'})
    async def handler(request):
        await asyncio.sleep(10)
        return httpx.Response(200, content=b'not reached')
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    started = time.monotonic()
    try:
        with pytest.raises(Cancelled):
            sing(MusicSegment.model_validate(plan()['segments'][0]), tmp_path, confirmed=True,
                 cancel=lambda: time.monotonic()-started > .1, client=client)
    finally:
        asyncio.run(client.aclose())
    assert time.monotonic()-started < 2


def test_long_segmented_mix_and_selective_invalidation(client, musical, tmp_path):
    from factory.render import ffmpeg
    from factory.security import run
    value = plan(300)
    first = value['segments'][0]
    first.update(kind='instrumental', sections=[])
    second = {**copy.deepcopy(first), 'id': 'second'}
    value['segments'] = [first, second, {'id': 'pause', 'title': 'Explicit pause', 'kind': 'pause',
        'duration': 20, 'visible_action': 'A calm pause with no narration'}]
    revision = save(client, musical, value, target_duration=620)
    path = tmp_path/'long.wav'
    run([ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i',
         'sine=frequency=220:sample_rate=24000:duration=300', '-c:a', 'pcm_s16le', path])
    for name in ['share', 'second']:
        response = client.post(f"/projects/{musical['id']}/music/{name}/import", params={
            'revision': revision, 'rights': 'Controlled test tone, not music vocals', 'role': 'instrumental'},
            files={'file': ('known.wav', path.read_bytes(), 'audio/wav')})
        assert response.status_code == 200, response.text
        revision = response.json()['revision']
    assert client.post(f"/projects/{musical['id']}/music/operations", json={
        'revision': revision, 'kind': 'mix'}).status_code == 202
    assert Worker().once()
    current = client.get(f"/projects/{musical['id']}/music").json()
    assert current['final']['duration'] == 620
    assert len(current['audio']['mix_report']['segments']) == 3
    retained = current['audio']['takes']['second']
    value['segments'][0]['direction'] = 'A new original musical arrangement'
    save(client, musical, value, revision=current['revision'])
    updated = client.get(f"/projects/{musical['id']}/music").json()
    assert updated['audio']['takes']['share'] == {}
    assert updated['audio']['takes']['second'] == retained
    assert not updated['final'] and updated['history']


def test_legacy_import_beats_obsolete_generated_checkpoint(client, musical, tmp_path):
    from factory.external_render import prepared
    stale = settings.output_dir/'stale.wav'
    replacement = tmp_path/'replacement.wav'
    sine(stale, seconds=8)
    from factory.render import ffmpeg
    from factory.security import run
    run([ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i',
         'sine=frequency=660:sample_rate=24000:duration=8', replacement])
    with Session.begin() as db:
        p = db.get(VideoProject, musical['id'])
        p.narration = {'generated_path': str(stale)}
        p.music_state = {}
        p.storyboard = {'duration': 8, 'scenes': [{'duration': 8, 'environment': 'magic_forest',
            'characters': [{'character_id': 'dino', 'asset_version': 'dino-v1'}], 'camera': [{'time': 0}]}]}
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == p.id))
        job.checkpoint = {**job.checkpoint, 'audio': str(stale)}
    response = client.post(f"/projects/{musical['id']}/audio", files={
        'file': ('replacement.wav', replacement.read_bytes(), 'audio/wav')})
    assert response.status_code == 200
    with Session.begin() as db:
        p = db.get(VideoProject, musical['id'])
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == p.id))
        _, _, audio = prepared(p, job)
        assert digest(audio) == digest(replacement) != digest(stale)
    preview = client.get(f"/projects/{musical['id']}/narration")
    assert preview.content == replacement.read_bytes()


def test_real_supported_music_actions_and_offscreen_mouth(client, musical):
    from factory.music_animation import synchronize
    from factory.visual_schema import VisualBoard
    value = plan()
    value['segments'][0]['events'] = [dict(time=0, end=4, character_id='dino', action='clap'),
                                     dict(time=4, end=8, character_id='dino', action='dance')]
    save(client, musical, value)
    board = VisualBoard(duration=8, scenes=[dict(duration=8, environment='magic_forest',
         characters=[dict(character_id='dino', asset_version='dino-v1')], camera=[dict(time=0)])])
    with Session() as db:
        result = synchronize(db.get(VideoProject, musical['id']), board)
    assert [a.kind for a in result.scenes[0].actions] == ['clap', 'dance']
    assert not result.scenes[0].singing
    from content_factory_render.scene import Action
    board.scenes[0].actions = [Action(character_id='dino', kind='wave', start=0, end=8)]
    with Session() as db, pytest.raises(ValueError, match='conflicts'):
        synchronize(db.get(VideoProject, musical['id']), VisualBoard.model_validate(board.model_dump()))


def test_real_blender_musical_round_trip(client, musical, tmp_path):
    import os
    import shutil

    from content_factory_render.archive import source_sha, unpack
    from content_factory_render.contract import InputPackage
    from content_factory_render.runner import Renderer, load_package
    from factory.external_render import TEMPLATE
    from factory.music_animation import synchronize
    from factory.render import ffmpeg
    from factory.render_release import RENDER_COMMIT
    from factory.visual_schema import VisualBoard
    executable = os.environ.get('FACTORY_TEST_BLENDER')
    if not executable:
        pytest.skip('Set FACTORY_TEST_BLENDER for an actual isolated Cycles CPU music round-trip')
    with Session.begin() as db:
        p = db.get(VideoProject, musical['id'])
        p.target_duration, p.width, p.height = .5, 64, 96
    value = plan()
    value['segments'][0].update(kind='instrumental', duration=.5, sections=[],
        events=[dict(time=0, end=.5, character_id='dino', action='sway')])
    revision = save(client, musical, value)
    for kind in ['instrumental', 'mix']:
        response = client.post(f"/projects/{musical['id']}/music/operations", json={
            'revision': revision, 'kind': kind, 'segment_id': 'share'})
        assert response.status_code == 202, response.text
        assert Worker().once()
        revision = client.get(f"/projects/{musical['id']}/music").json()['revision']
    with Session.begin() as db:
        p = db.get(VideoProject, musical['id'])
        p.storyboard = synchronize(p, VisualBoard(duration=.5, scenes=[dict(duration=.5,
            environment='magic_forest', particles=0,
            characters=[dict(character_id='dino', asset_version='dino-v1')], camera=[dict(time=0)])])).model_dump()
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == p.id,
                                                   ProductionJob.revision == revision))
        p.status = job.state = 'WAITING_FOR_EXTERNAL_RENDER'
    response = client.post(f"/projects/{musical['id']}/external-render/export", json={'expected_revision': revision})
    assert response.status_code == 200, response.text
    with Session() as db:
        exported = db.get(ExternalRenderExport, response.json()['export_id'])
        archive = settings.output_dir/exported.path
        package = InputPackage.model_validate(exported.manifest)
    extracted = tmp_path/'portable'
    assert load_package(archive, extracted, trusted_commit=RENDER_COMMIT, template=TEMPLATE) == package
    assert package.template_sha256 == source_sha(TEMPLATE)
    renderer = Renderer(package, extracted, tmp_path/'render', blender=executable,
        template=TEMPLATE, ffmpeg=ffmpeg(), backend='CPU', threads=1, timeout=600, disk_mb=128)
    renderer.render(batch_size=12, persistent=tmp_path/'drive')
    result = renderer.finish(tmp_path/'result.zip')
    imported = client.post(f"/projects/{musical['id']}/external-render/import", content=result.read_bytes(),
        headers={'Content-Type': 'application/zip'})
    assert imported.status_code == 200, imported.text
    current = client.get(f"/projects/{musical['id']}").json()
    assert current['status'] == 'HUMAN_REVIEW' and not current['approved_hash']
    assert current['artifacts'][0]['probe']['checks']
    evidence = os.environ.get('FACTORY_MUSIC_EVIDENCE')
    if evidence:
        from pathlib import Path
        target = Path(evidence)
        target.mkdir(parents=True, exist_ok=True)
        for src, name in [(archive, 'input.zip'), (result, 'result.zip')]:
            shutil.copyfile(src, target/name)
        unpack(result, target/'result')
        (target/'README.txt').write_text('Real Cycles CPU test: 12 frames, 64x96, original local instrumental. '
            'No sung vocal or actual Colab/GPU execution. Test media is not a finished artistic demo.', encoding='utf-8')


def test_pipeline_uses_music_checkpoints_without_piper_or_codex(client, musical, monkeypatch):
    from contextlib import nullcontext

    from factory.schemas import AgentResult
    from factory.visual_schema import VisualBoard
    value = plan()
    value['segments'][0].update(kind='instrumental', sections=[], events=[
        dict(time=0, end=8, character_id='dino', action='sway')])
    revision = save(client, musical, value)
    for kind in ['instrumental', 'mix']:
        assert client.post(f"/projects/{musical['id']}/music/operations", json={
            'revision': revision, 'kind': kind, 'segment_id': 'share'}).status_code == 202
        assert Worker().once()
        revision = client.get(f"/projects/{musical['id']}/music").json()['revision']
    calls = []
    class Boundary:
        def generate(self, role, context, response_type, **kwargs):
            calls.append(role)
            if response_type is VisualBoard:
                return VisualBoard(duration=8, scenes=[dict(duration=8, environment='magic_forest',
                    characters=[dict(character_id='dino', asset_version='dino-v1')], camera=[dict(time=0)])])
            assert response_type is AgentResult
            return AgentResult(summary='Controlled external text fixture', flags=[])
        def persistence_guard(self):
            return nullcontext()
    monkeypatch.setattr('factory.pipeline.get_provider', lambda *_: Boundary())
    monkeypatch.setattr('factory.codex.CodexProvider.generate', lambda *_a, **_k: pytest.fail('Codex called'))
    monkeypatch.setattr('factory.pipeline.Piper.scenes', lambda *_a, **_k: pytest.fail('Old speech/score called'))
    with Session.begin() as db:
        p = db.get(VideoProject, musical['id'])
        p.script = dict(title='Sharing music', description='Original educational music', beats=['Share a flower'])
        p.metadata_json = dict(title='Sharing music', description='Original local instrumental', tags=[])
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == p.id,
                                                   ProductionJob.revision == revision))
        job.checkpoint = {**job.checkpoint, 'creative_director': {'summary': 'Keep this concept', 'flags': []},
                           'script_writer': p.script}
    assert client.post(f"/projects/{musical['id']}/jobs/resume", json={}).status_code == 200
    assert Worker().once()
    detail = client.get(f"/projects/{musical['id']}").json()
    assert detail['status'] == 'WAITING_FOR_EXTERNAL_RENDER', detail['jobs'][0]['error']
    assert calls.count('Storyboard Planner') == 1
    assert detail['jobs'][0]['checkpoint']['_music_boards']['share']['board']['duration'] == 8
    assert detail['jobs'][0]['checkpoint']['creative_director']['summary'] == 'Keep this concept'
    assert detail['storyboard']['scenes'][0]['actions'][0]['kind'] == 'sway'


def test_compilation_real_mp4_units_require_new_human_review(client, musical):
    from factory.models import RenderArtifact
    from factory.render import ffmpeg, validate_video
    from factory.security import run
    units = []
    for index in range(2):
        created = client.post('/projects', json={'idea': f'Controlled compilation source fixture number {index}',
                                               'channel_id': 'wondernest'}).json()
        folder = settings.output_dir/created['id']/'1'
        folder.mkdir(parents=True)
        movie = folder/'video.mp4'
        run([ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=64x96:r=24:d=4',
             '-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=24000:duration=4',
             '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', movie])
        report = validate_video(movie, 64, 96, 24, 4)
        hashed = digest(movie)
        with Session.begin() as db:
            p = db.get(VideoProject, created['id'])
            p.width, p.height, p.fps, p.target_duration, p.status = 64, 96, 24, 4, 'HUMAN_REVIEW'
            db.add(RenderArtifact(project_id=p.id, revision=1, path=str(movie.relative_to(settings.output_dir)),
                                  sha256=hashed, probe=report, render_seconds=0))
            job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == p.id))
            job.state = 'HUMAN_REVIEW'
        assert client.post(f"/projects/{created['id']}/review", json={
            'approved': True, 'artifact_hash': hashed, 'notes': 'Controlled test source reviewed'}).status_code == 200
        units.append(dict(id=f'unit-{index}', title='Reviewed unit', kind='unit', duration=4,
                          source_project_id=created['id'], source_artifact_hash=hashed,
                          visible_action='Keep the complete source unit'))
    value = {**plan(), 'format': 'compilation', 'segments': units}
    with Session.begin() as db:
        p = db.get(VideoProject, musical['id'])
        p.width, p.height, p.fps = 64, 96, 24
    revision = save(client, musical, value)
    response = client.post(f"/projects/{musical['id']}/music/operations", json={
        'revision': revision, 'kind': 'assemble'})
    assert response.status_code == 202, response.text
    assert Worker().once()
    detail = client.get(f"/projects/{musical['id']}").json()
    assert detail['status'] == 'HUMAN_REVIEW', detail['jobs'][0]['error']
    assert not detail['approved_hash']
    assert len(detail['artifacts']) == 1
    assert detail['artifacts'][0]['probe']['visual']['engine'] == 'reviewed-unit-compilation'


def test_storyboard_segment_checkpoint_recovers_after_interruption(client, musical):
    from contextlib import nullcontext

    from factory.music_animation import plan_board
    from factory.security import ConfigurationRequired
    from factory.visual_schema import VisualBoard
    value = plan(4)
    value['segments'].append({**copy.deepcopy(value['segments'][0]), 'id': 'second'})
    revision = save(client, musical, value)
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == musical['id'],
                                                   ProductionJob.revision == revision))
        job.state = 'DRAFT'
        job_id = job.id
    assert claim('planner') == job_id
    calls = []
    class Boundary:
        fail = True
        def generate(self, role, context, response_type, **kwargs):
            segment_id = context['music_segment']['id']
            calls.append(segment_id)
            if segment_id == 'second' and self.fail:
                raise ConfigurationRequired('Controlled external interruption')
            return VisualBoard(duration=4, scenes=[dict(duration=4, environment='magic_forest',
                characters=[dict(character_id='dino', asset_version='dino-v1')], camera=[dict(time=0)])])
        def persistence_guard(self):
            return nullcontext()
    provider = Boundary()
    context = dict(music_plan=MusicPlan.model_validate(value).model_dump(), duration=8, fps=24,
        channel='wondernest', visual_selection={'character': 'dino', 'environment': 'magic_forest'})
    with pytest.raises(ConfigurationRequired):
        plan_board(musical['id'], job_id, 'planner', provider, {'provider': 'controlled'}, context, {}, lambda: False)
    with Session() as db:
        saved = db.get(ProductionJob, job_id).checkpoint
    assert set(saved['_music_boards']) == {'share'}
    provider.fail = False
    result = plan_board(musical['id'], job_id, 'planner', provider, {'provider': 'controlled'}, context, saved, lambda: False)
    assert result.duration == 8 and calls == ['share', 'second', 'second']
