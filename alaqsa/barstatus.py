"""Status file for the Omarchy bar widget (Omarchy only).

The widget (omarchy/zephyrus.al-aqsa) reads $XDG_RUNTIME_DIR/al-aqsa/bar.json and
does its own per-second countdown from the timestamps in it, so this only needs
rewriting when something changes: a new prayer day, a prayer checked off, a new
mosque. The background service refreshes it; the app refreshes it right after
you check a prayer.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import storage
from .hijri import format_hijri
from .place import Place
from .timetable import NAMES, PRAYERS, SUNRISE, Timetable

STATUS_FILE = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "al-aqsa" / "bar.json"


def is_omarchy() -> bool:
    return bool(os.environ.get("OMARCHY_PATH")) or shutil.which("omarchy") is not None or Path("/usr/share/omarchy").is_dir()


def build(place: Place, tt: Timetable, log: storage.PrayerLog, now: datetime, notify: bool) -> dict:
    pd = tt.prayer_day(now)
    events = []
    for day in (pd - timedelta(days=1), pd, pd + timedelta(days=1)):
        schedule = tt.day(day)
        for key in ("fajr", SUNRISE, "dhuhr", "asr", "maghrib", "isha"):
            name = "Jumu'ah" if key == "dhuhr" and schedule.jumua else NAMES[key]
            iqama = schedule.jumua if name == "Jumu'ah" else schedule.iqama.get(key)
            events.append({
                "key": key,
                "name": name,
                "day": day.isoformat(),
                "at": int(schedule.times[key].timestamp() * 1000),
                "prayer": key in PRAYERS,
                "prayed": key in PRAYERS and log.is_prayed(day, key),
                "today": day == pd,
                "iqama": int(iqama.timestamp() * 1000) if iqama else None,
                # Why it can't be checked right now ("" = it can); re-written when a prayer starts
                "locked": (tt.lock_reason(day, key, now) or "") if key in PRAYERS else "Sunrise is not a prayer",
            })
    local = now.astimezone(tt.tz)
    return {
        "place": place.name,
        "source": place.source,
        "date": f"{local:%A} {local.day} {local:%B}",
        "hijri": format_hijri(local.date(), tt.hijri_adjustment),
        "prayerDay": pd.isoformat(),
        "notify": notify,
        "prayedToday": len(log.prayed(pd)),
        "events": events,
    }


def write(now: datetime | None = None) -> bool:
    """Refresh the status file if anything changed. Returns whether it was written."""
    settings = storage.load_config()
    try:
        place = Place.from_dict(settings.get("place") or settings.get("mosque"))
    except (TypeError, AttributeError):
        return False
    cached = storage.load_timetable(place.key)
    if not cached:
        return False
    tt = Timetable.from_data(cached[0])
    status = build(place, tt, storage.PrayerLog.load(), now or datetime.now(timezone.utc), settings.get("notify", True))
    text = json.dumps(status, ensure_ascii=False, indent=1)
    try:
        if STATUS_FILE.read_text() == text:
            return False
    except OSError:
        pass
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STATUS_FILE.parent, prefix=".bar.")
    with os.fdopen(fd, "w") as file:
        file.write(text)
    os.replace(tmp, STATUS_FILE)
    return True
