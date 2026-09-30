"""A place to take prayer times from: a mosque (Mawaqit, my-masjid) or a city timetable (islam.nu)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

STOCKHOLM = (59.3293, 18.0686)
VAXJO = (56.8777, 14.8091)

PROVIDERS = {"mawaqit": "Mawaqit", "mymasjid": "my-masjid", "islamnu": "islam.nu"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Place:
    provider: str  # "mawaqit", "mymasjid" or "islamnu"
    slug: str
    name: str
    address: str = ""
    uuid: str = ""
    latitude: float | None = None
    longitude: float | None = None

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.slug}"

    @property
    def source(self) -> str:
        return PROVIDERS.get(self.provider, self.provider)

    @property
    def kind(self) -> str:
        return "City timetable" if self.provider == "islamnu" else "Mosque"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Place:
        data = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        data.setdefault("provider", "mawaqit")  # saved before islam.nu support
        return cls(**data)

    def distance_km(self, lat: float, lon: float) -> float | None:
        if self.latitude is None or self.longitude is None:
            return None
        return haversine_km(self.latitude, self.longitude, lat, lon)
