"""Isolated browser-test audio fixture. Never generates real singing or calls AI."""
import sys

from factory.config import settings
from factory.db import Session
from factory.models import ProductionJob, VideoProject
from factory.queue import ACTIVE, Worker
from sqlalchemy import select
from test_render import sine


def main():
    mode, project_id = sys.argv[1:3]
    if mode == 'audio':
        path = settings.storage_root/'known-music-test-tone.wav'
        path.parent.mkdir(parents=True, exist_ok=True)
        sine(path, seconds=8)
        print(path)
    elif mode == 'mix':
        with Session() as db:
            jobs = list(db.scalars(select(ProductionJob).where(ProductionJob.state.in_(ACTIVE))))
            assert len(jobs) == 1 and jobs[0].project_id == project_id
            assert jobs[0].checkpoint.get('_music_operation', {}).get('kind') == 'mix'
        assert Worker().once()  # Only the explicitly queued local mix; no external inference.
        with Session() as db:
            assert db.get(VideoProject, project_id).narration.get('final')
        print('Validated local mix')
    else:
        raise ValueError('Unknown isolated fixture action')


if __name__ == '__main__':
    main()
