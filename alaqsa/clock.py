"""The big countdown clock: several digit fonts and an animation for every digit that changes."""

from __future__ import annotations

import math
import random
import time

from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widget import Widget

DURATION = 0.45  # seconds a digit takes to change
FPS = 30
DIM_CHARS = "·"  # unlit pixels (LED) are drawn dimmed

# --- fonts ---------------------------------------------------------------------

# Classic: thin rounded box-drawing digits (3 rows)
CLASSIC = {
    "0": ["╭─╮", "│ │", "╰─╯"], "1": ["╶┐ ", " │ ", "╶┴╴"], "2": ["╶─╮", "╭─╯", "╰─╴"],
    "3": ["╶─╮", " ─┤", "╶─╯"], "4": ["╷ ╷", "╰─┤", "  ╵"], "5": ["╭─╴", "╰─╮", "╶─╯"],
    "6": ["╭─╴", "├─╮", "╰─╯"], "7": ["╶─┐", "  │", "  ╵"], "8": ["╭─╮", "├─┤", "╰─╯"],
    "9": ["╭─╮", "╰─┤", "╶─╯"], ":": [" ", "•", " "], "-": ["   ", "╶─╴", "   "], " ": ["   "] * 3,
}

# Script: a real calligraphic italic typeface, drawn in braille dots (2×4 per character)
SCRIPT_FONT = ("URW Bookman:style=Demi Italic", "/usr/share/fonts/gsfonts/URWBookman-DemiItalic.otf")

# 5×7 pixel digits, drawn as Bold (half blocks), Italic (slanted Bold) or LED (dots)
PIXELS = {
    "0": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    ":": [".", ".", "#", ".", "#", ".", "."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    " ": ["....."] * 7,
}


def _half_blocks(bitmap: list[str], wide: bool) -> list[str]:
    """Two pixel rows per character using ▀ ▄ █; `wide` doubles each pixel horizontally."""
    rows = bitmap + ["." * len(bitmap[0])] * (len(bitmap) % 2)
    out = []
    for top, bottom in zip(rows[::2], rows[1::2]):
        line = ""
        for a, b in zip(top, bottom):
            ch = {("#", "#"): "█", ("#", "."): "▀", (".", "#"): "▄"}.get((a, b), " ")
            line += ch * (2 if wide else 1)
        out.append(line)
    return out


LED_TOP, LED_BOTTOM = 0x1B, 0xE4  # a 2×2 braille dot cluster in the top / bottom half of a cell


def _led(bitmap: list[str], wide: bool) -> list[str]:
    """Dot-matrix LEDs: each lit pixel is a small cluster of braille dots, two pixel rows per line."""
    rows = bitmap + ["." * len(bitmap[0])] * (len(bitmap) % 2)
    return [
        "".join(chr(0x2800 | (LED_TOP if a == "#" else 0) | (LED_BOTTOM if b == "#" else 0)) for a, b in zip(top, bottom))
        for top, bottom in zip(rows[::2], rows[1::2])
    ]


def _find_font(pattern: str, fallback: str) -> str | None:
    import os
    import subprocess

    try:
        path = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True, timeout=3).stdout
        if path and "Italic" in path:
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    return fallback if os.path.exists(fallback) else None


