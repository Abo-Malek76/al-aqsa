"""Progress numbers for the Progress panel."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .storage import PrayerLog
from .timetable import PRAYERS, Timetable

WINDOW_DAYS = 30


@dataclass(frozen=True)
class Stats:
    streak: int  # consecutive complete days up to today (or yesterday, while today is in progress)
    best_streak: int
    month_complete: int
    month_days: int  # days of the month so far
    per_prayer: dict[str, tuple[int, int]]  # prayer -> (prayed, possible) over the last WINDOW_DAYS
    window_days: int
    has_data: bool


def compute(log: PrayerLog, timetable: Timetable, now: datetime, month: date) -> Stats:
    today = timetable.today(now)

    day = today if log.is_complete(today) else today - timedelta(days=1)
    streak = 0
    while log.is_complete(day):
        streak += 1
        day -= timedelta(days=1)

    best = run = 0
    previous = None
    for day in log.days():
        if log.is_complete(day):
            run = run + 1 if previous and day - previous == timedelta(days=1) else 1
            previous = day
            best = max(best, run)
        else:
            previous = None

    last = calendar.monthrange(month.year, month.month)[1]
    month_end = min(date(month.year, month.month, last), today)
    month_days = max(0, (month_end - month).days + 1)
    month_complete = sum(log.is_complete(month + timedelta(days=i)) for i in range(month_days))

    logged = log.days()
    per_prayer = {p: (0, 0) for p in PRAYERS}
    window = 0
    if logged:
        start = max(logged[0], today - timedelta(days=WINDOW_DAYS - 1))
        window = (today - start).days + 1
        for i in range(window):
            day = start + timedelta(days=i)
            try:
                times = timetable.day(day).times
            except ValueError:
                continue
            for prayer in PRAYERS:
                if day < today or times[prayer] <= now:
                    prayed, possible = per_prayer[prayer]
                    per_prayer[prayer] = (prayed + log.is_prayed(day, prayer), possible + 1)

    return Stats(streak, best, month_complete, month_days, per_prayer, window, bool(logged))
