"""Hijri (Islamic) dates from the Umm al-Qura calendar, with the source's day adjustment
(mosques on Mawaqit shift it to match local moon sighting)."""

from __future__ import annotations

from datetime import date, timedelta

from hijridate import Gregorian

MONTHS = (
    "Muharram", "Safar", "Rabiʿ al-Awwal", "Rabiʿ al-Thani", "Jumada al-Ula", "Jumada al-Akhirah",
    "Rajab", "Shaʿban", "Ramadan", "Shawwal", "Dhu al-Qaʿdah", "Dhu al-Hijjah",
)


def format_hijri(day: date, adjustment: int = 0) -> str:
    try:
        h = Gregorian.fromdate(day + timedelta(days=adjustment)).to_hijri()
    except (OverflowError, ValueError):
        return ""
    return f"{h.day} {MONTHS[h.month - 1]} {h.year}"
