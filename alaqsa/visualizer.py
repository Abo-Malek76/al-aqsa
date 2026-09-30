"""cliamp-style beat visualizer for the countdown clock.

Two beat sources:
- PulseSource: the clock's own heartbeat — every second is a beat, stronger as the
  next prayer gets close. Costs nothing.
- MusicSource: listens to what's playing on the default audio output (PipeWire/Pulse
  monitor via `parec`) and turns it into frequency bands with beat detection, like
  cliamp's visualizers. Only runs while that mode is on; audio is analysed in memory
  and never stored.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import threading
import time

from rich.color import Color

BANDS = 32
RATE = 22050
CHUNK = 1024  # samples per analysis frame (~46 ms)

# Braille dot bits, indexed [row 0-3][column 0-1]
BRAILLE = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))


class PulseSource:
    """A synthetic beat on every second of the countdown."""

    def __init__(self) -> None:
        self.urgency = 0.0  # 0..1, set from the time left until the next prayer

    def read(self, now: float) -> tuple[list[float], float]:
        phase = now % 1.0
        beat = math.exp(-phase * 2.8)  # hit at the second, then a visible decay
        strength = 0.75 + 0.25 * self.urgency
        second = int(now)
        bands = []
        for i in range(BANDS):
            x = i / (BANDS - 1)
            # Kick-heavy shape plus slow shimmer; a per-second seed varies each hit
            seed = math.sin(second * 12.9898 + i * 4.1414) * 43758.5453
            jitter = 0.7 + 0.3 * (seed - math.floor(seed))
            hit = beat * strength * (1.0 - 0.4 * x) * jitter
            shimmer = 0.08 + 0.06 * math.sin(now * 2.1 + i * 0.55) + 0.04 * math.sin(now * 3.7 - i * 0.9)
            bands.append(min(1.0, max(0.0, hit + shimmer * (0.6 + 0.4 * strength))))
        return bands, beat * strength


class MusicSource:
    """Frequency bands and beats from the audio currently playing."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bands = [0.0] * BANDS
        self._beat = 0.0
        self._last_sound = 0.0
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self.error: str | None = None

    @staticmethod
    def available() -> bool:
        return shutil.which("parec") is not None

    def start(self) -> bool:
        if self._process:
            return True
        try:
            import numpy  # noqa: F401  (checked here so the app still runs without it)
        except ImportError:
            self.error = "numpy isn't installed"
            return False
        if not self.available():
            self.error = "parec (PipeWire/PulseAudio) isn't available"
            return False
        try:
            self._process = subprocess.Popen(
                ["parec", "-d", "@DEFAULT_MONITOR@", "--format=s16le", f"--rate={RATE}", "--channels=1", "--latency-msec=30"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except OSError as error:
            self.error = str(error)
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        process, self._process = self._process, None
        if process:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()

    @property
    def silent(self) -> bool:
        return time.monotonic() - self._last_sound > 2.0

    def read(self) -> tuple[list[float], float]:
        with self._lock:
            return list(self._bands), self._beat

    def _run(self) -> None:
        import numpy as np

        window = np.hanning(CHUNK)
        freqs = np.fft.rfftfreq(CHUNK, 1 / RATE)
        edges = np.geomspace(40, 10000, BANDS + 1)
        bins = [np.where((freqs >= lo) & (freqs < hi))[0] for lo, hi in zip(edges[:-1], edges[1:])]
        bins = [b if len(b) else np.array([np.argmin(abs(freqs - lo))]) for b, lo in zip(bins, edges[:-1])]
        smooth = np.zeros(BANDS)
        peak = 1e-3
        bass_avg = 0.0
        last_beat = 0.0
        beat = 0.0
        need = CHUNK * 2

        process = self._process
        while process and process.poll() is None and self._process is process:
            raw = process.stdout.read(need)
            if not raw or len(raw) < need:
                break
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            level = float(np.sqrt(np.mean(samples**2)))
            spectrum = np.abs(np.fft.rfft(samples * window))
            energy = np.array([spectrum[b].mean() for b in bins])
            energy = np.log1p(energy * 8.0)

            # Auto-gain: follow the loudest recent band, decaying slowly
            peak = max(peak * 0.995, float(energy.max()), 1e-3)
            target = np.clip(energy / peak, 0, 1)
            # Fast attack, slow release, like a VU meter
            smooth = np.where(target > smooth, target * 0.7 + smooth * 0.3, smooth * 0.82)

            now = time.monotonic()
            bass = float(target[: BANDS // 6].mean())
            bass_avg = bass_avg * 0.9 + bass * 0.1
            if bass > bass_avg * 1.35 and bass > 0.35 and now - last_beat > 0.18:
                beat, last_beat = 1.0, now
            else:
                beat *= 0.8

            with self._lock:
                self._bands = smooth.tolist()
                self._beat = beat
                if level > 0.004:
                    self._last_sound = now


def gradient(colors: list[str], steps: int) -> list[Color]:
    """Evenly blend a list of hex colors across `steps` positions."""
    parsed = [Color.parse(c).get_truecolor() for c in colors]
    out = []
    for i in range(max(1, steps)):
        pos = i / max(1, steps - 1) * (len(parsed) - 1)
        a, b = parsed[int(pos)], parsed[min(len(parsed) - 1, int(pos) + 1)]
        t = pos - int(pos)
        out.append(Color.from_rgb(*(a[k] + (b[k] - a[k]) * t for k in range(3))))
    return out


class PeakHold:
    """Peak caps that hang above the bars and slowly fall, like Winamp/cliamp."""

    def __init__(self, fall: float = 0.025) -> None:
        self.fall = fall
        self.peaks = [0.0] * BANDS

    def update(self, bands: list[float]) -> list[float]:
        self.peaks = [max(b, p - self.fall) for b, p in zip(bands, self.peaks)]
        return self.peaks


def _spread(values: list[float], columns: int, dot_rows: int) -> list[int]:
    """Values per dot column, symmetric around the centre (bass in the middle) like cliamp's mirror."""
    heights = []
    for x in range(columns):
        pos = abs(x - (columns - 1) / 2) / ((columns - 1) / 2 or 1) * (len(values) - 1)
        lo = int(pos)
        hi = min(len(values) - 1, lo + 1)
        heights.append(round((values[lo] + (values[hi] - values[lo]) * (pos - lo)) * dot_rows))
    return heights


def render_bars(
    bands: list[float],
    rows: int,
    column_colors: list[int],
    mirror: bool = False,
    peaks: list[float] | None = None,
) -> list[list[tuple[str, int]]]:
    """Spectrum bars in braille, growing up (or down for the reflection).

    Returns each row as runs of (characters, colour index), one colour index per
    column from `column_colors`. Runs keep the number of styled pieces small, which
    is what makes redrawing this many times a second cheap.
    """
    width = len(column_colors)
    dot_rows = rows * 4
    columns = width * 2
    heights = _spread(bands, columns, dot_rows)
    caps = _spread(peaks, columns, dot_rows) if peaks else [0] * columns

    lines = []
    for row in range(rows):
        runs: list[tuple[str, int]] = []
        chars: list[str] = []
        current = column_colors[0] if width else 0
        for col in range(width):
            cell = 0x2800
            for dr in range(4):
                y = row * 4 + dr
                level = y + 1 if mirror else dot_rows - y  # 1 = the row nearest the clock
                for dc in range(2):
                    x = col * 2 + dc
                    if heights[x] >= level or (caps[x] == level and caps[x] > heights[x] + 1):
                        cell |= BRAILLE[dr][dc]
            if column_colors[col] != current:
                runs.append(("".join(chars), current))
                chars, current = [], column_colors[col]
            chars.append(chr(cell))
        runs.append(("".join(chars), current))
        lines.append(runs)
    return lines
