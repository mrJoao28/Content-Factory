"""Real bounded audio adapters. Local synthesis is instrumental, never singing."""
import array
import asyncio
import contextlib
import math
import os
import subprocess
import time
import wave
from uuid import uuid4

import httpx

from .config import settings
from .music_schema import MusicPlan
from .render import ffmpeg
from .security import Cancelled, ConfigurationRequired, Vault, run, terminate_tree

RATE = 24000


def process(args, *, cancel=lambda: False, timeout=600):
    """Cancel owned FFmpeg process without retaining media in memory or logging arguments."""
    child = subprocess.Popen([str(a) for a in args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                             start_new_session=os.name != 'nt')
    started = time.monotonic()
    try:
        while child.poll() is None:
            if cancel():
                raise Cancelled('Music processing cancelled')
            if time.monotonic()-started > timeout:
                raise ValueError('Music processing timed out; completed segment files are retained')
            time.sleep(.05)
        if child.returncode:
            raise ValueError('Audio processing failed; verify the input audio and FFmpeg installation')
    finally:
        if child.poll() is None:
            terminate_tree(child)


def normalize(source, destination):
    from .render import probe
    duration = float(probe(source)['format']['duration'])
    if not math.isfinite(duration) or not 0 < duration <= 3600:
        raise ValueError('Imported audio must have a measurable duration no longer than 3600 seconds')
    temporary = destination.with_suffix('.partial.wav')
    try:
        run([ffmpeg(), '-v', 'error', '-y', '-i', source, '-vn', '-ac', '1', '-ar', RATE,
             '-c:a', 'pcm_s16le', temporary], timeout=600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def instrumental(segment, path, *, cancel=lambda: False):
    """Original deterministic additive bell accompaniment, streamed 4096 samples at a time."""
    temporary = path.with_suffix('.partial.wav')
    # Original short pentatonic motif; no external music, samples or copyrighted melody.
    notes = (261.6256, 329.6276, 391.9954, 440.0, 391.9954, 329.6276, 293.6648, 261.6256)
    try:
        with wave.open(str(temporary), 'wb') as output:
            output.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            for offset in range(0, round(segment.duration*RATE), 4096):
                if cancel():
                    raise Cancelled('Instrumental cancelled')
                data = array.array('h')
                for i in range(offset, min(offset+4096, round(segment.duration*RATE))):
                    t = i/RATE
                    beat = t*segment.bpm_requested/60
                    frequency = notes[int(beat) % len(notes)]
                    envelope = min(1, (beat % 1)*25)*math.exp(-3*(beat % 1))
                    sample = .23*envelope*(math.sin(math.tau*frequency*t)+.2*math.sin(math.tau*frequency*2*t))
                    data.append(round(32767*sample))
                if os.sys.byteorder != 'little':
                    data.byteswap()
                output.writeframesraw(data.tobytes())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def sing(segment, directory, *, confirmed, cancel=lambda: False, client=None):
    async def supervised():
        task = asyncio.create_task(_sing(segment, directory, confirmed=confirmed, cancel=cancel, client=client))
        try:
            async with asyncio.timeout(600):
                while not task.done():
                    if cancel():
                        raise Cancelled('Singing cancelled; provider charges may still apply')
                    await asyncio.wait((task,), timeout=.1)
                return await task
        except TimeoutError as exc:
            raise ConfigurationRequired('Music generation timed out; check provider history before a paid retry') from exc
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
    return asyncio.run(supervised())


async def _sing(segment, directory, *, confirmed, cancel, client):
    """Official ElevenLabs Music API; one paid request, no automatic retries/fallback."""
    if not confirmed:
        raise ValueError('Explicit paid generation confirmation is required for each song')
    if segment.kind != 'song' or not 3 <= segment.duration <= 300:
        raise ValueError('Singing adapter accepts songs of 3-300 seconds; split explicitly or import audio')
    if len(segment.sections) > 30 or any(not 3 <= s.duration <= 120 for s in segment.sections):
        raise ValueError('Music v2.5 requires at most 30 lyric sections, each 3-120 seconds; edit before a paid request')
    credentials = Vault().get('elevenlabs_music')
    if not credentials or not credentials.get('api_key'):
        raise ConfigurationRequired('Configure ElevenLabs Music in the secure vault or import a song')
    # v2/v2.5 use chunks; the older v1 global_styles/sections format is not sent.
    body = {'model_id': 'music_v2_5', 'store_for_inpainting': False, 'composition_plan': {
        'chunks': [{'text': f'[{s.kind.title()} {i+1}]\n'+'\n'.join(s.lines),
                    'duration_ms': round(s.duration*1000), 'context_adherence': 'high',
                    'positive_styles': ['Original English children song', 'clear gentle singing',
                        segment.direction, f'{segment.bpm_requested} BPM, {segment.meter} meter', *segment.instruments],
                    'negative_styles': ['harsh distortion', 'frightening sounds']}
                   for i, s in enumerate(segment.sections)]}}
    started = time.monotonic()
    owned = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(20, read=300), follow_redirects=False)
    destination = directory/(uuid4().hex+'.mp3')
    temporary = destination.with_suffix('.partial')
    try:
        if cancel():
            raise Cancelled('Singing request cancelled before sending')
        async with client.stream('POST', 'https://api.elevenlabs.io/v1/music',
                           params={'output_format': 'mp3_44100_128'}, json=body,
                           headers={'xi-api-key': credentials['api_key']}) as response:
            if response.status_code != 200:
                messages = {401: 'Music credentials rejected', 403: 'Music permission or subscription unavailable',
                            429: 'Music usage limit reached; do not automatically retry'}
                raise ConfigurationRequired(messages.get(response.status_code,
                     'Music provider failed; a charge may have occurred. Check provider history before retrying'))
            if 'audio/' not in response.headers.get('content-type', '') and response.headers.get('content-type') != 'application/octet-stream':
                raise ValueError('Music provider returned an incompatible response; no audio accepted')
            size = 0
            with temporary.open('wb') as output:
                async for chunk in response.aiter_bytes(65536):
                    if cancel():
                        raise Cancelled('Singing cancelled; provider charges may still apply')
                    size += len(chunk)
                    if size > 32*1024**2 or time.monotonic()-started > 600:
                        raise ValueError('Music response exceeds the finite size or execution limit')
                    output.write(chunk)
            if not size:
                raise ValueError('Music provider returned empty audio')
            song_id = response.headers.get('song-id', '')[:200]
        temporary.replace(destination)
        return destination, song_id
    except httpx.HTTPError as exc:
        raise ConfigurationRequired('Music network request failed; check provider history before a paid retry') from exc
    finally:
        temporary.unlink(missing_ok=True)
        if owned:
            await client.aclose()


def analyze(path, *, cancel=lambda: False):
    peak, energy, count, silence, longest = 0, 0, 0, 0, 0
    with wave.open(str(path), 'rb') as source:
        if source.getparams()[:3] != (1, 2, RATE):
            raise ValueError('Mix must be mono 24 kHz PCM16')
        while chunk := source.readframes(2400):
            if cancel():
                raise Cancelled('Mix validation cancelled')
            values = array.array('h', chunk)
            if os.sys.byteorder != 'little':
                values.byteswap()
            maximum = max((abs(v) for v in values), default=0)
            peak = max(peak, maximum)
            energy += sum(v*v for v in values)
            count += len(values)
            silence = silence+len(values) if maximum < 32 else 0
            longest = max(longest, silence)
    if peak >= 32760:
        raise ValueError('Mix is clipping; lower segment or stem volumes before validating')
    if not count or energy/count < 16:
        raise ValueError('Mix is empty or silent; silence is not completed narration or singing')
    return dict(peak_dbfs=20*math.log10(max(peak, 1)/32768),
                rms_dbfs=10*math.log10(energy/count/32768**2),
                longest_silence=longest/RATE, duration=count/RATE)


def mix(project, *, cancel=lambda: False, progress=lambda completed, total: None):
    from .music import signature, take_path, timeline
    from .security import digest
    plan = MusicPlan.model_validate(project.music_plan).validate_duration(project.target_duration)
    if any(row['conflict'] for row in timeline(project)):
        raise ValueError('Resolve missing audio or measured-duration conflicts in the timeline; nothing was trimmed or stretched')
    folder = settings.storage_root/'music-mixes'/project.id/str(project.revision)
    folder.mkdir(parents=True, exist_ok=True)
    cache = folder.parent/'segments'
    cache.mkdir(parents=True, exist_ok=True)
    segments, sources = [], []
    for segment in plan.segments:
        if cancel():
            raise Cancelled('Mix cancelled; completed segments remain cached')
        takes = project.music_state.get('takes', {}).get(segment.id, {})
        if segment.kind == 'pause':
            recipe = {'pause': segment.duration}
        else:
            for take in takes.values():
                if take['signature'] != signature(segment):
                    raise ValueError('Song changed; select audio for the current lyrics and duration')
                take_path(take)
            recipe = {'segment': segment.model_dump(), 'takes': takes}
        import hashlib
        import json
        key = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()
        path = cache/(key+'.wav')
        index = path.with_suffix('.json')
        valid = False
        if path.exists() and index.exists() and index.stat().st_size < 1024:
            try:
                valid = json.loads(index.read_text())['sha256'] == digest(path)
            except (ValueError, KeyError):
                pass
        if not valid:
            temporary = path.with_suffix('.partial.wav')
            try:
                if segment.kind == 'pause':
                    process([ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i', f'anullsrc=r={RATE}:cl=mono',
                             '-t', segment.duration, '-c:a', 'pcm_s16le', temporary], cancel=cancel)
                else:
                    roles = ['premixed'] if 'premixed' in takes else list(takes)
                    args, filters, labels = [ffmpeg(), '-v', 'error', '-y'], [], []
                    for i, role in enumerate(roles):
                        args += ['-i', take_path(takes[role])]
                        gain = segment.instrumental_gain if role == 'instrumental' and len(roles) > 1 else segment.effects_gain if role == 'effects' else segment.gain
                        filters.append(f'[{i}:a]volume={gain}[t{i}]')
                        labels.append(f'[t{i}]')
                    if segment.ducking and 'instrumental' in roles and ('vocals' in roles or 'speech' in roles):
                        i = roles.index('instrumental')
                        j = roles.index('vocals' if 'vocals' in roles else 'speech')
                        filters += [f'[t{j}]asplit[v][side]', f'[t{i}][side]sidechaincompress=threshold=0.025:ratio=6[duck]']
                        labels[i], labels[j] = '[duck]', '[v]'
                    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=longest:normalize=0,'
                                   f'afade=t=in:d={segment.fade_in},afade=t=out:st={max(0, segment.duration-segment.fade_out)}:d={segment.fade_out}[out]')
                    process([*args, '-filter_complex', ';'.join(filters), '-map', '[out]', '-ar', RATE,
                             '-ac', 1, '-c:a', 'pcm_s16le', temporary], cancel=cancel)
                    segment_report = analyze(temporary, cancel=cancel)
                    if segment_report['longest_silence'] > 2:
                        raise ValueError('Unexpected silence longer than two seconds; split an explicit pause or edit the source audio')
                temporary.replace(path)
                from content_factory_render.archive import atomic_json
                atomic_json(index, {'sha256': digest(path), 'recipe': key})
            finally:
                temporary.unlink(missing_ok=True)
        segments.append(path)
        sources.append({'segment': segment.id, 'sha256': digest(path), 'recipe': key})
        progress(len(segments), len(plan.segments))
    destination = folder/'final.wav'
    temporary = destination.with_suffix('.partial.wav')
    try:
        with wave.open(str(temporary), 'wb') as output:
            output.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            for path in segments:
                with wave.open(str(path), 'rb') as source:
                    while chunk := source.readframes(8192):
                        if cancel():
                            raise Cancelled('Mix assembly cancelled')
                        output.writeframesraw(chunk)
        report = analyze(temporary, cancel=cancel)
        if abs(report['duration']-project.target_duration) > 1/project.fps:
            raise ValueError('Measured final mix conflicts with project duration; explicitly revise the timeline')
        temporary.replace(destination)
        return destination, {**report, 'segments': sources, 'format': 'PCM16 WAV mono 24000 Hz'}
    finally:
        temporary.unlink(missing_ok=True)
