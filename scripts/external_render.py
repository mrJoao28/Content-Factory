"""Optional local CLI, using only the protected loopback API (no credentials)."""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from uuid import UUID


def main():
    parser = argparse.ArgumentParser(description='Export/import a prepared Content Factory project via its local API')
    parser.add_argument('action', choices=['export', 'import'])
    parser.add_argument('project_id', type=UUID)
    parser.add_argument('file', type=Path)
    parser.add_argument('--revision', type=int, default=1)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Invalid local port')
    base = f'http://127.0.0.1:{args.port}'
    path = f'/projects/{args.project_id}/external-render/{args.action}'
    if args.action == 'export':
        body = json.dumps({'expected_revision': args.revision}).encode()
    else:
        if args.file.stat().st_size > 256*1024**2:
            parser.error('ZIP exceeds 256 MiB')
        body = args.file.read_bytes()
    request = urllib.request.Request(base+path, data=body, headers={'X-Factory-Client': 'local',
        'Content-Type': 'application/json' if args.action == 'export' else 'application/zip'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            result = json.load(response)
        if args.action == 'export':
            urllib.request.urlretrieve(base+result['download_url'], args.file)
        print(json.dumps(result))
    except urllib.error.HTTPError as error:
        print(error.read(4096).decode(errors='replace'))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
