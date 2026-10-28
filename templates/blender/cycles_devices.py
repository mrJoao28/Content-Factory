"""Trusted device probe; enumerates Cycles without claiming rendering succeeded."""
import json
import sys
from pathlib import Path

import bpy

backend, destination = sys.argv[sys.argv.index('--')+1:]
if backend not in {'CPU', 'OPTIX', 'CUDA'}:
    raise ValueError('Unsupported Cycles backend')
devices = []
if backend != 'CPU':
    preferences = bpy.context.preferences.addons['cycles'].preferences
    preferences.compute_device_type = backend
    preferences.refresh_devices()
    devices = [{'name': d.name, 'type': d.type, 'id': d.id} for d in preferences.devices if d.type == backend]
    if not devices:
        raise RuntimeError('No supported device for the explicitly selected backend')
Path(destination).write_text(json.dumps({'backend': backend, 'devices': devices,
    'blender': bpy.app.version_string, 'build': bpy.app.build_hash.decode()}), encoding='utf-8')
