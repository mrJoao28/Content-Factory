import os
from pathlib import Path

os.environ["FACTORY_DISABLE_WORKER"] = "1"

import pytest
from fastapi.testclient import TestClient

from factory import db as database
from factory.config import settings
from factory.main import app
from factory.models import Base


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    # pytest's tmp_path is unique; user data is never dropped or overwritten.
    engine = database.make_engine("sqlite:///"+str(tmp_path / "test.db"))
    database.Session.configure(bind=engine)
    monkeypatch.setattr(database, "engine", engine)
    import factory.main
    monkeypatch.setattr(factory.main, "engine", engine)
    for attr, name in (("storage_root", "data"), ("output_dir", "output"), ("assets_dir", "assets")):
        directory = tmp_path/name
        directory.mkdir()
        monkeypatch.setattr(settings, attr, directory)
    Base.metadata.create_all(engine)
    database.seed()
    yield
    from sqlalchemy.orm import close_all_sessions
    close_all_sessions()
    engine.dispose()


@pytest.fixture
def client():
    with TestClient(app, headers={"X-Factory-Client": "local"}) as c:
        yield c


@pytest.fixture
def project(client):
    response = client.post("/projects", json={"idea": "A small robot discovers a garden", "channel_id": "wondernest"})
    assert response.status_code == 201, response.text
    return response.json()
