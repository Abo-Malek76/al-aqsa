"""Timetables from my-masjid.com, the prayer-screen service some mosques use to publish their times.

The mosque's share screen (https://time.my-masjid.com/timingscreen/<id>) reads its yearly
adhan and iqama times from a public endpoint.
"""

from __future__ import annotations

import json
import re
import urllib.parse

from .mawaqit import MawaqitError as SourceError
from .mawaqit import _get

API_URL = "https://time.my-masjid.com/api/TimingsInfoScreen/GetMasjidTimings"

_TIME = re.compile(r"^\d{1,2}:\d{2}$")
ADHAN_KEYS = ("fajr", "shouruq", "zuhr", "asr", "maghrib", "isha")
IQAMA_KEYS = ("iqamah_Fajr", "iqamah_Zuhr", "iqamah_Asr", "iqamah_Maghrib", "iqamah_Isha")


def fetch_timetable(guid: str) -> dict:
    """A mosque's yearly timetable, in the same shape as a Mawaqit timetable."""
    try:
        data = json.loads(_get(f"{API_URL}?{urllib.parse.urlencode({'GuidId': guid})}"))
        model = data.get("model", data)
        timings = model["salahTimings"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SourceError("my-masjid returned an unexpected response") from error

    calendar: list[dict] = [{} for _ in range(12)]
    iqama: list[dict] = [{} for _ in range(12)]
    for row in timings:
        try:
            month, day = int(row["month"]), int(row["day"])
            times = [str(row[key]).strip()[:5] for key in ADHAN_KEYS]
        except (KeyError, TypeError, ValueError):
            continue
        if not 1 <= month <= 12 or not all(_TIME.match(t) for t in times):
            continue
        calendar[month - 1][str(day)] = times
        iqamas = [str(row.get(key) or "").strip()[:5] for key in IQAMA_KEYS]
        if all(_TIME.match(t) for t in iqamas):
            iqama[month - 1][str(day)] = iqamas

    if not all(calendar):
        raise SourceError("This mosque hasn't published a full year on my-masjid")

    settings = model.get("masjidSettings") or {}
    details = model.get("masjidDetails") or {}
    jumua = str(settings.get("jumahTime") or "").strip()[:5]
    return {
        "name": details.get("name"),
        "timezone": "Europe/Stockholm",
        "calendar": calendar,
        "iqama_calendar": iqama if all(iqama) else None,
        "jumua": jumua if _TIME.match(jumua) and settings.get("showJumahTime") else None,
        "hijri_adjustment": int(settings.get("hijriOffset") or 0),
    }
