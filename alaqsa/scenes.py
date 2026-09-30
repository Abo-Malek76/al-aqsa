"""Ambient scenes drawn around the countdown clock, in braille dots (2×4 per character).

The canvas is the strip above the clock plus the strip below it, stacked: the clock
itself hides the space in between. Every scene is a pure function of time, so it
costs nothing between frames.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .visualizer import BRAILLE


def _h(i: int, salt: int = 0) -> float:
    """Stable pseudo-random number in [0, 1) for particle i."""
    n = (i * 2654435761 + salt * 40503 + 12345) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return (n ^ (n >> 16)) / 0x100000000


@dataclass
class Sky:
    """Where the sun (or moon) is: `progress` 0..1 across the day (sunrise→maghrib) or night."""

    day: bool = True
    progress: float = 0.5


class Canvas:
    def __init__(self, width: int, top_rows: int, bottom_rows: int) -> None:
        self.cells = width
        self.w = width * 2
        self.top = top_rows * 4  # dot rows above the clock
        self.h = (top_rows + bottom_rows) * 4
        self.dots: dict[tuple[int, int], int] = {}

    def dot(self, x: float, y: float, color: int) -> None:
        xi, yi = int(x), int(y)
        if 0 <= xi < self.w and 0 <= yi < self.h:
            key = (xi, yi)
            if self.dots.get(key, -1) < color:
                self.dots[key] = color

    def lines(self, first_row: int, last_row: int) -> list[list[tuple[str, int]]]:
        """Character rows [first_row, last_row) as runs of (characters, colour index)."""
        cells: dict[tuple[int, int], list[int]] = {}
        for (x, y), color in self.dots.items():
            key = (x // 2, y // 4)
            cell = cells.setdefault(key, [0x2800, -1])
            cell[0] |= BRAILLE[y % 4][x % 2]
            cell[1] = max(cell[1], color)
        out = []
        for row in range(first_row, last_row):
            runs: list[tuple[str, int]] = []
            chars: list[str] = []
            current = 0
            for col in range(self.cells):
                cell = cells.get((col, row))
                if cell is None:
                    chars.append("⠀")  # blank keeps the current run going
                    continue
                if cell[1] != current and chars:
                    runs.append(("".join(chars), current))
                    chars = []
                current = cell[1]
                chars.append(chr(cell[0]))
            runs.append(("".join(chars), current))
            out.append(runs)
        return out


# --- scenes: each draws on the canvas for time t (seconds) ----------------------------


def fireflies(c: Canvas, t: float, sky: Sky) -> None:
    for i in range(max(10, c.w // 7)):
        fx, fy = 0.15 + _h(i, 1) * 0.25, 0.2 + _h(i, 2) * 0.3
        x = (0.5 + 0.48 * math.cos(t * fx + _h(i, 3) * 6.28)) * (c.w - 1)
        y = (0.5 + 0.46 * math.sin(t * fy + _h(i, 4) * 6.28)) * (c.h - 1)
        if math.sin(t * (1.5 + _h(i, 5) * 2) + i * 1.31) > 0.1:
            c.dot(x, y, 2)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                c.dot(x + dx, y + dy, 1)
        else:
            c.dot(x, y, 0)


def stars(c: Canvas, t: float, sky: Sky) -> None:
    for i in range(c.w * c.h // 45):
        x, y = _h(i, 1) * c.w, _h(i, 2) * c.h
        glow = math.sin(t * (0.6 + _h(i, 3) * 2.2) + _h(i, 4) * 6.28)
        if glow > 0.55:
            c.dot(x, y, 2)
        elif glow > -0.3:
            c.dot(x, y, 0)
    # A shooting star every few seconds
    period = 7.0
    n = int(t // period)
    p = (t % period) / 1.1
    if p < 1:
        x0, y0 = _h(n, 7) * c.w * 0.6 + c.w * 0.2, _h(n, 8) * c.top * 0.6
        for k in range(10):
            q = p - k * 0.025
            if 0 <= q <= 1:
                c.dot(x0 + q * c.w * 0.35, y0 + q * c.h * 0.5, 2 if k < 2 else 1)


def rain(c: Canvas, t: float, sky: Sky) -> None:
    span = c.h + 8
    for i in range(max(12, c.w // 3)):
        speed = 26 + _h(i, 1) * 18
        y = (t * speed + _h(i, 2) * span) % span - 4
        x = _h(i, 3) * (c.w + 10) - y * 0.35
        for k in range(3):
            c.dot(x + k * 0.35, y - k, 1 if k == 0 else 0)
        if y >= c.h - 2:  # splash on the ground
            c.dot(x - 1, c.h - 1, 2)
            c.dot(x + 1, c.h - 1, 2)


def snow(c: Canvas, t: float, sky: Sky) -> None:
    span = c.h + 4
    for i in range(max(10, c.w // 4)):
        speed = 3 + _h(i, 1) * 5
        y = (t * speed + _h(i, 2) * span) % span - 2
        x = _h(i, 3) * c.w + math.sin(t * (0.5 + _h(i, 4)) + i) * 3
        c.dot(x, y, 2 if _h(i, 5) > 0.6 else 1)
        if _h(i, 6) > 0.75:
            c.dot(x + 1, y, 1)


def waves(c: Canvas, t: float, sky: Sky) -> None:
    regions = ((0, c.top), (c.top, c.h))
    for layer, (y0, y1) in enumerate(regions):
        mid = (y0 + y1) / 2
        amp = (y1 - y0) * 0.3
        for x in range(c.w):
            y = mid + math.sin(x * 0.06 + t * 1.4 + layer) * amp + math.sin(x * 0.021 - t * 0.8) * amp * 0.6
            c.dot(x, y, 2)
            c.dot(x, y + 1, 1)
            # Water below the crest, sparser further down
            for d in range(2, int(y1 - y)):
                if _h(x * 31 + d, int(t * 3)) < 0.18 / d:
                    c.dot(x, y + d, 0)
            if _h(x, int(t * 6)) > 0.97:  # foam
                c.dot(x, y - 1, 2)


def aurora(c: Canvas, t: float, sky: Sky) -> None:
    for x in range(c.w):
        base = c.h * 0.35 + math.sin(x * 0.045 + t * 0.6) * c.h * 0.18 + math.sin(x * 0.012 - t * 0.35) * c.h * 0.12
        length = c.h * (0.25 + 0.2 * (1 + math.sin(x * 0.08 - t * 1.1)) / 2)
        color = int((math.sin(x * 0.02 + t * 0.3) + 1) * 1.5)  # drifting colours: 0..3
        for d in range(int(length)):
            if _h(x * 97 + d, int(t * 8)) < 0.85 - d / length * 0.7:
                c.dot(x, base + d, color if d < length * 0.6 else 0)
    for i in range(c.w // 10):  # a few stars behind it
        if math.sin(t * 1.3 + i) > 0.3:
            c.dot(_h(i, 1) * c.w, _h(i, 2) * c.top * 0.5, 3)


def matrix(c: Canvas, t: float, sky: Sky) -> None:
    span = c.h + 14
    for col in range(0, c.w, 3):
        if _h(col, 9) < 0.35:
            continue
        speed = 10 + _h(col, 1) * 16
        head = (t * speed + _h(col, 2) * span) % span
        for k in range(12):
            y = head - k
            if _h(col * 13 + int(y), int(t * 4)) > 0.25:
                c.dot(col, y, 2 if k == 0 else (1 if k < 5 else 0))


def sky_arc(c: Canvas, t: float, sky: Sky) -> None:
    """The sun's real position between sunrise and maghrib; at night the moon and stars."""
    top = c.top
    for i in range(c.w * c.h // 90 if not sky.day else 0):  # night stars
        if math.sin(t * (0.5 + _h(i, 3)) + i) > 0:
            c.dot(_h(i, 1) * c.w, _h(i, 2) * c.h, 0)
    # The arc path, dotted
    for x in range(0, c.w, 4):
        p = x / (c.w - 1)
        c.dot(x, top - 1 - math.sin(p * math.pi) * (top - 3), 0)
    p = min(1.0, max(0.0, sky.progress))
    cx = p * (c.w - 1)
    cy = top - 1 - math.sin(p * math.pi) * (top - 3)
    if sky.day:
        for dy in range(-2, 3):
            for dx in range(-3, 4):
                if dx * dx / 9 + dy * dy / 4 <= 1:
                    c.dot(cx + dx, cy + dy, 3)
        for k in range(8):  # rays
            a = k * math.pi / 4 + t * 0.4
            r = 5 + math.sin(t * 3 + k) * 0.8
            c.dot(cx + math.cos(a) * r * 1.4, cy + math.sin(a) * r * 0.7, 2)
    else:
        for dy in range(-2, 3):
            for dx in range(-3, 4):
                inside = dx * dx / 9 + dy * dy / 4 <= 1
                shadow = (dx - 1.5) ** 2 / 9 + dy * dy / 4 <= 0.8
                if inside and not shadow:
                    c.dot(cx + dx, cy + dy, 3)
    # Horizon below the clock, with gentle hills
    for x in range(c.w):
        y = c.h - 2 - (math.sin(x * 0.05) + 1) * 1.2
        c.dot(x, y, 1)
        c.dot(x, c.h - 1, 1)


# name: (label, draw, palette roles from darkest to brightest)
SCENES = {
    "fireflies": ("Fireflies", fireflies, ("success", "warning", "warning")),
    "stars": ("Night sky", stars, ("text-muted", "foreground", "accent")),
    "rain": ("Rain", rain, ("primary", "accent", "foreground")),
    "snow": ("Snow", snow, ("text-muted", "foreground", "foreground")),
    "waves": ("Waves", waves, ("primary", "accent", "foreground")),
    "aurora": ("Aurora", aurora, ("success", "accent", "secondary", "foreground")),
    "matrix": ("Matrix", matrix, ("success", "success", "foreground")),
    "sky": ("Sky", sky_arc, ("text-muted", "accent", "warning", "warning")),
}
