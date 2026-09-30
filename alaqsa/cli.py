"""Command-line actions used by the Omarchy bar widget and for setup.

    al-aqsa --check-current            check off the prayer that's on now (bar right-click)
    al-aqsa --check PRAYER YYYY-MM-DD  check / uncheck one prayer (bar panel rows)
    al-aqsa --notify on|off|toggle     prayer notifications
    al-aqsa --omarchy-bar install      add the prayer widget to the Omarchy bar
    al-aqsa --omarchy-bar remove       take it out again
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import barstatus, notifier, storage
from .place import Place
from .timetable import Timetable

PLUGIN_ID = "zephyrus.al-aqsa"
PLUGIN_SOURCE = Path(__file__).resolve().parent.parent / "omarchy" / PLUGIN_ID
PLUGIN_TARGET = Path.home() / ".config/omarchy/plugins" / PLUGIN_ID


def _toast(title: str, body: str = "") -> None:
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "--app-name=Al-Aqsa", "--icon=al-aqsa", "--expire-time=2500", title, body],
                       capture_output=True, timeout=10)


def _loaded():
    settings = storage.load_config()
    try:
        place = Place.from_dict(settings.get("place") or settings.get("mosque"))
    except (TypeError, AttributeError):
        _toast("Al-Aqsa", "Open the app to choose your mosque first")
        return 1
    cached = storage.load_timetable(place.key)
    if not cached:
        _toast("Al-Aqsa", "Open the app once to download the prayer times")
        return 1
    return Timetable.from_data(cached[0])


def check_current() -> int:
    tt = _loaded()
    if isinstance(tt, int):
        return tt
    now = datetime.now(timezone.utc)
    _, day, prayer = tt.last_prayer(now)
    return _toggle(tt, day, prayer, now)


def check(prayer: str, day_text: str) -> int:
    from datetime import date

    tt = _loaded()
    if isinstance(tt, int):
        return tt
    try:
        day = date.fromisoformat(day_text)
    except ValueError:
        print("Usage: al-aqsa --check PRAYER YYYY-MM-DD", file=sys.stderr)
        return 2
    return _toggle(tt, day, prayer.lower(), datetime.now(timezone.utc))


def _toggle(tt: Timetable, day, prayer: str, now: datetime) -> int:
    reason = tt.lock_reason(day, prayer, now)
    if reason:
        _toast("Can't change that", reason)
        return 1
    log = storage.PrayerLog.load()
    prayed = log.toggle(day, prayer)
    barstatus.write(now)
    name = prayer.capitalize()
    _toast(f"{name} checked ✓" if prayed else f"{name} unchecked", "")
    return 0


def omarchy_bar(action: str) -> int:
    if not barstatus.is_omarchy():
        print("The bar widget is for Omarchy only.", file=sys.stderr)
        return 1
    if action == "install":
        if PLUGIN_TARGET.exists():
            shutil.rmtree(PLUGIN_TARGET)
        shutil.copytree(PLUGIN_SOURCE, PLUGIN_TARGET)
        notifier.set_service(True)  # keeps the status file fresh
        barstatus.write()
        placed = subprocess.run(["omarchy", "bar", "put", PLUGIN_ID, "--after", "zephyrus.clock"], capture_output=True)
        if placed.returncode != 0:
            subprocess.run(["omarchy", "bar", "put", PLUGIN_ID], capture_output=True)
        storage.update_config({"omarchy_bar": True})
        print("Added the prayer widget to the Omarchy bar.")
        return 0
    if action == "remove":
        layout_remove(PLUGIN_ID)
        if PLUGIN_TARGET.exists():
            shutil.rmtree(PLUGIN_TARGET)
        storage.update_config({"omarchy_bar": False})
        print("Removed the prayer widget from the Omarchy bar.")
        return 0
    print("Usage: al-aqsa --omarchy-bar install|remove", file=sys.stderr)
    return 2


def layout_remove(widget_id: str) -> None:
    """Take a widget out of every bar section in ~/.config/omarchy/shell.json."""
    import json

    path = Path.home() / ".config/omarchy/shell.json"
    try:
        config = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    layout = config.get("bar", {}).get("layout", {})
    changed = False
    for section, widgets in layout.items():
        kept = [w for w in widgets if (w.get("id") if isinstance(w, dict) else w) != widget_id]
        if len(kept) != len(widgets):
            layout[section] = kept
            changed = True
    if changed:
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def main(args: list[str]) -> int | None:
    """Handle a command-line action; returns None when the app should start instead."""
    if args[:1] == ["--check-current"]:
        return check_current()
    if args[:1] == ["--check"] and len(args) == 3:
        return check(args[1], args[2])
    if args[:1] == ["--notify"]:
        value = args[1] if len(args) > 1 else "toggle"
        enable = (not storage.load_config().get("notify", True)) if value == "toggle" else value == "on"
        storage.update_config({"notify": enable})
        if enable:
            notifier.set_service(True)
        barstatus.write()
        print("Prayer notifications on" if enable else "Prayer notifications muted")
        return 0
    if args[:1] == ["--omarchy-bar"]:
        return omarchy_bar(args[1] if len(args) > 1 else "")
    if args[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    return None
