import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from alaqsa.storage import PrayerLog
from alaqsa.timetable import PRAYERS, Timetable

TZ = ZoneInfo("Europe/Stockholm")
ROW = ["05:00", "06:45", "12:40", "15:30", "18:30", "20:00"]
LATE_ISHA_ROW = ["02:30", "03:40", "13:10", "17:40", "22:05", "00:30"]


def timetable(row=ROW):
    months = [{str(d): row for d in range(1, 32)} for _ in range(12)]
    iqama = [{str(d): ["+10", "+10", "+10", "+5", "21:00"] for d in range(1, 32)} for _ in range(12)]
    return Timetable(months, iqama, "Europe/Stockholm", jumua="13:00")


def at(day, hm):
    h, m = map(int, hm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)


DAY = date(2026, 9, 30)  # a Wednesday
PREV = DAY - timedelta(days=1)
NEXT = DAY + timedelta(days=1)


class LockRules(unittest.TestCase):
    def setUp(self):
        self.tt = timetable()

    def test_sunrise_is_never_checkable(self):
        self.assertIsNotNone(self.tt.lock_reason(DAY, "sunrise", at(DAY, "10:00")))

    def test_prayer_locked_before_it_starts(self):
        self.assertIsNotNone(self.tt.lock_reason(DAY, "asr", at(DAY, "15:29")))
        self.assertIsNone(self.tt.lock_reason(DAY, "asr", at(DAY, "15:30")))

    def test_future_day_locked(self):
        self.assertIsNotNone(self.tt.lock_reason(NEXT, "fajr", at(DAY, "23:00")))

    def test_earlier_prayers_of_today_stay_open(self):
        self.assertIsNone(self.tt.lock_reason(DAY, "fajr", at(DAY, "23:59")))

    def test_previous_day_locked(self):
        for prayer in ("fajr", "dhuhr", "asr", "maghrib"):
            self.assertIsNotNone(self.tt.lock_reason(PREV, prayer, at(DAY, "00:30")), prayer)

    def test_previous_isha_open_until_fajr(self):
        self.assertIsNone(self.tt.lock_reason(PREV, "isha", at(DAY, "00:30")))
        self.assertIsNone(self.tt.lock_reason(PREV, "isha", at(DAY, "04:59")))
        self.assertIsNotNone(self.tt.lock_reason(PREV, "isha", at(DAY, "05:00")))

    def test_isha_after_midnight(self):
        tt = timetable(LATE_ISHA_ROW)
        self.assertEqual(tt.day(DAY).times["isha"], at(NEXT, "00:30"))
        self.assertIsNotNone(tt.lock_reason(DAY, "isha", at(NEXT, "00:10")))
        self.assertIsNone(tt.lock_reason(DAY, "isha", at(NEXT, "00:40")))
        self.assertIsNotNone(tt.lock_reason(DAY, "isha", at(NEXT, "02:30")))


class Periods(unittest.TestCase):
    def setUp(self):
        self.tt = timetable()

    def test_prayer_day_rolls_over_at_fajr(self):
        self.assertEqual(self.tt.prayer_day(at(DAY, "04:59")), PREV)
        self.assertEqual(self.tt.prayer_day(at(DAY, "05:00")), DAY)

    def test_next_prayer_skips_sunrise(self):
        _, _, name = self.tt.next_prayer(at(DAY, "05:30"))
        self.assertEqual(name, "dhuhr")

    def test_current_period_after_sunrise(self):
        self.assertEqual(self.tt.current_period(at(DAY, "07:00"))[2], "sunrise")

    def test_next_after_isha_is_tomorrows_fajr(self):
        start, day, name = self.tt.next_prayer(at(DAY, "22:00"))
        self.assertEqual((day, name, start), (NEXT, "fajr", at(NEXT, "05:00")))

    def test_iqama_relative_and_absolute(self):
        schedule = self.tt.day(DAY)
        self.assertEqual(schedule.iqama["fajr"], at(DAY, "05:10"))
        self.assertEqual(schedule.iqama["isha"], at(DAY, "21:00"))

    def test_jumua_only_on_friday(self):
        self.assertIsNone(self.tt.day(DAY).jumua)
        friday = date(2026, 10, 2)
        self.assertEqual(self.tt.day(friday).jumua, at(friday, "13:00"))


class Log(unittest.TestCase):
    def test_toggle_persists_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prayed.json"
            log = PrayerLog.load(path)
            for prayer in PRAYERS:
                log.toggle(DAY, prayer)
            reloaded = PrayerLog.load(path)
            self.assertTrue(reloaded.is_complete(DAY))
            reloaded.toggle(DAY, "asr")
            self.assertFalse(PrayerLog.load(path).is_complete(DAY))


if __name__ == "__main__":
    unittest.main()


class StatsAndPlaces(unittest.TestCase):
    def test_streaks_and_month(self):
        from alaqsa.stats import compute

        with tempfile.TemporaryDirectory() as tmp:
            log = PrayerLog.load(Path(tmp) / "prayed.json")
            for d in (26, 27, 28, 29):  # 4-day run ending yesterday
                for prayer in PRAYERS:
                    log.toggle(date(2026, 9, d), prayer)
            for prayer in PRAYERS:  # an older 1-day run
                log.toggle(date(2026, 9, 20), prayer)
            log.toggle(DAY, "fajr")
            s = compute(log, timetable(), at(DAY, "13:00"), date(2026, 9, 1))
            self.assertEqual((s.streak, s.best_streak, s.month_complete, s.month_days), (4, 4, 5, 30))
            # Today only counts prayers that have started: fajr + dhuhr at 13:00
            self.assertEqual(s.per_prayer["fajr"], (6, 11))
            self.assertEqual(s.per_prayer["asr"], (5, 10))

    def test_old_config_is_a_mawaqit_mosque(self):
        from alaqsa.place import Place

        old = {"uuid": "u", "slug": "some-mosque", "name": "M", "address": "A", "latitude": 1.0, "longitude": 2.0}
        place = Place.from_dict(old)
        self.assertEqual((place.provider, place.key), ("mawaqit", "mawaqit:some-mosque"))


