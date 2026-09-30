"""All timetable sources behind one interface."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from . import islamnu, mawaqit, mymasjid
from .mawaqit import MawaqitError as SourceError
from .place import STOCKHOLM, VAXJO, Place

REFRESH_AFTER = timedelta(days=7)

__all__ = ["SourceError", "fetch_timetable", "featured", "search", "needs_refresh"]


# Mosques that publish on my-masjid.com (it has no public search, so they're listed here)
VAXJO_MUSLIMER = Place(
    "mymasjid",
    "25709020-e669-46bc-b50e-65cc9ee7e8bd",
    "Växjö Muslimer — Växjö moské",
    "Försommarvägen 2, 352 37 Växjö",
    latitude=VAXJO[0],
    longitude=VAXJO[1],
)


def fetch_timetable(place: Place) -> dict:
    if place.provider == "islamnu":
        return islamnu.fetch_timetable(place.slug)
    if place.provider == "mymasjid":
        return mymasjid.fetch_timetable(place.slug)
    return mawaqit.fetch_timetable(place.slug)


def needs_refresh(data: dict, fetched_at: datetime) -> bool:
    now = datetime.now(timezone.utc)
    # islam.nu timetables are per year; Mawaqit's repeat every year
    if data.get("year") and data["year"] != now.astimezone().year:
        return True
    return now - fetched_at > REFRESH_AFTER


def _city(slug: str, name: str, at: tuple[float, float]) -> Place:
    return Place("islamnu", slug, name, "Sweden", latitude=at[0], longitude=at[1])


@lru_cache(maxsize=1)
def _cities() -> tuple[tuple[str, str], ...]:
    return tuple(islamnu.cities())


def featured() -> list[tuple[str, list[Place]]]:
    """Places for Stockholm and Växjö: the mosques we know publish there, plus the islam.nu city timetable."""
    sections = []
    errors = 0
    for title, slug, name, at, pinned in (
        ("Stockholm", "stockholm", "Stockholm", STOCKHOLM, []),
        ("Växjö", "vaexjoe", "Växjö", VAXJO, [VAXJO_MUSLIMER]),
    ):
        try:
            mosques = mawaqit.search_nearby(*at)
        except SourceError:
            mosques, errors = [], errors + 1
        sections.append((title, [*pinned, _city(slug, name, at), *mosques]))
    if errors == len(sections):
        raise SourceError("Couldn't reach Mawaqit — check your internet connection")
    return sections


def search(query: str) -> list[Place]:
    """Mosques and islam.nu cities matching a name or city."""
    results: list[Place] = [
        place for place in (VAXJO_MUSLIMER,) if islamnu.matches(f"{place.name} {place.address}", query)
    ]
    failures = []
    try:
        results += [
            Place("islamnu", slug, name, "Sweden")
            for slug, name in _cities()
            if islamnu.matches(name, query)
        ]
    except SourceError as error:
        failures.append(error)
    try:
        results += mawaqit.search_name(query)
    except SourceError as error:
        failures.append(error)
    if len(failures) == 2:
        raise failures[0]
    return results
