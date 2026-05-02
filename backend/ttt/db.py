import logging
from collections.abc import Iterator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from ttt.config import settings

log = logging.getLogger("ttt.db")

_db_url = f"sqlite:///{settings.ttt_db_path}"
engine = create_engine(_db_url, connect_args={"check_same_thread": False})


# Tiny lazy-migration registry — pairs of (table, column, ALTER fragment).
# SQLModel.metadata.create_all only creates missing tables; for additive column
# changes on existing dbs we run an idempotent ALTER. PoC-grade; replace with
# Alembic if/when the schema gets serious.
_LAZY_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("pagerevision", "deleted", "ALTER TABLE pagerevision ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT 0"),
]


def _apply_lazy_migrations() -> None:
    with engine.connect() as conn:
        for table, column, ddl in _LAZY_COLUMN_MIGRATIONS:
            cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]
            if column in cols:
                continue
            log.info("applying lazy migration: %s.%s", table, column)
            conn.execute(text(ddl))
            conn.commit()


def init_db() -> None:
    settings.ttt_db_path.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    _apply_lazy_migrations()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
