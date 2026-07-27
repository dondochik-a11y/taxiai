from datetime import datetime

from pydantic import BaseModel


class ShiftToggleOut(BaseModel):
    """Result of the /shift toggle. On start, only the boundary is set; on stop
    the elapsed time and today's income-so-far are filled in for the bot's
    confirmation message."""

    action: str  # "started" | "stopped"
    started_at: datetime
    ended_at: datetime | None = None
    elapsed_hours: float | None = None

    # Filled on stop (today's running totals), so the driver sees the payoff.
    net_income_today: float | None = None
    gross_income_today: float | None = None
    trips_count_today: int | None = None
