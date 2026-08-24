"""
Database connection/session management. SQLite by default; designed so a future
swap to PostgreSQL only requires changing the connection string + minor dialect
tweaks (no business-logic changes), per the project's technology requirements.
"""
from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from mediavault.database.models import Base

DEFAULT_DB_PATH = os.path.join(os.path.expanduser("~"), ".mediavault", "mediavault.db")


class Database:
    def __init__(self, db_path: str | None = None, echo: bool = False):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=echo,
            connect_args={"check_same_thread": False},
        )
        self._enable_sqlite_pragmas()
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _enable_sqlite_pragmas(self) -> None:
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            # WAL mode: crucial for crash-safety + concurrent reads during long scans.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


_db_instance: Database | None = None


def get_database(db_path: str | None = None, echo: bool = False) -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path=db_path, echo=echo)
        _db_instance.create_all()
    return _db_instance