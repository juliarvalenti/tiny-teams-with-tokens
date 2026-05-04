import logging
from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from ttt.config import settings

log = logging.getLogger("ttt.db")

_db_url = f"sqlite:///{settings.ttt_db_path}"
engine = create_engine(_db_url, connect_args={"check_same_thread": False})


def init_db() -> None:
    settings.ttt_db_path.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