class LateLogging(unittest.TestCase):
    def setUp(self):
        self.tt = timetable()

    def test_past_prayers_within_a_week_can_be_logged_late(self):
        now = at(DAY, "10:00")
        self.assertTrue(self.tt.can_log_late(PREV, "fajr", now))
        self.assertTrue(self.tt.can_log_late(DAY - timedelta(days=7), "isha", now))
        self.assertFalse(self.tt.can_log_late(DAY - timedelta(days=8), "fajr", now))

    def test_not_for_sunrise_future_or_still_open_prayers(self):
        now = at(DAY, "10:00")
        self.assertFalse(self.tt.can_log_late(PREV, "sunrise", now))
        self.assertFalse(self.tt.can_log_late(DAY, "asr", now))  # hasn't started
        self.assertFalse(self.tt.can_log_late(DAY, "fajr", now))  # still normally checkable
        self.assertFalse(self.tt.can_log_late(PREV, "isha", at(DAY, "04:00")))  # Isha still open

    def test_late_entries_count_and_stay_marked(self):
        from alaqsa.stats import compute

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prayed.json"
            log = PrayerLog.load(path)
            for prayer in PRAYERS:
                log.toggle(PREV, prayer) if prayer != "asr" else log.set_late(PREV, "asr", True)
            log = PrayerLog.load(path)
            self.assertTrue(log.is_complete(PREV))
            self.assertTrue(log.is_late(PREV, "asr"))
            self.assertFalse(log.is_late(PREV, "fajr"))
            self.assertEqual(log.late_count(date(2026, 9, 1), DAY), 1)
            self.assertEqual(compute(log, self.tt, at(DAY, "10:00"), date(2026, 9, 1)).streak, 1)
            log.set_late(PREV, "asr", False)
            self.assertFalse(PrayerLog.load(path).is_complete(PREV))

    def test_old_log_files_still_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prayed.json"
            path.write_text('{"version": 1, "days": {"2026-09-29": ["fajr"]}}')
            log = PrayerLog.load(path)
            self.assertTrue(log.is_prayed(PREV, "fajr"))
            self.assertFalse(log.is_late(PREV, "fajr"))


class Notifications(unittest.TestCase):
    def test_each_prayer_is_announced_once_when_it_starts(self):
        from alaqsa.notifier import Watcher

        tt, w = timetable(), Watcher()
        self.assertIsNone(w.check(tt, at(DAY, "15:00")))  # startup: Dhuhr already going on
        self.assertIsNone(w.check(tt, at(DAY, "15:29")))
        self.assertEqual(w.check(tt, at(DAY, "15:30")), (DAY, "asr"))
        self.assertIsNone(w.check(tt, at(DAY, "15:31")))  # not twice
        self.assertEqual(w.check(tt, at(DAY, "18:31")), (DAY, "maghrib"))

    def test_sunrise_is_never_announced(self):
        from alaqsa.notifier import Watcher

        tt, w = timetable(), Watcher()
        w.check(tt, at(DAY, "06:00"))
        self.assertIsNone(w.check(tt, at(DAY, "06:46")))

    def test_no_stale_announcement_after_suspend(self):
        from alaqsa.notifier import Watcher

        tt, w = timetable(), Watcher()
        w.check(tt, at(DAY, "13:00"))
        self.assertIsNone(w.check(tt, at(DAY, "16:10")))  # woke up 40 min after Asr started


class Settings(unittest.TestCase):
    def test_update_keeps_settings_written_by_others(self):
        from unittest import mock

        from alaqsa import storage

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(storage, "CONFIG_FILE", Path(tmp) / "config.json"):
            storage.save_config({"clock_font": "classic"})
            stale = storage.load_config()  # e.g. the app's copy, loaded earlier
            storage.update_config({"notify_sound": "/x/pebble.wav"})  # set elsewhere meanwhile
            stale["clock_font"] = "led"
            storage.update_config({"clock_font": stale["clock_font"]})
            self.assertEqual(storage.load_config(), {"clock_font": "led", "notify_sound": "/x/pebble.wav"})


class OmarchyBar(unittest.TestCase):
    def test_status_lists_three_days_in_order_with_checkoffs(self):
        from alaqsa.barstatus import build
        from alaqsa.place import Place

        with tempfile.TemporaryDirectory() as tmp:
            log = PrayerLog.load(Path(tmp) / "prayed.json")
            log.toggle(DAY, "asr")
            status = build(Place("islamnu", "stockholm", "Stockholm"), timetable(), log, at(DAY, "16:00"), True)
        events = status["events"]
        self.assertEqual(len(events), 18)
        self.assertEqual([e["at"] for e in events], sorted(e["at"] for e in events))
        today = [e for e in events if e["today"]]
        self.assertEqual([e["key"] for e in today], ["fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"])
        self.assertEqual([e["name"] for e in today if e["prayed"]], ["Asr"])
        self.assertFalse(next(e for e in today if e["key"] == "sunrise")["prayer"])

    def test_log_changes_from_elsewhere_are_not_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prayed.json"
            app_log = PrayerLog.load(path)
            bar_log = PrayerLog.load(path)
            bar_log.toggle(DAY, "fajr")  # checked from the bar
            app_log.toggle(DAY, "dhuhr")  # then in the app, which loaded before
            self.assertEqual(PrayerLog.load(path).prayed(DAY), {"fajr", "dhuhr"})
