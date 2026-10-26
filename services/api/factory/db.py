from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from .config import settings
from .models import Channel, Series


def make_engine(url):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


engine = make_engine(settings.database_url)
Session = sessionmaker(engine, expire_on_commit=False)


def seed():
    with Session.begin() as db:
        if db.scalar(select(Channel.id).limit(1)):
            return
        db.add_all(
            [
                Channel(
                    id="wondernest",
                    name="WonderNest Kids",
                    platform="youtube",
                    made_for_kids=True,
                    goals={"shorts_per_day": 5, "episode_interval_days": 2},
                ),
                Channel(
                    id="how-it-works",
                    name="How It Actually Works",
                    platform="tiktok",
                    made_for_kids=False,
                    goals={"videos_per_day": 2},
                ),
            ]
        )
        db.flush()
        for name in (
            "Magic Forest Adventures",
            "Little Robot Friends",
            "Animal Wonderland",
            "Tiny Space Explorers",
            "Rainbow Learning",
        ):
            db.add(
                Series(
                    channel_id="wondernest",
                    name=name,
                    style={"medium": "2.5D layered animation", "palette": "vibrant", "original": True},
                )
            )
