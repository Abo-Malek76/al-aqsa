"""Local storage: settings, cached mosque timetables and the prayer log.

Settings live in ~/.config/al-aqsa/, data in ~/.local/share/al-aqsa/
(respecting XDG_CONFIG_HOME / XDG_DATA_HOME). All writes are atomic.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from .timetable import PRAYERS

_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
CONFIG_DIR = _CONFIG_HOME / "al-aqsa"
DATA_DIR = _DATA_HOME / "al-aqsa"

CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = DATA_DIR / "prayed.json"
TIMETABLE_DIR = DATA_DIR / "timetables"


def migrate_legacy_dirs() -> None:
    """Move settings and the prayer log from before the app was renamed (salah -> al-aqsa)."""
    for old, new in ((_CONFIG_HOME / "salah", CONFIG_DIR), (_DATA_HOME / "salah", DATA_DIR)):
        if old.is_dir() and not new.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError):
        # Keep the unreadable file for inspection instead of silently overwriting it
        path.replace(path.with_suffix(path.suffix + ".corrupt"))
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_config() -> dict:
    return _read_json(CONFIG_FILE, {})


def save_config(config: dict) -> None:
    _write_json(CONFIG_FILE, config)


def update_config(changes: dict, remove: tuple[str, ...] = ()) -> dict:
    """Change some settings without touching the rest.

    Re-reads the file first, so settings written elsewhere since this process loaded
    them (another window, the notifier, a hand edit) are kept. Returns the new settings.
    """
    config = load_config()
    config.update(changes)
    for key in remove:
        config.pop(key, None)
    save_config(config)
    return config


def _timetable_file(key: str) -> Path:
    return TIMETABLE_DIR / f"{key.replace(':', '-')}.json"


def load_timetable(key: str) -> tuple[dict, datetime] | None:
    """Cached timetable for a place (see Place.key) and when it was fetched."""
    cached = _read_json(_timetable_file(key), None)
    if not cached:
        return None
    try:
        return cached["data"], datetime.fromisoformat(cached["fetched_at"])
    except (KeyError, ValueError):
        return None


def save_timetable(key: str, data: dict) -> None:
    _write_json(
        _timetable_file(key),
        {"fetched_at": datetime.now(timezone.utc).isoformat(), "data": data},
    )


class PrayerLog:
    """Which prayers were prayed on which day.

    A prayer checked after its day was over ("logged late") counts like any other,
    but is remembered separately so it stays visible as a late entry.
    """

    def __init__(self, days: dict[str, list[str]], path: Path = LOG_FILE, late: dict[str, list[str]] | None = None):
        self.path = path
        self._set(days, late or {})
        self._stamp = self._file_stamp()

    def _set(self, days: dict, late: dict) -> None:
        self._days = {day: set(prayers) & set(PRAYERS) for day, prayers in days.items()}
        self._late = {day: set(prayers) & self._days.get(day, set()) for day, prayers in late.items()}

    def _file_stamp(self):
        try:
            stat = self.path.stat()
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    @classmethod
    def load(cls, path: Path = LOG_FILE) -> PrayerLog:
        data = _read_json(path, {})
        return cls(data.get("days", {}), path, data.get("late", {}))

    def reload_if_changed(self) -> bool:
        """Pick up changes written by something else (e.g. the Omarchy bar). Returns True if it changed."""
        stamp = self._file_stamp()
        if stamp == self._stamp:
            return False
        data = _read_json(self.path, {})
        self._set(data.get("days", {}), data.get("late", {}))
        self._stamp = stamp
        return True

    def save(self) -> None:
        def ordered(entries: dict[str, set[str]]) -> dict[str, list[str]]:
            return {day: [p for p in PRAYERS if p in prayers] for day, prayers in sorted(entries.items()) if prayers}

        _write_json(self.path, {"version": 2, "days": ordered(self._days), "late": ordered(self._late)})
        self._stamp = self._file_stamp()

    def days(self) -> list[date]:
        """Days with at least one prayer checked, oldest first."""
        return sorted(date.fromisoformat(day) for day, prayers in self._days.items() if prayers)

    def prayed(self, day: date) -> set[str]:
        return set(self._days.get(day.isoformat(), ()))

    def is_prayed(self, day: date, prayer: str) -> bool:
        return prayer in self._days.get(day.isoformat(), ())

    def is_complete(self, day: date) -> bool:
        return self.prayed(day) >= set(PRAYERS)

    def is_late(self, day: date, prayer: str) -> bool:
        return prayer in self._late.get(day.isoformat(), ())

    def late_count(self, start: date, end: date) -> int:
        """Prayers logged late between two days (inclusive)."""
        return sum(
            len(prayers) for day, prayers in self._late.items() if start <= date.fromisoformat(day) <= end
        )

    def set_late(self, day: date, prayer: str, prayed: bool) -> None:
        """Log (or remove) a prayer after its day was over, and save."""
        self.reload_if_changed()
        key = day.isoformat()
        if prayed:
            self._days.setdefault(key, set()).add(prayer)
            self._late.setdefault(key, set()).add(prayer)
        else:
            self._days.get(key, set()).discard(prayer)
            self._late.get(key, set()).discard(prayer)
        self.save()

    def toggle(self, day: date, prayer: str) -> bool:
        """Flip a prayer and save. Returns the new state."""
        self.reload_if_changed()
        prayers = self._days.setdefault(day.isoformat(), set())
        self._late.get(day.isoformat(), set()).discard(prayer)
        if prayer in prayers:
            prayers.remove(prayer)
        else:
            prayers.add(prayer)
        self.save()
        return prayer in prayers
