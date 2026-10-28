"""Bounded ZIP transport. Digests establish integrity, never authorship."""
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

MAX_ZIP = 256 * 1024**2
MAX_EXPANDED = 512 * 1024**2
MAX_FILES = 256


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            digest.update(chunk)
    return digest.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.partial')
    temporary.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def unpack(source, destination, *, allowed=None):
    """Validate the entire directory before extracting; only regular files, ASCII names."""
    source, destination = Path(source), Path(destination)
    if source.stat().st_size > MAX_ZIP:
        raise ValueError('ZIP exceeds the 256 MiB transport limit')
    try:
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if not 1 <= len(entries) <= MAX_FILES:
                raise ValueError('ZIP file count outside limits')
            total, names = 0, set()
            for entry in entries:
                name = entry.filename
                parts = name.split('/')
                mode = entry.external_attr >> 16
                if (not re.fullmatch(r'[A-Za-z0-9_./-]+', name) or any(p in {'', '.', '..'} for p in parts)
                        or name.casefold() in names or (mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG})
                        or entry.flag_bits & 1 or (allowed is not None and name not in allowed)):
                    raise ValueError('ZIP contains an unsafe, ambiguous or unexpected entry')
                names.add(name.casefold())
                total += entry.file_size
                if total > MAX_EXPANDED or entry.file_size > MAX_EXPANDED or entry.file_size > max(1, entry.compress_size)*250:
                    raise ValueError('ZIP expansion limit exceeded')
            destination.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                target = destination / entry.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(entry) as stream, target.open('xb') as output:
                    while chunk := stream.read(1024**2):
                        written += len(chunk)
                        if written > entry.file_size:
                            raise ValueError('ZIP expanded beyond declared size')
                        output.write(chunk)
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise ValueError('Invalid ZIP transport') from exc
    return {e.filename for e in entries}


def pack(destination, files):
    temporary = Path(destination).with_suffix('.partial')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, source in files.items():
            archive.write(source, name)
    if temporary.stat().st_size > MAX_ZIP:
        temporary.unlink()
        raise ValueError('Package exceeds transport size limit')
    temporary.replace(destination)
