"""Prayer times for a day, the current/next prayer, and when a prayer may be checked off."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

PRAYERS = ("fajr", "dhuhr", "asr", "maghrib", "isha")
# How many days back a forgotten prayer can still be logged late
LATE_LOG_DAYS = 7
SUNRISE = "sunrise"
# Order of the six times in a Mawaqit calendar row
ROW_ORDER = ("fajr", SUNRISE, "dhuhr", "asr", "maghrib", "isha")

NAMES = {
    "fajr": "Fajr",
    SUNRISE: "Sunrise",
    "dhuhr": "Dhuhr",
    "asr": "Asr",
    "maghrib": "Maghrib",
    "isha": "Isha",
}


def _hm(value: str) -> tuple[int, int]:
    hours, minutes = value.strip().split(":")[:2]
    return int(hours), int(minutes)


def _at(day: date, value: str, tz: ZoneInfo) -> datetime:
    hours, minutes = _hm(value)
    return datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(hours=hours, minutes=minutes)


@dataclass(frozen=True)
class DaySchedule:
    day: date
    times: dict[str, datetime]  # fajr, sunrise, dhuhr, asr, maghrib, isha
    iqama: dict[str, datetime]  # prayers only, empty if the mosque doesn't publish iqama
    jumua: datetime | None  # Friday prayer, Fridays only


class Timetable:
    def __init__(
        self,
        calendar: list[dict],
        iqama_calendar: list[dict] | None,
        tz: str,
        jumua: str | None = None,
        hijri_adjustment: int = 0,
    ):
        self.calendar = calendar
        self.hijri_adjustment = hijri_adjustment
        self.iqama_calendar = iqama_calendar
        self.tz = ZoneInfo(tz)
        self.jumua = jumua
        self._cache: dict[date, DaySchedule] = {}

    @classmethod
    def from_data(cls, data: dict) -> Timetable:
        """From a timetable as returned by alaqsa.sources.fetch_timetable."""
        return cls(
            data["calendar"],
            data.get("iqama_calendar"),
            data.get("timezone") or "Europe/Stockholm",
            data.get("jumua"),
            int(data.get("hijri_adjustment") or 0),
        )

    def today(self, now: datetime) -> date:
        return now.astimezone(self.tz).date()

    def day(self, day: date) -> DaySchedule:
        if day not in self._cache:
            self._cache[day] = self._build(day)
        return self._cache[day]

    def _row(self, calendar: list[dict], day: date):
        month = calendar[day.month - 1]
        # Timetables without a 29 February reuse the 28th
        return month.get(str(day.day)) or month.get(str(day.day - 1))

    def _build(self, day: date) -> DaySchedule:
        row = self._row(self.calendar, day)
        if not row or len(row) < 6:
            raise ValueError(f"No prayer times for {day.isoformat()}")

        times = {name: _at(day, value, self.tz) for name, value in zip(ROW_ORDER, row)}
        # Late summer Isha can fall after midnight (e.g. "00:30")
        if times["isha"] < times["maghrib"]:
            times["isha"] += timedelta(days=1)

        iqama: dict[str, datetime] = {}
        iqama_row = self._row(self.iqama_calendar, day) if self.iqama_calendar else None
        if iqama_row:
            for prayer, value in zip(PRAYERS, iqama_row):
                value = str(value).strip()
                try:
                    if value.startswith("+") or value.isdigit():
                        iqama[prayer] = times[prayer] + timedelta(minutes=int(value.lstrip("+")))
                    elif ":" in value:
                        at = _at(day, value, self.tz)
                        iqama[prayer] = at + timedelta(days=1) if at < times[prayer] - timedelta(hours=12) else at
                except ValueError:
                    continue

        jumua = None
        if day.weekday() == 4 and self.jumua:
            try:
                jumua = _at(day, self.jumua, self.tz)
            except ValueError:
                pass
        return DaySchedule(day, times, iqama, jumua)

    def prayer_day(self, now: datetime) -> date:
        """The day whose prayers are in progress. Isha's time lasts until the next
        Fajr, so after midnight but before Fajr it is still the previous day."""
        today = self.today(now)
        return today - timedelta(days=1) if now < self.day(today).times["fajr"] else today

    def _events(self, now: datetime, names: tuple[str, ...]) -> list[tuple[datetime, date, str]]:
        pd = self.prayer_day(now)
        return sorted(
            (self.day(d).times[name], d, name)
            for d in (pd - timedelta(days=1), pd, pd + timedelta(days=1))
            for name in names
        )

    def current_period(self, now: datetime) -> tuple[datetime, date, str]:
        """The latest prayer or sunrise that has started (sunrise = no prayer time until Dhuhr)."""
        return [e for e in self._events(now, ROW_ORDER) if e[0] <= now][-1]

    def next_prayer(self, now: datetime) -> tuple[datetime, date, str]:
        """The next prayer to start. Sunrise is not a prayer, so it's skipped."""
        return next(e for e in self._events(now, PRAYERS) if e[0] > now)

    def lock_reason(self, day: date, prayer: str, now: datetime) -> str | None:
        """Why a prayer can't be checked/unchecked right now, or None if it can.

        - Sunrise is not a prayer.
        - A prayer can't be marked before its time starts.
        - Previous days are locked, except Isha, which stays open until the next
          Fajr (in Swedish summers Isha is often prayed after midnight).
        """
        if prayer not in PRAYERS:
            return "Sunrise is not a prayer"

        start = self.day(day).times[prayer]
        if now < start:
            when = "today" if self.today(start) == self.today(now) else start.strftime("%a %-d %b")
            return f"{NAMES[prayer]} hasn't started yet (starts {start:%H:%M} {when})"

        if prayer == "isha":
            closes = self.day(day + timedelta(days=1)).times["fajr"]
            if now >= closes:
                return f"That Isha closed at Fajr ({closes:%H:%M}), so it can't be changed"
            return None

        if day != self.today(now):
            return "Previous days can't be changed"
        return None

    def can_log_late(self, day: date, prayer: str, now: datetime) -> bool:
        """Whether a locked prayer from an earlier day may still be logged late:
        it's a real prayer, its day is over, and it was within the last LATE_LOG_DAYS days."""
        if prayer not in PRAYERS or self.lock_reason(day, prayer, now) is None:
            return False
        if now < self.day(day).times[prayer]:
            return False  # never for prayers that haven't happened
        return self.today(now) - day <= timedelta(days=LATE_LOG_DAYS)

    def last_prayer(self, now: datetime) -> tuple[datetime, date, str]:
        """The most recent prayer that has started (sunrise isn't a prayer)."""
        return [e for e in self._events(now, PRAYERS) if e[0] <= now][-1]
