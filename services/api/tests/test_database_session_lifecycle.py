"""Regression tests for request-scoped DB session lifecycle."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from app import database

if TYPE_CHECKING:
    from types import TracebackType


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0
        self._in_transaction = True

    def in_transaction(self) -> bool:
        return self._in_transaction

    async def commit(self) -> None:
        self.commits += 1
        self._in_transaction = False

    async def rollback(self) -> None:
        self.rollbacks += 1
        self._in_transaction = False

    async def close(self) -> None:
        self.closes += 1


class _SessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


@pytest.mark.asyncio
async def test_get_db_session_rolls_back_and_closes_on_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client disconnect/cancelled request still rolls back and closes session."""
    fake = _FakeSession()
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _SessionFactory(fake))

    with pytest.raises(asyncio.CancelledError):
        async with database.get_db_session():
            raise asyncio.CancelledError()

    assert fake.commits == 0
    assert fake.rollbacks == 1
    assert fake.closes == 1


@pytest.mark.asyncio
async def test_get_db_session_commits_and_closes_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful request commits once and closes the session."""
    fake = _FakeSession()
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _SessionFactory(fake))

    async with database.get_db_session() as session:
        assert isinstance(session, _FakeSession)

    assert fake.commits == 1
    assert fake.rollbacks == 0
    assert fake.closes == 1
