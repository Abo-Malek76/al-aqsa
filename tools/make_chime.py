"""Generate alaqsa/assets/chime.wav: a soft three-note bell arpeggio for prayer notifications."""

import wave
from pathlib import Path

import numpy as np

RATE = 44100
OUT = Path(__file__).resolve().parent.parent / "alaqsa/assets/chime.wav"

# (start seconds, frequency Hz, loudness): G major rising, with a quiet high sparkle at the end
NOTES = [(0.00, 783.99, 1.0), (0.13, 987.77, 0.85), (0.26, 1174.66, 0.8), (0.46, 1567.98, 0.35)]
# Bell-ish partials: (ratio, level, decay seconds)
PARTIALS = [(1.0, 1.0, 0.9), (2.0, 0.28, 0.45), (3.01, 0.09, 0.25), (4.17, 0.05, 0.15)]

length = 2.6
t = np.arange(int(RATE * length)) / RATE
signal = np.zeros_like(t)
for start, freq, level in NOTES:
    n = t - start
    on = n >= 0
    attack = 1 - np.exp(-np.clip(n, 0, None) / 0.004)
    for ratio, amp, decay in PARTIALS:
        tone = np.sin(2 * np.pi * freq * ratio * n) * amp * np.exp(-np.clip(n, 0, None) / decay)
        signal += np.where(on, tone * attack * level, 0)

# A little room: a few soft echoes
room = signal.copy()
for delay, gain in ((0.043, 0.22), (0.067, 0.16), (0.091, 0.11), (0.127, 0.07)):
    shift = int(delay * RATE)
    room[shift:] += signal[:-shift] * gain
signal = room

fade = np.clip((length - t) / 0.4, 0, 1)
signal *= fade
signal = signal / np.abs(signal).max() * 0.45  # comfortable, not loud

OUT.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(OUT), "wb") as f:
    f.setnchannels(1)
    f.setsampwidth(2)
    f.setframerate(RATE)
    f.writeframes((signal * 32767).astype("<i2").tobytes())
print(f"wrote {OUT} ({length}s)")
