"""Finite interactive rendering, independent of FastAPI, SQLite and credentials."""
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image

from .archive import atomic_json, identity, pack, sha, source_sha, unpack
from .contract import InputPackage, ResultPackage


def valid_frame(path, width, height):
    try:
        with Image.open(path) as image:
            if image.format != 'PNG' or image.size != (width, height):
                return False
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def execute(args, *, timeout, cancel=lambda: False):
    """Bounded logs to a temporary file; interruption terminates the process group."""
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen([str(a) for a in args], stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                   shell=False, start_new_session=os.name != 'nt',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancel():
                    raise InterruptedError('Rendering cancelled; completed checkpoint shards remain available')
                if time.monotonic()-started > timeout:
                    raise TimeoutError('Render timeout; resume compatible saved checkpoints')
                time.sleep(.2)
            if process.returncode:
                raise RuntimeError('Render process failed. Check GPU compatibility/VRAM, free disk and selected backend; no CPU fallback occurred')
        finally:
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10)
                else:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def load_package(archive, destination, *, trusted_commit, template):
    unpack(archive, destination, allowed={'manifest.json', 'audio/narration.wav'})
    raw = Path(destination, 'manifest.json')
    if raw.stat().st_size > 2*1024**2:
        raise ValueError('Manifest exceeds 2 MiB')
    package = InputPackage.model_validate_json(raw.read_bytes())
    if package.render_commit != trusted_commit or package.template_sha256 != source_sha(template):
        raise ValueError('Package requires a different trusted render release. Explicitly load its reviewed repository commit first')
    audio = Path(destination, package.audio_path)
    if audio.stat().st_size != package.audio.size or sha(audio) != package.audio.sha256:
        raise ValueError('Audio integrity mismatch')
    return package


