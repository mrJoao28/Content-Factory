def test_alembic_upgrade_and_downgrade(tmp_path, monkeypatch):
    import alembic  # noqa: F401
    from alembic import command
    from alembic.config import Config
    from factory.config import ROOT, settings
    from sqlalchemy import create_engine, inspect

    url = "sqlite:///" + str(tmp_path / "migration.db")
    monkeypatch.setattr(settings, "database_url", url)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "services/api/migrations"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    assert "video_projects" in inspect(engine).get_table_names()
    command.downgrade(config, "base")
    assert "video_projects" not in inspect(engine).get_table_names()
    engine.dispose()


def test_visual_migration_preserves_existing_project_data(tmp_path, monkeypatch):
    import json
    import sqlite3

    from alembic import command
    from alembic.config import Config
    from factory.config import ROOT, settings

    path = tmp_path/"legacy.db"
    monkeypatch.setattr(settings, "database_url", "sqlite:///"+str(path))
    config = Config(str(ROOT/"alembic.ini"))
    config.set_main_option("script_location", str(ROOT/"services/api/migrations"))
    command.upgrade(config, "0001")
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO video_projects
            (id,created_at,updated_at,channel_id,title,description,idea,idea_hash,language,platform,
             content_type,target_duration,aspect_ratio,width,height,fps,script,storyboard,assets,
             narration,metadata,status,revision,approved_hash)
            VALUES ('legacy','2026-01-01','2026-01-01','wondernest','Keep this','Original',
                    'Original idea','legacyhash','en-US','youtube','short',35,'9:16',720,1280,24,
                    '{"title":"Original script"}','{}','[]','{}','{}','FAILED',3,NULL)""")
    command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT title,script,revision,visual_config FROM video_projects WHERE id='legacy'").fetchone()
    assert row[:3] == ("Keep this", '{"title":"Original script"}', 3)
    assert json.loads(row[3]) == {"engine": "compositor_2d"}


def test_frozen_initial_schema_executes_on_real_sqlite(tmp_path):
    import ast
    import sqlite3

    from factory.config import ROOT
    from factory.models import Base

    source = ast.parse((ROOT / "services/api/migrations/versions/0001_initial.py").read_text())
    statements = next(
        ast.literal_eval(n.value)
        for n in source.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "SCHEMA_SQL" for t in n.targets)
    )
    with sqlite3.connect(tmp_path / "schema.db") as db:
        for statement in statements:
            db.execute(statement)
        for table in Base.metadata.tables.values():
            if table.name in {"external_render_exports", "music_versions"}:
                continue  # Added by 0003, verified by the upgrade/downgrade test.
            columns = {r[1] for r in db.execute(f'PRAGMA table_info("{table.name}")')}
            # The frozen initial migration predates visual_config; subsequent revisions add it.
            expected = set(table.columns.keys()) - ({"visual_config", "music_plan", "music_state"} if table.name == "video_projects" else set())
            assert columns == expected


def test_music_migration_after_offline_bootstrap(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from factory.config import ROOT, settings
    from factory.models import Base
    from sqlalchemy import create_engine
    url = 'sqlite:///'+str(tmp_path/'bootstrapped.db')
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setattr(settings, 'database_url', url)
    config = Config(str(ROOT/'alembic.ini'))
    config.set_main_option('script_location', str(ROOT/'services/api/migrations'))
    command.upgrade(config, 'head')
