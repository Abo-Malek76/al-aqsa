"""Al-Aqsa — prayer times, countdown and prayer tracker for the terminal."""

from __future__ import annotations

import calendar as cal
import math
import os
import random
import re
import time
from datetime import date, datetime, timedelta, timezone

from rich.segment import Segment
from rich.style import Style as RichStyle
from rich.table import Table
from rich.text import Span, Text
from textual.strip import Strip
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Center, Container, Vertical
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widget import Widget
from textual.widgets import Button, DataTable, Footer, Input, OptionList, ProgressBar, Static
from textual.widgets.option_list import Option

from . import barstatus, notifier, sources, stats, storage, themes
from .clock import ANIMATIONS, FONTS, BigClock
from .scenes import SCENES, Canvas, Sky
from .visualizer import MusicSource, PeakHold, PulseSource, gradient, render_bars
from .hijri import format_hijri
from .place import STOCKHOLM, Place
from .sources import SourceError
from .timetable import LATE_LOG_DAYS, NAMES, PRAYERS, SUNRISE, Timetable
from .visibility import VisibilityWatcher

# Nerd Font glyphs (Omarchy ships JetBrainsMono Nerd Font)
CHECKED = "󰄲"
UNCHECKED = "󰄱"
LOCK = "󰌾"
SUN = "󰖜"
PILL_LEFT = ""
PILL_RIGHT = ""

NARROW = 110  # below this many columns the panels stack in one scrolling column
FPS = 15  # clock animation frame rate
GRADIENT_STEPS = 13  # colours across the visualizer width

# Clock animation modes, in the order `v` cycles through them
VISUALS = {
    "pulse": "Pulse — beats with every second, stronger as the prayer gets close",
    "music": "Music — reacts to whatever is playing on your computer",
    **{key: label for key, (label, _, _) in SCENES.items()},
    "off": "Off",
}
VISUALS["sky"] = "Sky — the sun's real position between sunrise and Maghrib, the moon at night"
CELL = 6  # calendar cell width


def now() -> datetime:
    return datetime.now(timezone.utc)


def themed(text: Text, theme: Theme) -> Text:
    """Resolve Textual theme variables ($accent, $success, ...) in Rich text styles."""

    def resolve(style):
        if not isinstance(style, str) or "$" not in style:
            return style
        return re.sub(r"\$([a-z-]+)", lambda m: getattr(theme, m.group(1).replace("-", "_"), None) or "default", style)

    return Text(
        text.plain,
        style=resolve(text.style),
        spans=[Span(span.start, span.end, resolve(span.style)) for span in text.spans],
        justify=text.justify,
        no_wrap=text.no_wrap,
        end=text.end,
    )


class ThemedStatic(Static):
    """A Static whose Rich text may use theme variables like $accent."""

    def update(self, content="", **kwargs) -> None:
        if isinstance(content, Text):
            content = themed(content, self.app.current_theme)
        super().update(content, **kwargs)


