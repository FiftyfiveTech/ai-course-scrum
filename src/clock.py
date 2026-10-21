"""
Clock abstraction — inject FakeClock in tests and demo, Clock in production.
No lifecycle code calls datetime.now() directly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol


class ClockProtocol(Protocol):
    def now(self) -> datetime: ...


class Clock:
    """Real wall-clock for production."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FakeClock:
    """Controllable clock for tests and demo."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: int) -> None:
        self._now += timedelta(**kwargs)

    def set(self, dt: datetime) -> None:
        self._now = dt
