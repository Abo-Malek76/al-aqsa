# Al-Aqsa

Prayer times from your mosque, a countdown to the next prayer and a prayer tracker — in the terminal.

- **Mosques** that publish their own official timetable:
  - Växjö Muslimer (Försommarvägen 2, Växjö) via [my-masjid](https://my-masjid.com)
  - [Mawaqit](https://mawaqit.net) mosques, e.g. Skärholmen SIKF and Vårby Gård VISUK in Stockholm
  - Stockholms moské (Kapellgränd 10) has no public feed yet; use the islam.nu Stockholm timetable
- **City timetables** from [islam.nu](https://islam.nu/bonetider/) for 60+ Swedish cities, including Stockholm and Växjö.
- Follows your Omarchy theme live, or pick any Omarchy/built-in theme with `T`.

> [!NOTE]
> **Made and tested on [Omarchy](https://omarchy.org).** Al-Aqsa was built on and for Omarchy, and
> that's where it works best: it follows your Omarchy theme, adds a prayer widget to the Omarchy bar,
> and saves power using Hyprland. The core app — prayer times, countdown, check-offs, calendar and
> notifications — should work on any Linux terminal, and you're very welcome to run it without
> Omarchy. The Omarchy-only parts simply switch themselves off. If you get it working somewhere
> else, or hit a snag, feel free to open an issue or a pull request.

## Installation guide

### 1. What you need

**On Omarchy:** nothing extra — everything is already there. Skip to step 2.

**On other Linux systems:**

- **Python 3.11 or newer** and **git**
- A terminal using a **[Nerd Font](https://www.nerdfonts.com/)** (for the icons, checkboxes and the rounded calendar)
- Optional, for the extras:
  - `notify-send` (libnotify) and `pw-play` or `paplay` — prayer notifications and their sound
  - a **systemd user session** — notifications while the app is closed
  - `rsvg-convert` (librsvg) — the launcher icon
  - `parec` (PipeWire/PulseAudio) — the *Music* visualizer

| Distribution | Command |
|---|---|
| Arch | `sudo pacman -S --needed python git libnotify librsvg pipewire-pulse` |
| Debian / Ubuntu | `sudo apt install python3 python3-venv git libnotify-bin librsvg2-bin pulseaudio-utils` |
| Fedora | `sudo dnf install python3 git libnotify librsvg2-tools pulseaudio-utils` |

### 2. Download and install

```sh
git clone https://github.com/Abo-Malek76/al-aqsa.git ~/al-aqsa
cd ~/al-aqsa
./install.sh
```

`install.sh` only touches your own user folders — no `sudo`. It creates a private Python
environment inside the folder, the `al-aqsa` command (in `~/.local/bin`), a launcher entry and the
icon. Keep the folder where it is; the app runs from it.

### 3. First run

1. Open **Al-Aqsa** from your app launcher (on Omarchy: `SUPER + SPACE` → *Al-Aqsa*), or run `al-aqsa`.
2. Pick your mosque or city from the list, or search for one and press Enter.
3. That's it. On Omarchy the prayer widget appears in the bar, and prayer notifications are on
   (press `n` to mute them).

If `al-aqsa` says *command not found*, add `~/.local/bin` to your `PATH` (Omarchy already has it).

### What works where

| Feature | Omarchy | Other Linux |
|---|:---:|:---:|
| Prayer times, countdown, check-offs, calendar, streaks | ✓ | ✓ |
| Clock fonts, digit animations, scenes, themes | ✓ | ✓ (built-in themes) |
| Prayer notifications with a chime | ✓ | ✓ with a systemd user session and `notify-send` |
| Follows your desktop theme live | ✓ | — |
| Bar widget and prayer panel | ✓ | — |
| Pauses animations when the window is hidden | ✓ | Hyprland only |

### Updating

```sh
cd ~/al-aqsa
git pull
./install.sh
```

### Uninstalling

```sh
cd ~/al-aqsa
./uninstall.sh            # keeps your settings and prayer log
./uninstall.sh --purge    # deletes them too
```

This removes the command, launcher entry, icon, background service and (on Omarchy) the bar widget.
Then delete the folder.

### Troubleshooting

- **Boxes or question marks instead of icons** — your terminal isn't using a Nerd Font.
- **No notifications** — check the background service: `systemctl --user status al-aqsa-notify`,
  and test the sound and popup with `~/al-aqsa/.venv/bin/python -m alaqsa.notifier --test`.
- **The bar widget doesn't show or doesn't update (Omarchy)** — `al-aqsa --omarchy-bar install`,
  then `omarchy restart shell`.
- **"Couldn't reach Mawaqit"** — you're offline; the app keeps using the last downloaded timetable.

## Keys

| Key | Action |
|-----|--------|
| `space` / `enter` / click | Check or uncheck the selected prayer |
| `←` `→` (`h` `l`) | Previous / next day |
| `[` `]` | Previous / next month |
| `t` | Back to today |
| `m` | Change mosque or city |
| `Ctrl+c` / `T` | Pick a theme (System follows Omarchy; ↑↓ previews) |
| `c` / `C` | Next / previous theme |
| `s` | Random theme |
| `v` / `V` | Next / previous visual around the clock |
| `f` | Clock font: Classic → Script → Bold → Italic → LED |
| `a` | Digit animation: Roll → Flip → Drop → Dissolve → Scramble → None |
| `x` | Clock shows hours:minutes:seconds or just hours:minutes |
| `n` | Prayer notifications on/off (the 󰂚 bell in the header) |
| `r` | Re-download the timetable |
| `j` `k` | Scroll down / up (narrow windows, where the panels stack) |
| `PgDn` `PgUp` | Scroll a page |
| `g` `G` | Jump to top / bottom |
| `q` | Quit |

## Omarchy bar (Omarchy only)

On Omarchy the app adds a section to the bar next to the clock — `󱠧 Fajr 4h 41m`, styled like
the rest of the bar (it only takes the accent colour in the last 10 minutes or when a prayer starts).

- **Left click** opens the prayer panel (same design as the clock's calendar): the next prayer and
  countdown, a rail from the last prayer to the next, and today's times. **Click a row** — or use
  ↑↓ / j k and Enter / Space — to check a prayer off (same rules as the app; locked rows explain why).
  The bell mutes notifications (`n`), the arrow button opens the app (`o`), Esc closes.
- **Right click** checks off the prayer that's on now. **Middle click** opens Al-Aqsa.

The plugin lives in `omarchy/zephyrus.al-aqsa/` and is installed to `~/.config/omarchy/plugins/`.
`al-aqsa --omarchy-bar install` / `remove` adds or removes it. The background service keeps
`$XDG_RUNTIME_DIR/al-aqsa/bar.json` up to date; the widget does its own per-second countdown.

## Saving resources

On Hyprland the app watches whether its window is actually on screen. When it's on a workspace
nobody is looking at, or behind a fullscreen game, the clock animation, scenes, music listening and
per-second updates pause (≈0.3% CPU instead of ~5–10%). Visible but unfocused — e.g. on a second
monitor or the tablet — it keeps animating.

## Prayer notifications

When a prayer starts you get a desktop notification and a soft three-note chime (not an adhan) —
even with the app closed, via the `al-aqsa-notify` systemd user service. Mute/unmute with `n` (the background service keeps running for the bar);
test with `.venv/bin/python -m alaqsa.notifier --test`. The built-in chime is generated by
`tools/make_chime.py`; to use your own WAV instead, set `"notify_sound"` in
`~/.config/al-aqsa/config.json` to its path (e.g. copy it to `~/.local/share/al-aqsa/sounds/`).

## Countdown clock

Five fonts (`f`) — Classic, Script (a calligraphic italic typeface), Bold, Italic and LED dot-matrix —
and an animation for every digit that changes (`a`): Roll (odometer), Flip (split-flap board),
Drop (falls in and bounces), Dissolve, Scramble, or None. Both are remembered.

## Visualizer

cliamp-style braille spectrum bars around the countdown, with the digits flashing on each beat.

- **Pulse** (default): every second is a beat, getting stronger over the last 30 minutes before a prayer.
- **Music**: reacts to whatever is playing on your computer (listens to the default output through
  `parec`; analysed in memory, never recorded). Falls back to Pulse when nothing is playing.
- **Scenes**: Fireflies, Night sky (with shooting stars), Rain, Snow, Waves, Aurora, Matrix,
  and Sky — the sun's real position between sunrise and Maghrib, the moon at night.
- **Off**: no animation, no CPU cost.

## Rules

- Sunrise is shown but is not a prayer, so it can't be checked.
- A prayer can't be checked before its time starts.
- Past days are locked — except Isha, which stays open until the next Fajr.
- Forgot to check a prayer you did pray? Go to that day and press `space` on it to **log it late**
  (up to 7 days back). It counts for your streak but stays marked in amber as logged late.
- The day view switches to the new day at Fajr, not midnight.

## Files

- `~/.config/al-aqsa/config.json` — chosen mosque/city and theme
- `~/.local/share/al-aqsa/prayed.json` — your prayer log
- `~/.local/share/al-aqsa/timetables/` — cached yearly timetable (works offline, refreshed weekly)

## Development

```sh
python -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -m unittest discover -s tests
```