class VizStrip(Widget):
    """A fixed-height strip of visualizer bars, drawn line by line from pre-coloured
    runs. It repaints without re-laying-out the screen, which keeps the animation cheap."""

    def __init__(self, rows: int, dim: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rows = rows
        self.dim = dim
        self.styles.height = rows
        self._lines: list[list[tuple[str, int]]] = []
        self._palette: list = []
        self._styles: list[RichStyle] = []
        self._styles_key = None

    def show(self, lines: list[list[tuple[str, int]]], palette: list, dim: bool | None = None) -> None:
        self._lines = lines
        if dim is not None and dim != self.dim:
            self.dim = dim
            self._styles_key = None
        if self._palette is not palette:
            self._palette = palette
            self._styles_key = None
        self.refresh()

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        if y >= len(self._lines):
            return Strip.blank(width, self.rich_style)
        base = self.rich_style  # carries the panel background
        if self._styles_key != (id(self._palette), base):
            self._styles = [base + RichStyle(color=color, dim=self.dim) for color in self._palette]
            self._styles_key = (id(self._palette), base)
        return Strip([Segment(text, self._styles[index]) for text, index in self._lines[y]]).adjust_cell_length(width, base)


def duration(delta: timedelta) -> str:
    minutes = max(0, int(delta.total_seconds() // 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def day_label(day: date, today: date) -> str:
    relative = {0: "Today", -1: "Yesterday", 1: "Tomorrow"}.get((day - today).days)
    short = f"{day:%a} {day.day} {day:%b}"
    return f"{relative} · {short}" if relative else f"{day:%A} {day.day} {day:%B %Y}"


def calendar_text(month: date, today: date, selected: date, log: storage.PrayerLog, theme: Theme) -> tuple[Text, int, int]:
    """The month grid, and how many days are complete / partial."""
    green = theme.success or "green"
    yellow = theme.warning or "yellow"
    accent = theme.accent or theme.primary
    bg = theme.background or "black"

    grid = Text(no_wrap=True)
    grid.append("".join(f"{name:^{CELL}}" for name in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")), style="dim")
    grid.append("\n")

    complete = partial = 0
    weeks = cal.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month)
    weeks += [[]] * (6 - len(weeks))  # always six rows so the panel doesn't jump
    for week in weeks:
        grid.append("\n")
        for day in week or [None] * 7:
            if day is None or day.month != month.month:
                grid.append(" " * CELL)
                continue
            count = len(log.prayed(day))
            mark = " underline" if day == selected and day != today else ""
            if count == 5:
                complete += 1
                # Rounded chip; the digits stay in the same columns as unmarked days
                grid.append(" " if day.day >= 10 else "  ")
                grid.append(PILL_LEFT, style=green)
                grid.append(str(day.day), style=f"bold {bg} on {green}{mark}")
                grid.append(PILL_RIGHT, style=green)
                grid.append(" ")
                continue
            partial += bool(count)
            if day == today:
                style = f"bold {accent} underline"
            elif day > today:
                style = f"dim{mark}"
            elif count:
                style = f"{yellow}{mark}"
            else:
                style = mark.strip()
            grid.append("  ")
            grid.append(f"{day.day:>2}", style=style)
            grid.append("  ")
        grid.append("\n")
    grid.rstrip()
    return grid, complete, partial


def bar(fraction: float, width: int, color: str) -> Text:
    filled = round(max(0.0, min(1.0, fraction)) * width)
    return Text.assemble(("━" * filled, color), ("━" * (width - filled), "dim"))


# --- main screen -------------------------------------------------------------


class MainScreen(Screen):
    BINDINGS = [
        Binding("space", "toggle", "Check", priority=True),
        Binding("left,h", "shift_day(-1)", "Day"),
        Binding("right,l", "shift_day(1)", "Day", show=False),
        Binding("left_square_bracket", "shift_month(-1)", "Month"),
        Binding("right_square_bracket", "shift_month(1)", "Month", show=False),
        Binding("t", "go_today", "Today"),
        Binding("m", "choose_place", "Mosque"),
        Binding("T", "choose_theme", "Theme", show=False),
        Binding("ctrl+c", "choose_theme", "Pick theme", show=False, priority=True),
        Binding("c", "app.cycle_theme(1)", "Theme", key_display="c/s/^c"),
        Binding("C", "app.cycle_theme(-1)", "Previous theme", show=False),
        Binding("s", "app.random_theme", "Random theme", show=False),
        Binding("v", "cycle_visual(1)", "Visual", key_display="v/V"),
        Binding("V", "cycle_visual(-1)", "Previous visual", show=False),
        Binding("f", "cycle_clock_font", "Clock", key_display="f/a/x"),
        Binding("a", "cycle_clock_animation", "Digit animation", show=False),
        Binding("x", "toggle_seconds", "Seconds", show=False),
        Binding("n", "app.toggle_notifications", "Notify"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "app.quit", "Quit"),
        # Scrolling (only when the panels are stacked in a narrow window)
        Binding("j", "scroll('down')", "Scroll", key_display="j/k"),
        Binding("k", "scroll('up')", "Scroll up", show=False),
        Binding("pagedown", "scroll('page_down')", "Page down", show=False, priority=True),
        Binding("pageup", "scroll('page_up')", "Page up", show=False, priority=True),
        Binding("g", "scroll('home')", "Top", show=False),
        Binding("G", "scroll('end')", "Bottom", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.view_day: date | None = None
        self.following = True  # the view follows the current prayer day
        self._table_signature = None
        self._side_signature = None
        self.pulse = PulseSource()
        self.music = MusicSource()
        self.peaks = PeakHold()
        self._gradient_key = None
        self._gradient: list = []
        self._flash = None
        self.sky = Sky()
        self.active = True  # False while the window can't be seen (see set_active)

    def compose(self) -> ComposeResult:
        yield ThemedStatic(id="header")
        with Container(id="body"):
            with Vertical(id="left"):
                with Vertical(id="next", classes="panel"):
                    yield ThemedStatic(id="next-label")
                    yield VizStrip(3, id="viz-top", classes="viz")
                    yield BigClock(
                        self.app.settings.get("clock_font", "classic"),
                        self.app.settings.get("clock_animation", "roll"),
                        id="countdown",
                    )
                    yield VizStrip(2, dim=True, id="viz-bottom", classes="viz")
                    yield ProgressBar(total=1.0, show_eta=False, show_percentage=False, id="progress")
                    yield ThemedStatic(id="hint")
                with Vertical(id="today", classes="panel"):
                    yield DataTable(id="prayers", cursor_type="row")
                    yield ThemedStatic(id="day-note")
                with Vertical(id="week", classes="panel"):
                    yield ThemedStatic(id="week-table")
            with Vertical(id="right"):
                with Vertical(id="month", classes="panel"):
                    with Center():
                        yield ThemedStatic(id="calendar")
                    yield ThemedStatic(id="legend")
                with Vertical(id="stats", classes="panel"):
                    yield ThemedStatic(id="stats-text")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#next").border_title = "Next prayer"
        self.query_one("#stats").border_title = "Progress"
        table = self.query_one(DataTable)
        table.add_column("", key="check", width=2)
        table.add_column("Prayer", key="name", width=9)
        table.add_column("Adhan", key="adhan", width=5)
        table.add_column("Iqama", key="iqama", width=5)
        table.add_column("", key="status", width=13)
        self._tick_timer = self.set_interval(1, self.tick)
        self._digits_timer = self.set_interval(0.1, self.update_clock_digits)
        self._animation = self.set_interval(1 / FPS, self.animate, pause=True)
        self.set_visual(self.app.settings.get("visual", "pulse"), announce=False, save=False)
        self.tick()
        if not self.active:  # started hidden
            self._tick_timer.pause()
            self._digits_timer.pause()

    def on_unmount(self) -> None:
        self.music.stop()

    # --- clock animation ---

    def set_visual(self, mode: str, announce: bool = True, save: bool = True) -> None:
        if mode not in VISUALS:
            mode = "pulse"
        if mode == "music" and self.active and not self.music.start():
            self.notify(f"Music mode needs audio access: {self.music.error}", severity="warning", timeout=4)
            mode = "pulse"
        if mode != "music":
            self.music.stop()
        self.visual = mode
        for viz in self.query(".viz"):
            viz.display = mode != "off"
        if mode == "off" or not self.active:
            self._animation.pause()
            self.query_one(BigClock).set_color(None)
            self._flash = None
        else:
            self._animation.resume()
        if save:
            self.app.save_settings(visual=mode)
        if announce:
            self.app.clear_notifications()
            self.notify(f"Clock animation: {VISUALS[mode]}", timeout=2.5)

    def set_active(self, active: bool) -> None:
        """Pause everything that only matters on screen while the window is hidden
        (another workspace, behind a fullscreen game); resume when it's back."""
        if active == self.active:
            return
        self.active = active
        if debug_log := os.environ.get("AL_AQSA_DEBUG_LOG"):
            with open(debug_log, "a") as file:
                file.write(f"{time.time():.1f} {'visible' if active else 'hidden'}\n")
        if not hasattr(self, "_tick_timer"):  # not mounted yet: on_mount applies it
            return
        for timer in (self._tick_timer, self._digits_timer):
            timer.resume() if active else timer.pause()
        if active:
            self.set_visual(self.visual, announce=False, save=False)  # restarts animation / music listening
            self.reload()
            self.update_clock_digits()
        else:
            self._animation.pause()
            self.music.stop()

    def action_cycle_visual(self, step: int = 1) -> None:
        modes = list(VISUALS)
        self.set_visual(modes[(modes.index(self.visual) + step) % len(modes)])

    def _scene_palette(self, roles: tuple[str, ...]) -> list:
        theme = self.app.current_theme
        key = (roles, theme.name)
        if key != getattr(self, "_scene_palette_key", None):
            background = Color.parse(theme.background or "#000000")
            foreground = Color.parse(theme.foreground or "#ffffff")
            colors = []
            for role in roles:
                if role == "text-muted":
                    colors.append(background.blend(foreground, 0.45))
                else:
                    colors.append(Color.parse(getattr(theme, role, None) or theme.primary))
            self._scene_palette_cache = [c.rich_color for c in colors]
            self._scene_palette_key = key
        return self._scene_palette_cache

    def animate(self) -> None:
        if self.visual in SCENES:
            top = self.query_one("#viz-top", VizStrip)
            width = top.size.width
            if width <= 0:
                return
            _, draw, roles = SCENES[self.visual]
            canvas = Canvas(width, 3, 2)
            draw(canvas, time.time(), self.sky)
            palette = self._scene_palette(roles)
            top.show(canvas.lines(0, 3), palette)
            self.query_one("#viz-bottom", VizStrip).show(canvas.lines(3, 5), palette, dim=False)
            if self._flash is not None:
                self._flash = None
                self.query_one(BigClock).set_color(None)
            return
        if self.visual == "music" and not self.music.silent:
            bands, beat = self.music.read()
        else:
            # Pulse mode, or nothing playing yet in music mode
            bands, beat = self.pulse.read(time.time())

        top = self.query_one("#viz-top", VizStrip)
        width = top.size.width
        if width <= 0:
            return
        theme = self.app.current_theme
        key = (width, theme.name)
        if key != self._gradient_key:
            # A few gradient steps across the width: looks smooth, keeps the runs long
            colors = [theme.primary, theme.accent or theme.primary, theme.secondary or theme.primary]
            self._gradient = gradient([colors[0], colors[1], colors[2], colors[1], colors[0]], GRADIENT_STEPS)
            self._columns = [round(col / max(1, width - 1) * (GRADIENT_STEPS - 1)) for col in range(width)]
            self._gradient_key = key
        peaks = self.peaks.update(bands)
        top.show(render_bars(bands, 3, self._columns, peaks=peaks), self._gradient)
        self.query_one("#viz-bottom", VizStrip).show(render_bars(bands, 2, self._columns, mirror=True), self._gradient, dim=True)

        # The digits flash towards the foreground colour on every beat (only repaint
        # when the quantised brightness actually changes)
        level = round(min(1.0, beat) * 6)
        if (level, theme.name) != self._flash:
            self._flash = (level, theme.name)
            accent = Color.parse(theme.accent or theme.primary)
            bright = Color.parse(theme.foreground or "#ffffff")
            self.query_one(BigClock).set_color(accent.blend(bright, level / 6 * 0.75).rich_color)

    # --- clock font and digit animation ---

    def action_cycle_clock_font(self) -> None:
        clock = self.query_one(BigClock)
        keys = list(FONTS)
        clock.set_font(keys[(keys.index(clock.font_key) + 1) % len(keys)])
        self.app.save_settings(clock_font=clock.font_key)
        self.app.clear_notifications()
        self.notify(f"Clock font: {clock.font.name}", timeout=1.5)

    def action_cycle_clock_animation(self) -> None:
        clock = self.query_one(BigClock)
        keys = list(ANIMATIONS)
        clock.set_animation(keys[(keys.index(clock.animation_key) + 1) % len(keys)])
        self.app.save_settings(clock_animation=clock.animation_key)
        self.app.clear_notifications()
        self.notify(f"Digit animation: {ANIMATIONS[clock.animation_key][0]}", timeout=1.5)

    def update_clock_digits(self) -> None:
        """Runs 10×/s so digits change right on the second (the main tick is only 1×/s)."""
        tt = self.timetable
        if tt is None:
            return
        t = now()
        target, _, _ = tt.next_prayer(t)
        left = max(0.0, (target - t).total_seconds())
        if self.app.settings.get("clock_seconds", True):
            h, rem = divmod(int(left), 3600)
            value = f"{h:02d}:{rem // 60:02d}:{rem % 60:02d}"
        else:
            # Round the minutes up, so it only shows 00:00 when the prayer starts
            h, m = divmod(math.ceil(left / 60), 60)
            value = f"{h:02d}:{m:02d}"
        self.query_one(BigClock).set_value(value)

    def action_toggle_seconds(self) -> None:
        show = not self.app.settings.get("clock_seconds", True)
        self.app.save_settings(clock_seconds=show)
        self.update_clock_digits()
        self.app.clear_notifications()
        self.notify("Clock: hours, minutes and seconds" if show else "Clock: hours and minutes", timeout=1.5)

    def on_resize(self) -> None:
        self.set_class(self.size.width < NARROW, "narrow")
        self.refresh_bindings()  # show or hide the scroll keys
        self._side_signature = None
        self.tick()

    @property
    def timetable(self) -> Timetable | None:
        return self.app.timetable

    def reload(self) -> None:
        """Redraw everything (new place, timetable, theme or log change)."""
        self._table_signature = None
        self._side_signature = None
        if self.is_mounted:  # otherwise on_mount draws it
            self.tick()

    def tick(self) -> None:
        if self.app.prayer_log.reload_if_changed():  # e.g. checked off from the Omarchy bar
            self._table_signature = None
            self._side_signature = None
        tt = self.timetable
        t = now()
        self.update_header(tt, t)
        if tt is None:
            return
        if self.following or self.view_day is None:
            self.view_day = tt.prayer_day(t)
        self.update_countdown(tt, t)
        self.update_table(tt, t)
        self.update_side(tt, t)

    # --- panels ---

    def update_header(self, tt: Timetable | None, t: datetime) -> None:
        place: Place | None = self.app.place
        local = t.astimezone(tt.tz if tt else None)
        theme = self.app.current_theme
        badge = themed(Text.assemble((" AL-AQSA ", "bold $background on $primary")), theme)
        center = Text.assemble((place.name, "bold"), (f"  {place.source}", "dim")) if place else Text("No mosque selected", style="dim")
        bell = Text("󰂚 " if self.app.notifications_on else "󰂛 ", style="$success" if self.app.notifications_on else "dim")
        clock = Text.assemble(themed(bell, theme), (f"{local:%H:%M:%S}", "bold"))
        date_line = f"{local:%a} {local.day} {local:%b}"
        if tt:
            hijri = format_hijri(local.date(), tt.hijri_adjustment)
            date_line += f"  ·  {hijri}" if hijri else ""

        grid = Table.grid(expand=True)
        grid.add_column(justify="left", no_wrap=True)
        grid.add_column(justify="center", ratio=1, no_wrap=True, overflow="ellipsis")
        grid.add_column(justify="right", no_wrap=True)
        if self.has_class("narrow"):
            grid.add_row(badge, center, clock)
            grid.add_row(Text(""), Text(date_line, style="dim"), Text(""))
        else:
            grid.add_row(badge, center, Text.assemble((date_line + "   ", "dim"), clock))
        self.query_one("#header", Static).update(grid)

    @staticmethod
    def _sky_position(tt: Timetable, t: datetime) -> Sky:
        """The sun between today's sunrise and maghrib, or the moon between maghrib and sunrise."""
        today = tt.today(t)
        times = tt.day(today).times
        if times[SUNRISE] <= t < times["maghrib"]:
            return Sky(True, (t - times[SUNRISE]) / (times["maghrib"] - times[SUNRISE]))
        if t >= times["maghrib"]:
            start, end = times["maghrib"], tt.day(today + timedelta(days=1)).times[SUNRISE]
        else:
            start, end = tt.day(today - timedelta(days=1)).times["maghrib"], times[SUNRISE]
        return Sky(False, (t - start) / (end - start))

    def update_countdown(self, tt: Timetable, t: datetime) -> None:
        start, _, period = tt.current_period(t)
        target, _, prayer = tt.next_prayer(t)
        seconds = max(0, int((target - t).total_seconds()))
        self.pulse.urgency = max(0.0, 1.0 - seconds / 1800) ** 1.5  # builds over the last 30 minutes
        self.sky = self._sky_position(tt, t)
        self.update_clock_digits()

        name = NAMES[prayer]
        if prayer == "dhuhr" and target.astimezone(tt.tz).weekday() == 4:
            name = "Jumu'ah"
        self.query_one("#next-label", Static).update(
            Text.assemble(("Until ", "dim"), (name, "bold $accent"), (f"  ·  {target.astimezone(tt.tz):%H:%M}", "dim"))
        )

        span = (target - start).total_seconds()
        self.query_one("#progress", ProgressBar).update(total=1.0, progress=(t - start).total_seconds() / span if span else 0)

        if period == SUNRISE:
            hint = Text("Sunrise has passed — no prayer until Dhuhr", style="dim")
        elif period == "fajr":
            sunrise = tt.day(tt.prayer_day(t)).times[SUNRISE]
            hint = Text.assemble(("Now ", "dim"), ("Fajr", "bold"), (f"  ·  ends at sunrise {sunrise.astimezone(tt.tz):%H:%M} (in {duration(sunrise - t)})", "dim"))
        else:
            hint = Text.assemble(("Now ", "dim"), (NAMES[period], "bold"), (f"  ·  since {start.astimezone(tt.tz):%H:%M}", "dim"))
        self.query_one("#hint", Static).update(hint)

    def update_table(self, tt: Timetable, t: datetime) -> None:
        day = self.view_day
        today = tt.today(t)
        panel = self.query_one("#today")
        try:
            schedule = tt.day(day)
        except ValueError:
            panel.border_title = f"No times for {day}"
            return

        _, current_day, current = tt.current_period(t)
        log = self.app.prayer_log
        rows = []
        for key in (*PRAYERS[:1], SUNRISE, *PRAYERS[1:]):
            start = schedule.times[key]
            name = "Jumu'ah" if key == "dhuhr" and schedule.jumua else NAMES[key]
            iqama = schedule.jumua if name == "Jumu'ah" else schedule.iqama.get(key)
            is_now = key == current and day == current_day

            if key == SUNRISE:
                check = Text(SUN, style="dim")
                status = Text("not a prayer", style="dim italic")
                style = "dim"
            else:
                prayed = log.is_prayed(day, key)
                late = prayed and log.is_late(day, key)
                locked = tt.lock_reason(day, key, t)
                check_style = "bold $warning" if late else ("bold $success" if prayed else ("dim" if locked else ""))
                check = Text(CHECKED if prayed else UNCHECKED, style=check_style)
                if late:
                    status = Text("logged late", style="$warning")
                elif is_now:
                    status = Text("● now", style="bold $accent")
                elif start > t:
                    status = Text(f"in {duration(start - t)}", style="dim")
                elif locked and not prayed and tt.can_log_late(day, key, t):
                    status = Text("not logged", style="dim italic")
                elif locked:
                    status = Text(f"{LOCK} locked", style="dim")
                else:
                    status = Text("prayed" if prayed else "", style="$success")
                style = "bold $accent" if is_now else ("dim" if start > t else "")

            rows.append((
                key,
                check,
                Text(name, style=style),
                Text(start.astimezone(tt.tz).strftime("%H:%M"), style=style),
                Text(iqama.astimezone(tt.tz).strftime("%H:%M") if iqama else "—", style="dim"),
                status,
            ))

        signature = (day, tuple((r[0], *(c.markup for c in r[1:])) for r in rows))
        if signature != self._table_signature:
            self._table_signature = signature
            table = self.query_one(DataTable)
            cursor = table.cursor_row
            table.clear()
            theme = self.app.current_theme
            for key, *cells in rows:
                table.add_row(*(themed(cell, theme) for cell in cells), key=key)
            if cursor is not None and table.row_count:
                table.move_cursor(row=min(cursor, table.row_count - 1), animate=False)

        done = len(log.prayed(day))
        panel.border_title = day_label(day, today)
        panel.border_subtitle = f"{done}/5 prayed" + (" · alhamdulillah" if done == 5 else "")
        panel.set_class(done == 5, "complete")

        note = Text()
        if day != today and day == tt.prayer_day(t):
            fajr = tt.day(today).times["fajr"].astimezone(tt.tz)
            note = Text(f"Isha is still open until Fajr at {fajr:%H:%M}", style="$warning")
        elif any(not log.is_prayed(day, p) and tt.can_log_late(day, p, t) for p in PRAYERS):
            note = Text.assemble(("Forgot to check one? Press ", "dim"), ("space", "bold"), (" on it to log it late.", "dim"))
        elif not self.following:
            note = Text("t  back to today", style="dim")
        self.query_one("#day-note", Static).update(note)

    def update_side(self, tt: Timetable, t: datetime) -> None:
        month = self.view_day.replace(day=1)
        today = tt.today(t)
        stats_panel = self.query_one("#stats-text", Static)
        width = max(20, stats_panel.size.width or 40)
        # The log changing resets this through reload(); prayers starting change the stats each minute at most
        signature = (month, self.view_day, today, t.hour, t.minute, width)
        if signature == self._side_signature:
            return
        self._side_signature = signature

        theme = self.app.current_theme
        self.update_week(tt, t, today, theme)
        grid, complete, partial = calendar_text(month, today, self.view_day, self.app.prayer_log, theme)
        panel = self.query_one("#month")
        panel.border_title = f"{month:%B %Y}"
        panel.border_subtitle = f"{complete} complete · {partial} partial"
        self.query_one("#calendar", Static).update(grid)

        green = theme.success or "green"
        legend = Text(justify="center")
        legend.append(PILL_LEFT, style=green)
        legend.append("  ", style=f"on {green}")
        legend.append(PILL_RIGHT, style=green)
        legend.append(" all 5   ", style="dim")
        legend.append("12", style=theme.warning or "yellow")
        legend.append(" some   ", style="dim")
        legend.append("12", style=f"bold underline {theme.accent or theme.primary}")
        legend.append(" today   ", style="dim")
        legend.append("[ ]", style="bold")
        legend.append(" month", style="dim")
        self.query_one("#legend", Static).update(legend)

        s = stats.compute(self.app.prayer_log, tt, t, month)
        text = Text(no_wrap=True)
        label = 13
        text.append(f"{'Streak':<{label}}", style="dim")
        text.append(f"{s.streak} day{'s' if s.streak != 1 else ''}", style="bold $success" if s.streak else "bold")
        text.append(f"   best {s.best_streak}\n", style="dim")
        text.append(f"{'This month':<{label}}", style="dim")
        text.append(f"{s.month_complete}", style="bold")
        text.append(f" / {s.month_days} days complete\n", style="dim")
        late = self.app.prayer_log.late_count(month, today)
        text.append(f"{'Logged late':<{label}}", style="dim")
        text.append(f"{late}", style="bold $warning" if late else "bold")
        text.append(" this month\n\n", style="dim")
        if s.has_data:
            text.append(f"Last {s.window_days} day{'s' if s.window_days != 1 else ''}\n", style="dim")
            bar_width = max(6, width - 9 - 6)
            for prayer in PRAYERS:
                prayed, possible = s.per_prayer[prayer]
                fraction = prayed / possible if possible else 0
                color = theme.success if fraction >= 0.8 else (theme.warning if fraction >= 0.5 else theme.error)
                text.append(f"{NAMES[prayer]:<9}")
                text.append_text(bar(fraction, bar_width, color or "green"))
                text.append(f" {round(fraction * 100):>3}%\n" if possible else "    —\n", style="dim")
        else:
            text.append("Check off prayers with space to track your progress here.", style="dim")
        text.rstrip()
        stats_panel.update(text)

    def update_week(self, tt: Timetable, t: datetime, today: date, theme: Theme) -> None:
        """The week around the viewed day: every time, green when prayed."""
        monday = self.view_day - timedelta(days=self.view_day.weekday())
        sunday = monday + timedelta(days=6)
        panel = self.query_one("#week")
        panel.border_title = f"Week {monday.isocalendar().week}"
        panel.border_subtitle = f"{monday.day} {monday:%b} – {sunday.day} {sunday:%b}"

        green = theme.success or "green"
        accent = theme.accent or theme.primary
        table = Table(box=None, expand=True, pad_edge=False, show_edge=False, padding=(0, 1), header_style="dim")
        table.add_column("", no_wrap=True)
        for key in (*PRAYERS[:1], SUNRISE, *PRAYERS[1:]):
            table.add_column(NAMES[key] if key != SUNRISE else "Sunrise", justify="center", no_wrap=True)
        table.add_column("", justify="right", no_wrap=True)
        log = self.app.prayer_log
        for i in range(7):
            day = monday + timedelta(days=i)
            try:
                times = tt.day(day).times
            except ValueError:
                continue
            is_today, is_view = day == today, day == self.view_day
            label_style = f"bold {accent}" if is_today else ("bold" if is_view else "")
            cells = [Text(("› " if is_view else "  ") + f"{day:%a} {day.day:>2}", style=label_style)]
            for key in (*PRAYERS[:1], SUNRISE, *PRAYERS[1:]):
                value = times[key].astimezone(tt.tz).strftime("%H:%M")
                if key == SUNRISE:
                    style = "dim italic"
                elif log.is_late(day, key):
                    style = f"bold {theme.warning or 'yellow'}"
                elif log.is_prayed(day, key):
                    style = f"bold {green}"
                elif times[key] > t:
                    style = "dim"
                else:
                    style = ""
                cells.append(Text(value, style=style))
            done = len(log.prayed(day))
            cells.append(Text(f"{done}/5", style=f"bold {green}" if done == 5 else ("dim" if not done else "")))
            table.add_row(*cells)
        self.query_one("#week-table", Static).update(table)

    # --- actions ---

    def action_toggle(self) -> None:
        tt = self.timetable
        table = self.query_one(DataTable)
        if tt is None or not table.row_count:
            return
        key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value
        day, log, t = self.view_day, self.app.prayer_log, now()
        reason = tt.lock_reason(day, key, t)
        if not reason:
            log.toggle(day, key)
            self.reload()
            self.app.refresh_bar()
            return

        when = f"{NAMES[key]} on {day:%A} {day.day} {day:%B}"
        if tt.can_log_late(day, key, t) and not log.is_prayed(day, key):
            question = LateLogScreen(
                f"Log {when} as prayed?",
                "It counts for your streak, and stays marked as logged late.",
                "Log it",
            )
            self.app.push_screen(question, lambda ok: ok and self._set_late(day, key, True))
        elif tt.can_log_late(day, key, t) and log.is_late(day, key):
            question = LateLogScreen(f"Remove the late log for {when}?", "", "Remove", danger=True)
            self.app.push_screen(question, lambda ok: ok and self._set_late(day, key, False))
        elif tt.can_log_late(day, key, t):
            self.notify(f"{when} was checked on time, so it's locked", severity="warning", timeout=3)
        elif key in PRAYERS and now() >= tt.day(day).times[key] and day < tt.today(t):
            self.notify(f"{reason}. Late logging is only possible for the last {LATE_LOG_DAYS} days.", severity="warning", timeout=4)
        else:
            self.notify(reason, severity="warning", timeout=3)

    def _set_late(self, day: date, prayer: str, prayed: bool) -> None:
        self.app.prayer_log.set_late(day, prayer, prayed)
        self.reload()
        self.app.refresh_bar()

    @on(DataTable.RowSelected)
    def row_clicked(self) -> None:
        self.action_toggle()

    def _view(self, day: date) -> None:
        self.view_day = day
        self.following = self.timetable is not None and day == self.timetable.prayer_day(now())
        self.reload()

    def action_shift_day(self, days: int) -> None:
        if self.view_day:
            self._view(self.view_day + timedelta(days=days))

    def action_shift_month(self, months: int) -> None:
        if self.view_day:
            index = self.view_day.year * 12 + self.view_day.month - 1 + months
            year, month = divmod(index, 12)
            self._view(date(year, month + 1, min(self.view_day.day, cal.monthrange(year, month + 1)[1])))

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # Nothing scrolls when everything fits side by side, so hide the scroll keys then
        if action == "scroll":
            return self.has_class("narrow")
        return True

    def action_scroll(self, how: str) -> None:
        body = self.query_one("#body")
        {
            "down": lambda: body.scroll_relative(y=3, animate=False),
            "up": lambda: body.scroll_relative(y=-3, animate=False),
            "page_down": body.scroll_page_down,
            "page_up": body.scroll_page_up,
            "home": lambda: body.scroll_home(animate=False),
            "end": lambda: body.scroll_end(animate=False),
        }[how]()

    def action_go_today(self) -> None:
        self.following = True
        self.reload()

    def action_choose_place(self) -> None:
        self.app.choose_place()

    def action_choose_theme(self) -> None:
        self.app.push_screen(ThemeScreen())

    def action_refresh(self) -> None:
        self.app.refresh_timetable(quiet=False)


class LateLogScreen(ModalScreen[bool]):
    """Confirm logging (or un-logging) a prayer after its day is over."""

    BINDINGS = [
        Binding("y,enter", "answer(True)", "Yes"),
        Binding("n,escape", "answer(False)", "No"),
    ]

    def __init__(self, question: str, detail: str, confirm: str, danger: bool = False) -> None:
        super().__init__()
        self.question, self.detail, self.confirm, self.danger = question, detail, confirm, danger

    def compose(self) -> ComposeResult:
        with Vertical(id="late-log", classes="panel"):
            yield ThemedStatic(Text(self.question, style="bold"), id="late-question")
            if self.detail:
                yield ThemedStatic(Text(self.detail, style="dim"), id="late-detail")
            with Center(id="late-buttons"):
                yield Button(f"{self.confirm}  (y)", variant="error" if self.danger else "warning", id="yes")
                yield Button("Cancel  (n)", id="no")

    def on_mount(self) -> None:
        self.query_one("#late-log").border_title = "Log late"

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_answer(self, answer: bool) -> None:
        self.dismiss(answer)


# --- mosque / city picker ----------------------------------------------------


class PlaceScreen(Screen):
    BINDINGS = [Binding("escape", "cancel", "Back")]

    def __init__(self, first_run: bool = False) -> None:
        super().__init__()
        self.first_run = first_run
        self.results: list[Place] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="picker", classes="panel"):
            yield ThemedStatic(
                Text.assemble(
                    ("Mosques publish their own times on ", "dim"), ("Mawaqit", "bold"), (" and ", "dim"),
                    ("my-masjid", "bold"), ("; ", "dim"), ("islam.nu", "bold"), (" has a timetable for each Swedish city.", "dim"),
                ),
                id="picker-intro",
            )
            yield Input(placeholder="Search a mosque or city, then press Enter", id="search")
            yield OptionList(id="results")
            yield ThemedStatic(id="picker-status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#picker").border_title = "Choose where your prayer times come from"
        self.status("Finding mosques in Stockholm and Växjö…")
        self.load_featured()
        self.query_one(OptionList).focus()

    def status(self, message: str, style: str = "dim") -> None:
        self.query_one("#picker-status", Static).update(Text(message, style=style))

    def _prompt(self, place: Place) -> Text:
        current = self.app.place
        theme = self.app.current_theme
        distance = place.distance_km(*STOCKHOLM) if place.provider == "mawaqit" else None
        prompt = Text.assemble(
            ("● " if current and current.key == place.key else "  ", "$success"),
            (place.name, "bold"),
            (f"  {place.kind}", "$secondary" if place.provider == "islamnu" else "$accent"),
            "\n  ",
            (place.address or "—", "dim"),
            (f"  ·  {place.source}", "dim"),
        )
        return themed(prompt, theme)

    def show(self, sections: list[tuple[str, list[Place]]], heading: str) -> None:
        self.results = []
        options = self.query_one(OptionList)
        options.clear_options()
        theme = self.app.current_theme
        for title, places in sections:
            if title:
                options.add_option(Option(themed(Text(f"── {title} ", style="bold $primary"), theme), disabled=True))
            for place in places:
                self.results.append(place)
                options.add_option(Option(self._prompt(place), id=str(len(self.results) - 1)))
        first = next((i for i, o in enumerate(options.options) if not o.disabled), None)
        options.highlighted = first
        self.status(heading if self.results else "Nothing found — try another name")

    @work(thread=True, exclusive=True, group="search")
    def load_featured(self) -> None:
        try:
            sections = sources.featured()
        except SourceError as error:
            self.app.call_from_thread(self.status, str(error), "$error")
            return
        count = sum(len(places) for _, places in sections)
        self.app.call_from_thread(self.show, sections, f"{count} sources for Stockholm and Växjö · search to find others")

    @work(thread=True, exclusive=True, group="search")
    def search(self, query: str) -> None:
        try:
            places = sources.search(query)
        except SourceError as error:
            self.app.call_from_thread(self.status, str(error), "$error")
            return
        cities = [p for p in places if p.provider == "islamnu"]
        mosques = [p for p in places if p.provider != "islamnu"]
        sections = [(title, group) for title, group in (("Mosques", mosques), ("Cities · islam.nu", cities)) if group]
        self.app.call_from_thread(self.show, sections, f"{len(places)} results for “{query}”")

    @on(Input.Submitted)
    def submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if query:
            self.status(f"Searching “{query}”…")
            self.search(query)
        else:
            self.status("Finding mosques in Stockholm and Växjö…")
            self.load_featured()
        self.query_one(OptionList).focus()

    @on(OptionList.OptionSelected)
    def selected(self, event: OptionList.OptionSelected) -> None:
        place = self.results[int(event.option.id)]
        self.status(f"Downloading this year's times for {place.name}…")
        self.load_timetable(place)

    @work(thread=True, exclusive=True, group="timetable")
    def load_timetable(self, place: Place) -> None:
        try:
            data = sources.fetch_timetable(place)
            Timetable.from_data(data).day(date.today())  # make sure it's usable
        except (SourceError, ValueError, KeyError) as error:
            self.app.call_from_thread(self.status, str(error), "$error")
            return
        self.app.call_from_thread(self.dismiss, (place, data))

    def action_cancel(self) -> None:
        if self.first_run:
            self.app.exit()
        else:
            self.dismiss(None)


# --- theme picker ------------------------------------------------------------


class ThemeScreen(ModalScreen):
    """Pick a theme; highlighting previews it, Enter keeps it, Escape goes back."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="themes", classes="panel"):
            yield OptionList(id="theme-list")
        yield Footer()

    def on_mount(self) -> None:
        panel = self.query_one("#themes")
        panel.border_title = "Theme"
        panel.border_subtitle = "↑↓ preview · enter keep · esc cancel · c/s outside"
        self.original = self.app.theme_choice
        options = self.query_one(OptionList)
        self.names: list[str | None] = []

        def add(name: str | None, label: Text | str) -> None:
            self.names.append(name)
            options.add_option(Option(label, disabled=name is None))

        add(themes.SYSTEM, Text.assemble(("System", "bold"), ("  follows your Omarchy theme", "dim")))
        add(None, Text("── Omarchy themes", style="dim"))
        for name, label, _ in self.app.omarchy_theme_list:
            add(name, label)
        add(None, Text("── Built-in", style="dim"))
        for name, label in themes.textual_themes():
            add(name, label)
        if self.original in self.names:
            options.highlighted = self.names.index(self.original)
        options.focus()

    @on(OptionList.OptionHighlighted)
    def preview(self, event: OptionList.OptionHighlighted) -> None:
        name = self.names[event.option_index]
        if name:
            self.app.apply_theme(name)

    @on(OptionList.OptionSelected)
    def keep(self, event: OptionList.OptionSelected) -> None:
        name = self.names[event.option_index]
        if name:
            self.app.apply_theme(name, save=True)
            self.dismiss()

    def action_cancel(self) -> None:
        self.app.apply_theme(self.original)
        self.dismiss()


# --- app ---------------------------------------------------------------------


class AlAqsaApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "Al-Aqsa"

    def __init__(self) -> None:
        super().__init__()
        storage.migrate_legacy_dirs()
        self.settings = storage.load_config()
        self.prayer_log = storage.PrayerLog.load()
        self.place: Place | None = None
        self.timetable: Timetable | None = None
        self.theme_choice = self.settings.get("theme", themes.SYSTEM)
        self.omarchy_theme_list = themes.omarchy_themes()
        self._system_stamp = None
        self.notifications_on = self.settings.get("notify", True)
        self.main = MainScreen()

    def save_settings(self, _remove: tuple[str, ...] = (), **changes) -> None:
        """Save only these settings, keeping anything else in the file as it is on disk."""
        self.settings = storage.update_config(changes, _remove)

    # --- themes ---

    def _register_system_theme(self) -> bool:
        theme = themes.system_theme()
        if theme:
            self.register_theme(theme)
            self._system_stamp = themes.system_stamp()
        return theme is not None

    def apply_theme(self, name: str, save: bool = False) -> None:
        if name == themes.SYSTEM and not self._register_system_theme():
            name = "tokyo-night"
        elif name.startswith("omarchy-") and name not in self.available_themes:
            path = next((p for n, _, p in self.omarchy_theme_list if n == name), None)
            theme = themes.from_colors(name, path) if path else None
            if theme is None:
                name = "tokyo-night"
            else:
                self.register_theme(theme)
        if name not in self.available_themes:
            name = "tokyo-night"
        self.theme = name
        self.main.reload()
        if save:
            self.theme_choice = name
            self.save_settings(theme=name)

    def theme_choices(self) -> list[tuple[str, str]]:
        """Every theme as (name, label), in the order the theme picker shows them."""
        return [
            (themes.SYSTEM, "System (follows Omarchy)"),
            *((name, label) for name, label, _ in self.omarchy_theme_list),
            *themes.textual_themes(),
        ]

    def _switch_theme(self, name: str, label: str) -> None:
        self.apply_theme(name, save=True)
        self.clear_notifications()  # don't pile up toasts while cycling fast
        self.notify(f"Theme: {label}", timeout=1.5)

    def action_cycle_theme(self, step: int) -> None:
        choices = self.theme_choices()
        names = [name for name, _ in choices]
        index = names.index(self.theme_choice) if self.theme_choice in names else 0
        self._switch_theme(*choices[(index + step) % len(choices)])

    def action_random_theme(self) -> None:
        self._switch_theme(*random.choice([c for c in self.theme_choices() if c[0] != self.theme_choice]))

    @work(thread=True, exclusive=True, group="notify")
    def action_toggle_notifications(self) -> None:
        enable = not self.notifications_on
        if enable and not notifier.set_service(True):
            self.call_from_thread(self.notify, "Couldn't start the notification service (systemd --user)", severity="error")
            return
        self.notifications_on = enable
        self.save_settings(notify=enable)
        self.refresh_bar()
        self.call_from_thread(self.main.reload)
        if enable:
            notifier.play_chime()
            self.call_from_thread(self.notify, "Prayer notifications on — you'll hear this when each prayer starts, even with the app closed", timeout=5)
        else:
            self.call_from_thread(self.notify, "Prayer notifications muted", timeout=2)

    @work(thread=True, group="bar")
    def refresh_bar(self) -> None:
        """Update the Omarchy bar widget's status file right away (Omarchy only)."""
        if barstatus.is_omarchy():
            try:
                barstatus.write()
            except (OSError, ValueError, KeyError):
                pass

    @work(thread=True, group="setup")
    def ensure_background(self) -> None:
        """Keep the background service running, and on Omarchy add the bar widget the first time."""
        if not notifier.service_enabled():
            notifier.set_service(True)
        if barstatus.is_omarchy() and self.settings.get("omarchy_bar") is None:
            from . import cli

            cli.omarchy_bar("install")
            self.settings = storage.load_config()

    def _follow_system_theme(self) -> None:
        """Pick up `omarchy theme set ...` while running."""
        if self.theme_choice != themes.SYSTEM or self.theme != themes.SYSTEM:
            return
        if themes.system_stamp() != self._system_stamp and self._register_system_theme():
            self.theme = "textual-dark"  # re-apply the updated theme under the same name
            self.theme = themes.SYSTEM
            self.main.reload()

    # --- lifecycle ---

    def on_mount(self) -> None:
        self.apply_theme(self.theme_choice)
        self.set_interval(2, self._follow_system_theme)
        self.ensure_background()
        self.visibility = VisibilityWatcher(lambda visible: self.call_from_thread(self.main.set_active, visible))
        self.visibility.start()
        self.push_screen(self.main)

        saved = self.settings.get("place") or self.settings.get("mosque")
        try:
            self.place = Place.from_dict(saved)
        except (TypeError, AttributeError):
            self.choose_place(first_run=True)
            return

        cached = storage.load_timetable(self.place.key)
        if cached:
            data, fetched_at = cached
            self.timetable = Timetable.from_data(data)
            self.main.reload()
            if sources.needs_refresh(data, fetched_at):
                self.refresh_timetable(quiet=True)
        else:
            self.refresh_timetable(quiet=False)

    def choose_place(self, first_run: bool = False) -> None:
        self.push_screen(PlaceScreen(first_run), self._place_chosen)

    def _place_chosen(self, result: tuple[Place, dict] | None) -> None:
        if not result:
            return
        place, data = result
        storage.save_timetable(place.key, data)
        self.save_settings(place=place.to_dict(), _remove=("mosque",))
        self.place = place
        self.timetable = Timetable.from_data(data)
        self.main.reload()
        self.refresh_bar()
        self.notify(f"Using prayer times from {place.name} ({place.source})", timeout=3)

    @work(thread=True, exclusive=True, group="refresh")
    def refresh_timetable(self, quiet: bool) -> None:
        place = self.place
        if place is None:
            return
        try:
            data = sources.fetch_timetable(place)
            timetable = Timetable.from_data(data)
            timetable.day(date.today())
        except (SourceError, ValueError, KeyError) as error:
            if self.timetable is None:
                message, severity = f"{error}. Press r to try again or m to pick another source.", "error"
            else:
                message, severity = f"{error}. Using the saved timetable.", "warning"
            if not quiet or self.timetable is None:
                self.call_from_thread(self.notify, message, severity=severity, timeout=6)
            return
        storage.save_timetable(place.key, data)
        self.call_from_thread(self._timetable_refreshed, timetable, quiet)

    def _timetable_refreshed(self, timetable: Timetable, quiet: bool) -> None:
        self.timetable = timetable
        self.main.reload()
        self.refresh_bar()
        if not quiet:
            self.notify("Prayer times updated", timeout=2)


def main() -> None:
    import sys

    from . import cli

    code = cli.main(sys.argv[1:])
    if code is not None:
        sys.exit(code)
    AlAqsaApp().run()
