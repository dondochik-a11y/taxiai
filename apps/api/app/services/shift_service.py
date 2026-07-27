"""Work-shift boundaries: the /shift toggle's server-side decision (start vs
stop) plus the pure "how many online hours did these shifts cover on this day"
calc that feeds finance_service's honest ₽/hour.

The pure helpers (merge_intervals, shift_hours_for_day, elapsed_hours) take
plain datetimes and an injected `now`, so they're unit-tested without a DB or a
wall clock — mirroring app/services/alerts.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.shift import Shift


def _clip_interval(
    start: datetime, end: datetime, day_start: datetime, day_end: datetime
) -> tuple[datetime, datetime] | None:
    """Intersect [start, end) with the [day_start, day_end) window, or None if
    they don't overlap."""
    lo = max(start, day_start)
    hi = min(end, day_end)
    if hi <= lo:
        return None
    return lo, hi


def merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Union of possibly-overlapping [start, end) intervals, so a driver who
    briefly ran two overlapping shifts isn't double-counted."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: iv[0])
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def shift_hours_for_day(
    shifts: list[tuple[datetime, datetime | None]],
    day_start: datetime,
    day_end: datetime,
    now: datetime,
) -> float | None:
    """Online hours contributed by these shifts to the [day_start, day_end)
    window. An open shift (ended_at is None) is treated as running until `now`
    (clamped to the day). Returns None when no shift overlaps the day, so the
    caller can fall back to the trip-timestamp inference. Overlapping shifts are
    unioned, not summed."""
    clipped: list[tuple[datetime, datetime]] = []
    for start, end in shifts:
        effective_end = end if end is not None else now
        piece = _clip_interval(start, effective_end, day_start, day_end)
        if piece is not None:
            clipped.append(piece)
    if not clipped:
        return None
    total_seconds = sum((hi - lo).total_seconds() for lo, hi in merge_intervals(clipped))
    return max(total_seconds / 3600, 0.0)


def elapsed_hours(started_at: datetime, ended_at: datetime) -> float:
    """Whole-shift duration in hours, for the /shift stop confirmation."""
    return max((ended_at - started_at).total_seconds() / 3600, 0.0)


# --- DB helpers -------------------------------------------------------------


def get_open_shift(db: Session, user_id: uuid.UUID) -> Shift | None:
    """The driver's single currently-running shift, or None."""
    return db.execute(
        select(Shift)
        .where(Shift.user_id == user_id, Shift.ended_at.is_(None))
        .order_by(Shift.started_at.desc())
    ).scalars().first()


def get_shifts_overlapping_day(
    db: Session, user_id: uuid.UUID, day_start: datetime, day_end: datetime
) -> list[Shift]:
    """Every shift that touches the [day_start, day_end) window — an open shift
    counts (ended_at IS NULL)."""
    return list(
        db.execute(
            select(Shift).where(
                Shift.user_id == user_id,
                Shift.started_at < day_end,
                (Shift.ended_at.is_(None)) | (Shift.ended_at > day_start),
            )
        ).scalars()
    )


def toggle_shift(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> dict:
    """Start a shift if none is open, otherwise stop the open one. Returns a
    render-ready payload for the bot. The decision lives here (server-side), the
    bot only renders — matching the rest of the office's thin-bot design."""
    now = now or datetime.now(timezone.utc)
    open_shift = get_open_shift(db, user_id)

    if open_shift is None:
        shift = Shift(user_id=user_id, started_at=now)
        db.add(shift)
        db.commit()
        db.refresh(shift)
        return {
            "action": "started",
            "started_at": shift.started_at,
            "ended_at": None,
            "elapsed_hours": None,
        }

    open_shift.ended_at = now
    db.commit()
    db.refresh(open_shift)
    return {
        "action": "stopped",
        "started_at": open_shift.started_at,
        "ended_at": open_shift.ended_at,
        "elapsed_hours": round(elapsed_hours(open_shift.started_at, open_shift.ended_at), 2),
    }