class Renderer:
    def __init__(self, package, extracted, work, *, blender, template, ffmpeg='ffmpeg', threads=2,
                 backend='CPU', timeout=1800, disk_mb=8192):
        preparation_started = time.monotonic()
        self.package, self.extracted = package, Path(extracted)
        self.blender, self.template, self.ffmpeg = blender, Path(template), ffmpeg
        if not 1 <= threads <= 8 or not 1 <= timeout <= 21600 or not 128 <= disk_mb <= 65536:
            raise ValueError('Execution limits outside supported bounds')
        if backend not in {'CPU', 'OPTIX', 'CUDA'}:
            raise ValueError('Choose an explicit Cycles backend')
        policy = package.profile.hardware
        if (policy == 'GPU' and backend == 'CPU') or (policy != 'GPU' and policy != backend):
            raise ValueError('Backend differs from exported policy; reexport explicitly to change hardware')
        version = subprocess.run([str(blender), '--version'], capture_output=True, timeout=30, check=True).stdout.decode().splitlines()[0]
        if not (version.startswith('Blender 4.5.') or version.startswith('Blender 5.2.')):
            raise ValueError('Unsupported Blender release; use the pinned notebook version')
        if source_sha(template) != package.template_sha256:
            raise ValueError('Trusted template differs from the exported release')
        Path(work).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temporary:
            device_file = Path(temporary)/'device.json'
            execute([blender, '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', 1,
                     '--python', self.template.with_name('cycles_devices.py'), '--', backend, device_file], timeout=60)
            device_identity = json.loads(device_file.read_text())
        if backend != 'CPU' and shutil.which('nvidia-smi'):
            driver = subprocess.run(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
                                    capture_output=True, timeout=20, check=False).stdout.decode(errors='replace')
            device_identity['driver_versions'] = sorted({line for line in driver.splitlines()
                                                         if re.fullmatch(r'[0-9.]{1,40}', line)})
        self.config = {'input': identity(package.model_dump(mode='json')), 'blender': version,
                       'backend': backend, 'engine': 'CYCLES', 'threads': threads,
                       'template': source_sha(template), 'profile': package.profile.model_dump(), 'device': device_identity}
        # Export IDs correlate transfers; identical semantic inputs may reuse compatible frames.
        self.config["input"] = identity({k: v for k, v in package.model_dump(mode="json").items() if k != "export_id"})
        self.cache_id = identity(self.config)
        self.folder = Path(work)/self.cache_id
        self.folder.mkdir(parents=True, exist_ok=True)
        self.timeout, self.disk_mb = timeout, disk_mb
        self.total = round(package.board.duration*package.profile.fps)
        estimate = self.total*package.profile.width*package.profile.height*3+64*1024**2
        if estimate > disk_mb*1024**2:
            raise ValueError('Full timeline exceeds configured frame disk budget; change the profile explicitly or increase the finite budget')
        self.started = time.monotonic()
        self._complete = None
        self.render_seconds, self.reused = 0., len(self.frames())
        self.report = None
        self.preparation_seconds = time.monotonic()-preparation_started

    def frames(self, refresh=False):
        p = self.package.profile
        if refresh or getattr(self, '_complete', None) is None:
            self._complete = {i for i in range(1, self.total+1)
                              if valid_frame(self.folder/f'{i:06}.png', p.width, p.height)}
        return set(self._complete)

    def batch(self, start, end, *, cancel=lambda: False):
        if not 1 <= start <= end <= self.total or end-start >= 120:
            raise ValueError('Frame batch must contain 1–120 valid timeline frames')
        p = self.package.profile
        required = (end-start+1)*p.width*p.height*3 + 64*1024**2
        if required > self.disk_mb*1024**2 or shutil.disk_usage(self.folder).free < required:
            raise ValueError('Insufficient configured disk budget or free disk')
        cfg = {**p.model_dump(), 'board': self.package.board.model_dump(mode='json'),
               'threads': self.config['threads'], 'backend': self.config['backend'],
               'device_report': str(self.folder/'device.json'), 'frame_start': start, 'frame_end': end}
        atomic_json(self.folder/'manifest.json', cfg)
        # Never let a truncated PNG cause the trusted template to skip a missing frame.
        for i in range(start, end+1):
            frame = self.folder/f'{i:06}.png'
            if frame.exists() and not valid_frame(frame, p.width, p.height):
                frame.unlink()
        before = self.frames()
        started = time.monotonic()
        try:
            execute([self.blender, '--background', '--factory-startup', '--disable-autoexec', '--threads',
                     self.config['threads'], '--python-exit-code', 1, '--python', self.template, '--',
                     self.folder/'manifest.json'], timeout=self.timeout, cancel=cancel)
        finally:
            # Validate this bounded batch once, including partial completion on cancellation.
            self._complete.difference_update(range(start, end+1))
            self._complete.update(i for i in range(start, end+1)
                                  if valid_frame(self.folder/f'{i:06}.png', p.width, p.height))
        elapsed = time.monotonic()-started
        self.render_seconds += elapsed
        if not set(range(start, end+1)) <= self.frames():
            raise ValueError('Blender did not complete every requested frame')
        device_path = self.folder/'device.json'
        if device_path.exists():
            device = json.loads(device_path.read_text())
            if device.get('backend') != self.config['backend']:
                raise ValueError('Blender effective backend mismatch')
            self.report = device
        elif len(before) < len(self.frames()):
            raise ValueError('Blender did not confirm the effective device')
        added = len(self.frames()-before)
        return {'completed': len(self.frames()), 'total': self.total, 'batch_seconds': round(elapsed, 3),
                'seconds_per_frame': round(elapsed/added, 3) if added else None,
                'device': self.report, 'reused_frames': self.reused,
                'preparation_seconds': round(self.preparation_seconds, 3)}

    def save_checkpoint(self, persistent, numbers):
        numbers = sorted(set(numbers))
        if not numbers or len(numbers) > 120 or not set(numbers) <= self.frames():
            raise ValueError('Checkpoint requires a complete bounded frame batch')
        target = Path(persistent)/self.cache_id
        target.mkdir(parents=True, exist_ok=True)
        files = {f'{n:06}.png': self.folder/f'{n:06}.png' for n in numbers}
        frame_hashes = {name: sha(path) for name, path in files.items()}
        shard_id = identity(frame_hashes)
        existing_index = target/f'{shard_id}.json'
        existing_archive = target/f'{shard_id}.zip'
        if existing_index.is_file() and existing_index.stat().st_size <= 65536 and existing_archive.is_file():
            previous = json.loads(existing_index.read_text())
            if (previous.get('execution_hash') == self.cache_id and previous.get('frames') == frame_hashes
                    and previous.get('sha256') == sha(existing_archive)):
                # Do not replace a durable shard (ZIP timestamps can differ across restores).
                return
        local = self.folder/f'{shard_id}.zip'
        pack(local, files)
        pending = target/f'{shard_id}.partial'
        shutil.copyfile(local, pending)
        if sha(pending) != sha(local):
            raise ValueError('Checkpoint persistent copy failed integrity validation')
        pending.replace(target/f'{shard_id}.zip')
        # Immutable per-shard index is published only after verification of its complete copy.
        atomic_json(target/f'{shard_id}.json', {'execution_hash': self.cache_id, 'sha256': sha(local),
                    'frames': frame_hashes, 'execution': self.config, 'device': self.report})
        local.unlink()

    def restore(self, persistent):
        target = Path(persistent)/self.cache_id
        indices = sorted(target.glob('*.json'))
        if len(indices) > 18000:
            raise ValueError('Too many checkpoint indices')
        for index in indices:
            if index.stat().st_size > 65536:
                raise ValueError('Checkpoint index too large')
            data = json.loads(index.read_text())
            if data.get('execution_hash') != self.cache_id or data.get('execution') != self.config:
                raise ValueError('Incompatible checkpoint backend/version/profile')
            archive = index.with_suffix('.zip')
            if not archive.exists() or sha(archive) != data['sha256']:
                raise ValueError('Incomplete/corrupt checkpoint shard; index is not usable')
            with tempfile.TemporaryDirectory(dir=self.folder) as temp:
                names = unpack(archive, temp, allowed=set(data['frames']))
                if names != set(data['frames']):
                    raise ValueError('Incomplete checkpoint frame list')
                for name in names:
                    if not (len(name) == 10 and name[:6].isdigit() and name.endswith('.png')):
                        raise ValueError('Invalid checkpoint frame number')
                    n = int(name[:6])
                    frame = Path(temp)/name
                    if not 1 <= n <= self.total or sha(frame) != data['frames'][name] or not valid_frame(frame, self.package.profile.width, self.package.profile.height):
                        raise ValueError('Corrupt checkpoint frame')
                for name in names:
                    pending = self.folder/(name+'.partial')
                    shutil.copyfile(Path(temp)/name, pending)
                    pending.replace(self.folder/name)
            self.report = data.get('device')
        self.reused = len(self.frames(refresh=True))
        return self.reused

    def render(self, *, persistent=None, batch_size=24, cancel=lambda: False, progress=print):
        if not 1 <= batch_size <= 120:
            raise ValueError('Batch size outside 1–120')
        deadline = time.monotonic()+self.timeout
        configured_timeout = self.timeout
        for start in range(1, self.total+1, batch_size):
            if time.monotonic() >= deadline:
                raise TimeoutError('Interactive execution time limit reached; restore checkpoints in a later authorized session')
            end = min(self.total, start+batch_size-1)
            self.timeout = min(configured_timeout, max(.1, deadline-time.monotonic()))
            try:
                progress(self.batch(start, end, cancel=cancel))
            except (InterruptedError, TimeoutError, RuntimeError, KeyboardInterrupt):
                # A controlled interruption can still persist already finalized frames from this batch.
                if persistent:
                    complete = self.frames().intersection(range(start, end+1))
                    if complete:
                        self.save_checkpoint(persistent, complete)
                raise
            finally:
                self.timeout = configured_timeout
            if persistent:
                self.save_checkpoint(persistent, range(start, end+1))

    def finish(self, destination, *, cancel=lambda: False):
        if len(self.frames(refresh=True)) != self.total or not self.report:
            raise ValueError('Cannot compose: missing frames or verified Blender device')
        p = self.package.profile
        movie = self.folder/'video.mp4'
        temporary = self.folder/'video.partial.mp4'
        execute([self.ffmpeg, '-nostdin', '-v', 'error', '-y', '-framerate', p.fps, '-start_number', 1,
                 '-i', self.folder/'%06d.png', '-i', self.extracted/self.package.audio_path,
                 '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-threads', self.config['threads'],
                 '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-af', 'alimiter=limit=0.95',
                 '-t', self.package.board.duration, '-movflags', '+faststart', temporary], timeout=1800, cancel=cancel)
        temporary.replace(movie)
        execute([self.ffmpeg, '-v', 'error', '-xerror', '-i', movie, '-f', 'null', '-'], timeout=1800, cancel=cancel)
        shutil.copyfile(self.folder/'000001.png', self.folder/'thumbnail.png')
        atomic_json(self.folder/'report.json', {'execution': self.config, 'device': self.report,
                    'frames': self.total, 'reused_frames': self.reused, 'render_seconds': self.render_seconds,
                    'preparation_seconds': self.preparation_seconds,
                    'elapsed_seconds': time.monotonic()-self.started, 'origin': 'assisted-notebook'})
        files = {name: self.folder/name for name in ('video.mp4', 'thumbnail.png', 'report.json')}
        result = ResultPackage(export_id=self.package.export_id, project_id=self.package.project_id,
                               revision=self.package.revision, input_hash=identity(self.package.model_dump(mode='json')),
                               profile=p, effective_backend=self.config['backend'], execution_hash=self.cache_id,
                               files={n: {'sha256': sha(f), 'size': f.stat().st_size} for n, f in files.items()})
        atomic_json(self.folder/'result.json', result.model_dump(mode='json'))
        pack(destination, {**files, 'result.json': self.folder/'result.json'})
        return Path(destination)
