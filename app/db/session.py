from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base


class Database:
    def __init__(self, database_url: str) -> None:
        connect_args: dict[str, object] = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        self.engine: Engine = create_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(bind=self.engine)

    def dispose(self) -> None:
        self.engine.dispose()


async def get_db(request: Request) -> AsyncGenerator[Session, None]:
    session = request.app.state.database.session_factory()
    try:
        yield session
    finally:
        session.close()