def _typeface(pattern: str, fallback: str):
    """Glyphs rendered from a system font into fine braille strokes (4 rows tall);
    falls back to Classic without Pillow or the font."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return _from_art(CLASSIC)
    path = _find_font(pattern, fallback)
    if path is None:
        return _from_art(CLASSIC)
    font = ImageFont.truetype(path, 18)
    height = 16  # 4 text rows of 4 braille dots

    def build(char: str, wide: bool) -> list[str]:
        left, top, right, bottom = font.getbbox("0123456789")
        advance = font.getlength("0") if char not in ":- " else font.getlength(":") + 2
        width = int(advance) + 6
        width += width % 2
        img = Image.new("L", (width, height), 0)
        if char.strip():
            ImageDraw.Draw(img).text((3, (height - (bottom - top)) // 2 - top), char, font=font, fill=255)
        px = img.load()
        return [
            "".join(
                chr(0x2800 | sum(BRAILLE_BITS[dy][dx] for dy in range(4) for dx in range(2) if px[cx + dx, cy + dy] > 100))
                for cx in range(0, width, 2)
            )
            for cy in range(0, height, 4)
        ]

    def cropped(char: str, wide: bool) -> list[str]:
        # Trim the blank columns every digit shares, so the clock isn't needlessly wide
        if wide not in spans:
            used = [
                i
                for c in "0123456789"
                for i, column in enumerate(zip(*build(c, wide)))
                if any(ch != "⠀" for ch in column)
            ]
            spans[wide] = (min(used), max(used) + 1)
        rows = build(char, wide)
        if char in ":- ":
            used = [i for i, column in enumerate(zip(*rows)) if any(ch != "⠀" for ch in column)]
            lo, hi = (min(used), max(used) + 1) if used else (0, 1)
            return [row[lo:hi] for row in rows]
        lo, hi = spans[wide]
        return [row[lo:hi] for row in rows]

    spans: dict[bool, tuple[int, int]] = {}
    return cropped


BRAILLE_BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))


def _slant(glyph: list[str]) -> list[str]:
    """Shear a glyph to the right, top rows further than bottom rows (italic)."""
    n = len(glyph)
    return [" " * (n - 1 - i) + row + " " * i for i, row in enumerate(glyph)]


class Font:
    def __init__(self, name: str, build, slant: bool = False, strokes: dict | None = None) -> None:
        self.name = name
        self._build = build  # (char, wide) -> rows
        self.slant = slant
        # Characters swapped when slanted, so vertical strokes stay connected
        self.strokes = str.maketrans(strokes or {})
        self._cache: dict[tuple[str, bool], list[str]] = {}

    def glyph(self, char: str, wide: bool) -> list[str]:
        key = (char, wide)
        if key not in self._cache:
            rows = self._build(char, wide)
            self._cache[key] = rows
        return self._cache[key]

    def rows(self, wide: bool) -> int:
        return len(self.glyph("0", wide))


def _from_art(art: dict[str, list[str]]):
    return lambda char, wide: list(art.get(char, art[" "]))


def _from_pixels(draw):
    # Always the normal-width version: keeps every font about as big as Classic
    return lambda char, wide: draw(PIXELS.get(char, PIXELS[" "]), False)


FONTS = {
    "classic": Font("Classic", _from_art(CLASSIC)),
    "script": Font("Script", _typeface(*SCRIPT_FONT)),
    "bold": Font("Bold", _from_pixels(_half_blocks)),
    "italic": Font("Italic", _from_pixels(_half_blocks), slant=True),
    "led": Font("LED", _from_pixels(_led)),
}

# --- animations ------------------------------------------------------------------


def _ease_out(p: float) -> float:
    return 1 - (1 - p) ** 3


def _bounce(p: float) -> float:
    """Ease-out bounce (0..1)."""
    n, d = 7.5625, 2.75
    if p < 1 / d:
        return n * p * p
    if p < 2 / d:
        p -= 1.5 / d
        return n * p * p + 0.75
    if p < 2.5 / d:
        p -= 2.25 / d
        return n * p * p + 0.9375
    p -= 2.625 / d
    return n * p * p + 0.984375


def _blank(glyph: list[str]) -> list[str]:
    return [" " * len(row) for row in glyph]


def roll(old: list[str], new: list[str], p: float, seed: int) -> list[str]:
    """Odometer: the old digit rolls up and out as the new one rolls in from below."""
    n = len(new)
    shift = round(_ease_out(p) * n)
    return (old + new)[shift : shift + n]


def drop(old: list[str], new: list[str], p: float, seed: int) -> list[str]:
    """The new digit falls in from above and bounces."""
    n = len(new)
    offset = round((1 - _bounce(p)) * n)
    return (_blank(new) * 1)[:offset] + new[: n - offset] if offset else list(new)


def flip(old: list[str], new: list[str], p: float, seed: int) -> list[str]:
    """Split-flap: the old digit folds down to a line, then the new one unfolds."""
    n = len(new)
    source, amount = (old, 1 - p * 2) if p < 0.5 else (new, p * 2 - 1)
    height = max(1, round(amount * n))
    top = (n - height) // 2
    out = _blank(new)
    for i in range(height):
        out[top + i] = source[min(n - 1, int(i * n / height))]
    if height <= 1:
        out[n // 2] = "─" * len(new[0])
    return out


def dissolve(old: list[str], new: list[str], p: float, seed: int) -> list[str]:
    """Pixels of the old digit fade out as the new ones fade in."""
    out = []
    for y, (a, b) in enumerate(zip(old, new)):
        row = []
        for x, (ca, cb) in enumerate(zip(a, b)):
            h = ((x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)) % 1000 / 1000
            row.append(cb if h < p - 0.15 else ("░" if h < p + 0.1 and (ca != " " or cb != " ") else ca))
        out.append("".join(row))
    return out


def scramble(old: list[str], new: list[str], p: float, seed: int, font=None, wide=False) -> list[str]:
    """Random digits flicker past before settling on the new one."""
    if p >= 0.8 or font is None:
        return new
    rng = random.Random(seed * 1000 + int(p * 12))
    return font.glyph(str(rng.randrange(10)), wide)


ANIMATIONS = {
    "roll": ("Roll", roll),
    "flip": ("Flip", flip),
    "drop": ("Drop", drop),
    "dissolve": ("Dissolve", dissolve),
    "scramble": ("Scramble", scramble),
    "none": ("None", None),
}

# --- widget ------------------------------------------------------------------------


class BigClock(Widget):
    """HH:MM:SS in a chosen font; each digit that changes animates to its new value."""

    DEFAULT_CSS = "BigClock { width: 100%; }"

    def __init__(self, font: str = "classic", animation: str = "roll", **kwargs) -> None:
        super().__init__(**kwargs)
        self.font_key = font if font in FONTS else "classic"
        self.animation_key = animation if animation in ANIMATIONS else "roll"
        self.value = "--:--:--"
        self._changes: dict[int, tuple[str, float]] = {}  # position -> (old char, start time)
        self.color: Color | None = None  # set by the beat flash; None = theme accent
        self._timer = None
        self._wide = True

    def on_mount(self) -> None:
        self._timer = self.set_interval(1 / FPS, self._frame, pause=True)
        self._apply_height()

    @property
    def font(self) -> Font:
        return FONTS[self.font_key]

    def set_font(self, key: str) -> None:
        self.font_key = key if key in FONTS else "classic"
        self._apply_height()
        self.refresh()

    def set_animation(self, key: str) -> None:
        self.animation_key = key if key in ANIMATIONS else "roll"

    def set_color(self, color: Color | None) -> None:
        if color != self.color:
            self.color = color
            self.refresh()

    def set_value(self, value: str) -> None:
        if value == self.value:
            return
        now = time.monotonic()
        if ANIMATIONS[self.animation_key][1] and len(value) == len(self.value):
            for i, (a, b) in enumerate(zip(self.value, value)):
                if a != b:
                    self._changes[i] = (a, now)
            if self._changes and self._timer:
                self._timer.resume()
        self.value = value
        self.refresh()

    def on_resize(self) -> None:
        self._apply_height()

    def _apply_height(self) -> None:
        # Use the wide version of pixel fonts when there's room for it
        wide_width = sum(len(self.font.glyph(c, True)[0]) + 1 for c in self.value.replace("-", "0")) + (len(self.font.glyph("0", True)) if self.font.slant else 0)
        self._wide = self.size.width == 0 or wide_width <= self.size.width
        rows = self.font.rows(self._wide)
        if self.styles.height is None or self.styles.height.value != rows:
            self.styles.height = rows

    def _frame(self) -> None:
        now = time.monotonic()
        self._changes = {i: c for i, c in self._changes.items() if now - c[1] < DURATION}
        if not self._changes and self._timer:
            self._timer.pause()
        self.refresh()

    def _glyph_at(self, index: int, char: str, now: float) -> list[str]:
        font, wide = self.font, self._wide
        new = font.glyph(char, wide)
        change = self._changes.get(index)
        if not change:
            return new
        old_char, start = change
        p = min(1.0, (now - start) / DURATION)
        old = font.glyph(old_char, wide)
        if len(old) != len(new) or len(old[0]) != len(new[0]):
            return new
        animate = ANIMATIONS[self.animation_key][1]
        if animate is scramble:
            return scramble(old, new, p, index, font, wide)
        return animate(old, new, p, index) if animate else new

    def _lines(self) -> list[str]:
        now = time.monotonic()
        glyphs = [self._glyph_at(i, c, now) for i, c in enumerate(self.value)]
        rows = max(len(g) for g in glyphs)
        lines = [" ".join(g[y] if y < len(g) else " " * len(g[0]) for g in glyphs) for y in range(rows)]
        return [line.translate(self.font.strokes) for line in _slant(lines)] if self.font.slant else lines

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        base = self.rich_style
        lines = self._lines()
        if y >= len(lines):
            return Strip.blank(width, base)
        line = lines[y]
        pad = max(0, (width - len(lines[0])) // 2)
        theme = self.app.current_theme
        color = self.color or Color.parse(theme.accent or theme.primary)
        on = base + Style(color=color, bold=True)
        background = Color.parse(theme.background or "#000000")
        faint = Color.from_rgb(*(b + (c - b) * 0.22 for c, b in zip(color.get_truecolor(), background.get_truecolor())))
        dim = base + Style(color=faint)
        segments = [Segment(" " * pad, base)]
        run, run_dim = "", False
        for ch in line:
            is_dim = ch in DIM_CHARS or ch == "░"
            if is_dim != run_dim and run:
                segments.append(Segment(run, dim if run_dim else on))
                run = ""
            run_dim = is_dim
            run += ch
        if run:
            segments.append(Segment(run, dim if run_dim else on))
        return Strip(segments).adjust_cell_length(width, base)
