"""
Shared datetime helpers. SQLite (via SQLAlchemy) returns naive datetimes even
for columns declared as DateTime(timezone=True), so any comparison against a
timezone-aware "now" must normalize both sides first to avoid
"can't compare offset-naive and offset-aware datetimes".
"""
from __future__ import annotations
from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value