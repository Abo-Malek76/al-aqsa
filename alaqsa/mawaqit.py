"""Client for Mawaqit (mawaqit.net), the platform mosques use to publish their own prayer times.

Mosques are found with the public search API. A mosque's full yearly timetable
comes from the `confData` block on its public Mawaqit page — the same data
Mawaqit's own screens and widgets use.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .place import STOCKHOLM, Place

BASE_URL = "https://mawaqit.net"
USER_AGENT = "al-aqsa/1.0 (prayer times app)"
TIMEOUT = 15

NEARBY_RADIUS_KM = 70


class MawaqitError(Exception):
    """Raised when a timetable source can't be reached or returns unusable data."""


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise MawaqitError(f"Couldn't reach Mawaqit ({error})") from error


def _search(params: dict) -> list[Place]:
    url = f"{BASE_URL}/api/2.0/mosque/search?{urllib.parse.urlencode(params)}"
    try:
        results = json.loads(_get(url))
    except json.JSONDecodeError as error:
        raise MawaqitError("Mawaqit returned an invalid search response") from error

    mosques = []
    for item in results:
        try:
            mosques.append(
                Place(
                    provider="mawaqit",
                    uuid=item["uuid"],
                    slug=item["slug"],
                    name=(item.get("name") or item.get("label") or item["slug"]).strip(),
                    address=(item.get("localisation") or "").strip(),
                    latitude=float(item["latitude"]),
                    longitude=float(item["longitude"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return mosques


def search_nearby(lat: float = STOCKHOLM[0], lon: float = STOCKHOLM[1]) -> list[Place]:
    """Mosques around a point, nearest first.

    Mawaqit only returns a handful of results per query, so a few points around
    the centre are searched and merged.
    """
    found: dict[str, Place] = {}
    errors = 0
    offsets = [(0, 0), (0.15, 0), (-0.15, 0), (0, 0.3), (0, -0.3)]
    for dlat, dlon in offsets:
        try:
            for mosque in _search({"lat": lat + dlat, "lon": lon + dlon}):
                found[mosque.uuid] = mosque
        except MawaqitError:
            errors += 1
    if errors == len(offsets):
        raise MawaqitError("Couldn't reach Mawaqit — check your internet connection")

    nearby = [m for m in found.values() if m.distance_km(lat, lon) <= NEARBY_RADIUS_KM]
    return sorted(nearby, key=lambda m: m.distance_km(lat, lon))


def search_name(query: str) -> list[Place]:
    """Search all Mawaqit mosques by name or city."""
    return _search({"word": query.strip()})


def fetch_timetable(slug: str) -> dict:
    """The mosque's yearly timetable and details, as published on its Mawaqit page."""
    page = _get(f"{BASE_URL}/en/{urllib.parse.quote(slug)}").decode("utf-8", "replace")

    marker = page.find("confData =")
    if marker == -1:
        raise MawaqitError("This mosque's page has no timetable")
    start = page.find("{", marker)
    try:
        conf, _ = json.JSONDecoder().raw_decode(page, start)
    except json.JSONDecodeError as error:
        raise MawaqitError("Couldn't read this mosque's timetable") from error

    calendar = conf.get("calendar")
    if not isinstance(calendar, list) or len(calendar) != 12 or not all(calendar):
        raise MawaqitError("This mosque hasn't published a full yearly timetable")

    iqama_calendar = conf.get("iqamaCalendar")
    return {
        "name": conf.get("name") or conf.get("label"),
        "timezone": conf.get("timezone") or "Europe/Stockholm",
        "calendar": calendar,
        "iqama_calendar": iqama_calendar if conf.get("iqamaEnabled", True) else None,
        "jumua": conf.get("jumua"),
        "hijri_adjustment": conf.get("hijriAdjustment") or 0,
    }
