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
            columns = {r[1] for r in db.execute(f'PRAGMA table_info("{table.name}")')}
            assert columns == set(table.columns.keys())
