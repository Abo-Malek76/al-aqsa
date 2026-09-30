"""Prayer-time notifications: a desktop notification and a soft chime when each prayer starts.

Runs as a small systemd user service (al-aqsa-notify.service), so it works even when the
app is closed. It sleeps until the next prayer, re-reading the chosen mosque and its
cached timetable every time, so changes made in the app apply straight away.

    python -m alaqsa.notifier          run the notifier (what the service does)
    python -m alaqsa.notifier --test   show a sample notification and play the chime
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import barstatus, storage
from .place import Place
from .timetable import NAMES, PRAYERS, Timetable

SERVICE = "al-aqsa-notify.service"
UNIT_FILE = Path.home() / ".config/systemd/user" / SERVICE
CHIME = Path(__file__).resolve().parent / "assets/chime.wav"
LATE_LIMIT = timedelta(minutes=5)  # after a suspend, don't announce prayers that started long ago


def sound_file() -> Path:
    """The user's chosen notification sound (settings "notify_sound"), else the built-in chime."""
    chosen = storage.load_config().get("notify_sound")
    if chosen and Path(chosen).expanduser().is_file():
        return Path(chosen).expanduser()
    return CHIME


def play_chime() -> None:
    for player in (["pw-play"], ["paplay"]):
        if shutil.which(player[0]):
            subprocess.Popen([*player, str(sound_file())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return


def notify(title: str, body: str) -> None:
    if shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", "--app-name=Al-Aqsa", "--icon=al-aqsa", "--urgency=normal", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    play_chime()


def _load() -> tuple[Place, Timetable] | None:
    settings = storage.load_config()
    try:
        place = Place.from_dict(settings.get("place") or settings.get("mosque"))
    except (TypeError, AttributeError):
        return None
    cached = storage.load_timetable(place.key)
    if not cached:
        return None
    return place, Timetable.from_data(cached[0])


def announce(place: Place, tt: Timetable, day, prayer: str) -> None:
    schedule = tt.day(day)
    start = schedule.times[prayer].astimezone(tt.tz)
    name = "Jumu'ah" if prayer == "dhuhr" and schedule.jumua else NAMES[prayer]
    iqama = schedule.jumua if name == "Jumu'ah" else schedule.iqama.get(prayer)
    body = f"It's time for {name} · {start:%H:%M}\n{place.name}"
    if iqama:
        body += f" — iqama {iqama.astimezone(tt.tz):%H:%M}"
    notify(f"{name} has started", body)


class Watcher:
    """Decides when a prayer has just started and should be announced (once)."""

    def __init__(self) -> None:
        self.announced = None

    def check(self, tt: Timetable, now: datetime):
        """The (day, prayer) to announce now, or None."""
        started, day, prayer = tt.last_prayer(now)
        if self.announced is None:
            self.announced = (day, prayer)  # don't announce whatever was already going on at start
            return None
        if (day, prayer) == self.announced:
            return None
        self.announced = (day, prayer)
        return (day, prayer) if now - started <= LATE_LIMIT else None


def run() -> None:
    watcher = Watcher()
    omarchy = barstatus.is_omarchy()
    while True:
        loaded = _load()
        now = datetime.now(timezone.utc)
        if loaded is None:
            time.sleep(60)
            continue
        place, tt = loaded
        if omarchy:
            try:
                barstatus.write(now)
            except (OSError, ValueError, KeyError):
                pass  # the bar is a nice-to-have; never let it stop notifications
        due = watcher.check(tt, now)
        if due and storage.load_config().get("notify", True):
            announce(place, tt, *due)
        # Wake up at the next prayer, and at least every 30 s (suspend, settings changes)
        wait = (tt.next_prayer(now)[0] - now).total_seconds()
        time.sleep(max(0.5, min(30.0, wait + 0.2)))


# --- service management (used by the app's `n` key) ---------------------------------


def _systemctl(*args: str) -> bool:
    try:
        return subprocess.run(["systemctl", "--user", *args], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def install_service() -> None:
    UNIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    UNIT_FILE.write_text(
        "[Unit]\n"
        "Description=Al-Aqsa prayer notifications and Omarchy bar status\n"
        "After=graphical-session.target\n"
        "PartOf=graphical-session.target\n\n"
        "[Service]\n"
        f"ExecStart={sys.executable} -m alaqsa.notifier\n"
        "Restart=on-failure\n"
        "RestartSec=10\n\n"
        "[Install]\n"
        "WantedBy=graphical-session.target\n"
    )
    _systemctl("daemon-reload")


def service_enabled() -> bool:
    return _systemctl("is-enabled", "--quiet", SERVICE)


def set_service(enabled: bool) -> bool:
    if enabled:
        install_service()
        return _systemctl("enable", "--now", SERVICE)
    return _systemctl("disable", "--now", SERVICE)


def main() -> None:
    if "--test" in sys.argv:
        notify("Asr has started", "It's time for Asr · 15:37\nThis is how prayer notifications look")
        time.sleep(3)  # let the chime finish
        return
    try:
        run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
