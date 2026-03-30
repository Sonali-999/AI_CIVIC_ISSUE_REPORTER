# location_service.py
"""
Location service for CivicAI.

Key features:
  1. Reverse-geocodes (lat, lon) → address + district via Nominatim (OSM)
  2. Extracts GPS EXIF from JPEG/PNG images as a secondary source
  3. CHENNAI DISTRICT BOUNDING BOXES — every official GCC zone is mapped to
     (lat_min, lat_max, lon_min, lon_max).
     coordinate_to_chennai_district(lat, lon) returns the zone name or None.
"""

from __future__ import annotations
import re
from typing import Optional

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError
    _GEOPY_OK = True
except ImportError:
    _GEOPY_OK = False
    print("[location_service] geopy not installed — install with: pip install geopy")

try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


# ─────────────────────────────────────────────────────────────────────────────
# CHENNAI GCC ZONE BOUNDING BOXES
#
# 15 administrative zones of the Greater Chennai Corporation.
# Each entry: "Zone Name": (lat_min, lat_max, lon_min, lon_max)
# ─────────────────────────────────────────────────────────────────────────────

CHENNAI_DISTRICTS: dict[str, tuple[float, float, float, float]] = {
    "Thiruvottiyur":     (13.1500, 13.2500, 80.2800, 80.3200),
    "Manali":            (13.1650, 13.2200, 80.2300, 80.2900),
    "Madhavaram":        (13.1450, 13.2000, 80.2100, 80.2700),
    "Tondiarpet":        (13.1100, 13.1600, 80.2700, 80.3100),
    "Royapuram":         (13.0950, 13.1350, 80.2850, 80.3100),
    "Thiru Vi Ka Nagar": (13.0900, 13.1300, 80.2550, 80.2950),
    "Ambattur":          (13.0800, 13.1500, 80.1400, 80.2200),
    "Anna Nagar":        (13.0700, 13.1100, 80.2050, 80.2500),
    "Teynampet":         (13.0350, 13.0750, 80.2400, 80.2850),
    "Kodambakkam":       (13.0400, 13.0800, 80.2000, 80.2450),
    "Valasaravakkam":    (13.0300, 13.0800, 80.1500, 80.2100),
    "Alandur":           (12.9900, 13.0450, 80.1950, 80.2500),
    "Adyar":             (12.9750, 13.0350, 80.2400, 80.2800),
    "Perungudi":         (12.9400, 13.0000, 80.2350, 80.2800),
    "Sholinganallur":    (12.8850, 12.9550, 80.2200, 80.2800),
}

CHENNAI_DISTRICT_NAMES: list[str] = sorted(CHENNAI_DISTRICTS.keys())

# Outer bounding box of all Chennai zones (quick pre-filter)
_CHENNAI_LAT_MIN = 12.88
_CHENNAI_LAT_MAX = 13.25
_CHENNAI_LON_MIN = 80.05
_CHENNAI_LON_MAX = 80.33


def coordinate_to_chennai_district(lat: float, lon: float) -> Optional[str]:
    """Return the GCC zone that contains (lat, lon), or None if outside Chennai."""
    if not (_CHENNAI_LAT_MIN <= lat <= _CHENNAI_LAT_MAX and
            _CHENNAI_LON_MIN <= lon <= _CHENNAI_LON_MAX):
        return None
    for name, (lat_min, lat_max, lon_min, lon_max) in CHENNAI_DISTRICTS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return None


def is_in_chennai_district(lat: Optional[float], lon: Optional[float],
                            district_name: str) -> bool:
    """Return True if (lat, lon) falls inside the named Chennai district bbox."""
    if lat is None or lon is None:
        return False
    bbox = CHENNAI_DISTRICTS.get(district_name)
    if not bbox:
        return False
    lat_min, lat_max, lon_min, lon_max = bbox
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


# ─────────────────────────────────────────────────────────────────────────────
# Nominatim reverse-geocoder
# ─────────────────────────────────────────────────────────────────────────────

_geolocator = Nominatim(user_agent="civicai_platform/1.0") if _GEOPY_OK else None


def reverse_geocode(lat: float, lon: float) -> dict:
    """Convert (lat, lon) → address + district.  Uses bounding-box lookup for
    Chennai zones; falls back to Nominatim admin fields elsewhere."""
    chennai_zone = coordinate_to_chennai_district(lat, lon)

    if not _GEOPY_OK or _geolocator is None:
        return {"address": "", "district": chennai_zone or "", "raw": None}

    try:
        location = _geolocator.reverse((lat, lon), exactly_one=True,
                                       language="en", timeout=10)
        if not location:
            return {"address": "", "district": chennai_zone or "", "raw": None}

        raw_addr = location.raw.get("address", {})

        if chennai_zone:
            district = chennai_zone
        else:
            district = (
                raw_addr.get("county")
                or raw_addr.get("state_district")
                or raw_addr.get("city_district")
                or raw_addr.get("city")
                or raw_addr.get("town")
                or raw_addr.get("village")
                or ""
            )
            district = re.sub(r"\s*district\s*$", "", district, flags=re.IGNORECASE).strip()

        return {"address": location.address or "", "district": district, "raw": location.raw}

    except (GeocoderTimedOut, GeocoderServiceError) as e:
        print(f"[location_service] Geocoder error: {e}")
        return {"address": "", "district": chennai_zone or "", "raw": None}
    except Exception as e:
        print(f"[location_service] Unexpected error: {e}")
        return {"address": "", "district": chennai_zone or "", "raw": None}


# ─────────────────────────────────────────────────────────────────────────────
# EXIF GPS extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_exif_gps(image_path: str) -> Optional[tuple[float, float]]:
    if not _PIL_OK:
        return None
    try:
        img = Image.open(image_path)
        exif_data = img._getexif()
        if not exif_data:
            return None
        tagged = {TAGS.get(k, k): v for k, v in exif_data.items()}
        gps_info_raw = tagged.get("GPSInfo")
        if not gps_info_raw:
            return None
        gps = {GPSTAGS.get(k, k): v for k, v in gps_info_raw.items()}

        def _dms_to_dd(dms, ref):
            d, m, s = [float(x) for x in dms]
            dd = d + m / 60 + s / 3600
            if ref in ("S", "W"):
                dd = -dd
            return dd

        lat = _dms_to_dd(gps["GPSLatitude"],  gps["GPSLatitudeRef"])
        lon = _dms_to_dd(gps["GPSLongitude"], gps["GPSLongitudeRef"])
        return lat, lon
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Unified entry point
# ─────────────────────────────────────────────────────────────────────────────

def get_location_from_image_or_coords(
    image_path: str,
    lat: Optional[float],
    lon: Optional[float],
) -> dict:
    """Priority: browser coords → EXIF GPS → nothing."""
    if lat is not None and lon is not None:
        geo = reverse_geocode(lat, lon)
        return {**geo, "latitude": lat, "longitude": lon, "source": "browser"}

    if image_path:
        coords = extract_exif_gps(image_path)
        if coords:
            elat, elon = coords
            geo = reverse_geocode(elat, elon)
            return {**geo, "latitude": elat, "longitude": elon, "source": "exif"}

    return {"address": "", "district": "", "latitude": None,
            "longitude": None, "raw": None, "source": "none"}