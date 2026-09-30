"""Themes: follow the active Omarchy theme, use any installed Omarchy theme, or a built-in Textual one."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from textual.theme import BUILTIN_THEMES, Theme

SYSTEM = "system"
CURRENT_COLORS = Path.home() / ".local/state/omarchy/current/theme/colors.toml"
THEME_DIRS = (
    Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "themes",
    Path.home() / ".config/omarchy/themes",
)


def from_colors(name: str, path: Path) -> Theme | None:
    """A Textual theme from an Omarchy colors.toml."""
    try:
        c = tomllib.loads(path.read_text())
        accent = c["accent"]
        return Theme(
            name=name,
            primary=accent,
            secondary=c.get("magenta", accent),
            accent=c.get("cyan", accent),
            foreground=c["foreground"],
            background=c["background"],
            surface=c.get("lighter_background", c["background"]),
            panel=c.get("lighter_background", c["background"]),
            success=c.get("green"),
            warning=c.get("yellow"),
            error=c.get("red"),
            dark=c.get("mode", "dark") != "light",
        )
    except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError):
        return None


def system_theme() -> Theme | None:
    return from_colors(SYSTEM, CURRENT_COLORS)


def system_stamp() -> float | None:
    """Changes whenever Omarchy switches theme."""
    try:
        return CURRENT_COLORS.stat().st_mtime
    except OSError:
        return None


def omarchy_themes() -> list[tuple[str, str, Path]]:
    """Installed Omarchy themes as (theme name, label, colors.toml); user themes override stock ones."""
    found: dict[str, Path] = {}
    for directory in THEME_DIRS:
        if directory.is_dir():
            for colors in directory.glob("*/colors.toml"):
                found[colors.parent.name] = colors
    return [
        (f"omarchy-{slug}", slug.replace("-", " ").replace("_", " ").title(), path)
        for slug, path in sorted(found.items())
    ]


def textual_themes() -> list[tuple[str, str]]:
    return [(name, name.replace("-", " ").title()) for name in sorted(BUILTIN_THEMES) if name != "textual-ansi"]
