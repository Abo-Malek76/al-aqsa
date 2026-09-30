"""Timetables from islam.nu, which publishes monthly prayer times for Swedish cities.

Each month is a public page (https://islam.nu/bonetider/<city>/<year>/<month>/)
with a table of Fajr, Shuruq, Dhuhr, Asr, Maghrib and Isha.
"""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import date

from .mawaqit import MawaqitError as SourceError  # shared "couldn't fetch" error
from .mawaqit import _get

BASE_URL = "https://islam.nu/bonetider"

_TIME = re.compile(r"^\d{1,2}:\d{2}$")


def _fold(text: str) -> str:
    """Lowercase without accents, for matching 'vaxjo' to 'Växjö'."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


def cities() -> list[tuple[str, str]]:
    """All cities islam.nu publishes times for, as (slug, name)."""
    page = _get(f"{BASE_URL}/stockholm/").decode("utf-8", "replace")
    found = {
        slug: html.unescape(name).strip()
        for slug, name in re.findall(r'href="(?:https://islam\.nu)?/bonetider/([a-z0-9-]+)/"[^>]*>\s*([^<]+?)\s*<', page)
    }
    if not found:
        raise SourceError("Couldn't read the city list from islam.nu")
    return sorted(found.items(), key=lambda item: _fold(item[1]))


def matches(name: str, query: str) -> bool:
    return _fold(query.strip()) in _fold(name)


def _month(slug: str, year: int, month: int) -> dict[str, list[str]]:
    page = _get(f"{BASE_URL}/{slug}/{year}/{month}/").decode("utf-8", "replace")
    body = page[page.find("<tbody") : page.find("</tbody>")]
    days: dict[str, list[str]] = {}
    for row in re.findall(r"<tr.*?</tr>", body, re.S):
        cells = [c.strip() for c in re.findall(r"<td[^>]*>\s*([^<]*?)\s*</td>", row)]
        if len(cells) >= 7 and cells[0].isdigit() and all(_TIME.match(c) for c in cells[1:7]):
            days[str(int(cells[0]))] = cells[1:7]
    return days


def fetch_timetable(slug: str, year: int | None = None) -> dict:
    """A full year of times for a city, in the same shape as a Mawaqit timetable."""
    year = year or date.today().year
    calendar = [_month(slug, year, month) for month in range(1, 13)]
    if not all(calendar):
        raise SourceError("islam.nu didn't return a full year of times for this city")
    return {
        "timezone": "Europe/Stockholm",
        "calendar": calendar,
        "iqama_calendar": None,
        "jumua": None,
        "hijri_adjustment": 0,
        "year": year,
    }
