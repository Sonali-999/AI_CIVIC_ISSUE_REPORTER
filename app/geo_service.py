"""
geo_service.py
--------------
Geospatial routing: GPS coordinates -> validated municipal location.

Implements Module 5 of the CivicAI design:

  * Haversine range validation (Eq. 4) - a coordinate pair is accepted only if
    it lies within a plausible great-circle distance of the municipal boundary
    centroid. This rejects spoofed or mistyped coordinates before they reach
    the database.

  * Nominatim reverse geocoding - turns the accepted coordinates into a
    human-readable address and administrative district, so a complaint is
    routed to the right ward without the citizen selecting one manually.

NOMINATIM USAGE POLICY
======================
OpenStreetMap's public Nominatim instance requires an identifying User-Agent
and permits at most one request per second. Both are enforced here. Results are
cached in-process because multiple complaints from one street resolve to the
same address, and re-requesting it would waste the rate-limit budget.
"""

from __future__ import annotations

import math
import os
import threading
import time

import requests
from dotenv import load_dotenv

load_dotenv()

# ── Municipal boundary (Eq. 4 reference point) ───────────────────────────────
# Defaults to Chennai. Override in .env for another municipality.
MUNICIPAL_LAT    = float(os.getenv("MUNICIPAL_LAT", "13.0827"))
MUNICIPAL_LON    = float(os.getenv("MUNICIPAL_LON", "80.2707"))
# Generous by default so testing from outside the city still works; tighten it
# for a real deployment to reject out-of-jurisdiction reports.
MUNICIPAL_RADIUS_KM = float(os.getenv("MUNICIPAL_RADIUS_KM", "150"))
ENFORCE_BOUNDARY = os.getenv("ENFORCE_BOUNDARY", "false").lower() == "true"

EARTH_RADIUS_KM = 6371.0088

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = os.getenv("NOMINATIM_USER_AGENT", "CivicAI/1.0 (civic issue reporter)")
REQUEST_TIMEOUT = 8

_rate_lock = threading.Lock()
_last_request_at = 0.0
_cache: dict[tuple[float, float], dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Eq. 4 - Haversine great-circle distance
# ─────────────────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance in kilometres between two coordinate pairs.

        d = 2r * arcsin( sqrt( sin^2(dphi/2)
                               + cos(phi1) cos(phi2) sin^2(dlambda/2) ) )
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    h = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def validate_coordinates(lat: float, lon: float) -> dict:
    """
    Range-validate a coordinate pair before it is trusted.

    Two checks: the pair must be a physically possible coordinate, and it must
    fall within MUNICIPAL_RADIUS_KM of the municipal centroid.

    Returns {"valid": bool, "distance_km": float, "reason": str}. When
    ENFORCE_BOUNDARY is false an out-of-range pair is still marked valid but
    carries a reason, so testing away from the city is not blocked.
    """
    if lat is None or lon is None:
        return {"valid": False, "distance_km": None, "reason": "No coordinates provided"}

    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return {"valid": False, "distance_km": None, "reason": "Coordinates are not numeric"}

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return {"valid": False, "distance_km": None,
                "reason": f"Coordinates out of range: {lat}, {lon}"}

    distance = haversine_km(MUNICIPAL_LAT, MUNICIPAL_LON, lat, lon)

    if distance > MUNICIPAL_RADIUS_KM:
        reason = (f"{distance:.0f} km from the municipal centroid "
                  f"(limit {MUNICIPAL_RADIUS_KM:.0f} km)")
        return {"valid": not ENFORCE_BOUNDARY, "distance_km": distance, "reason": reason}

    return {"valid": True, "distance_km": distance, "reason": "Within municipal boundary"}


# ─────────────────────────────────────────────────────────────────────────────
# Nominatim reverse geocoding
# ─────────────────────────────────────────────────────────────────────────────

def _respect_rate_limit() -> None:
    """Block until at least one second has passed since the previous request."""
    global _last_request_at
    with _rate_lock:
        elapsed = time.time() - _last_request_at
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        _last_request_at = time.time()


def reverse_geocode(lat: float, lon: float) -> dict:
    """
    Resolve coordinates to an address and administrative district.

    Returns {"address", "district", "city", "state", "postcode", "error"}.
    Never raises: a geocoding outage must not block a citizen from filing a
    complaint, so on failure the address falls back to the raw coordinates.
    """
    fallback = {
        "address": f"{lat:.5f}, {lon:.5f}",
        "district": "", "city": "", "state": "", "postcode": "", "error": "",
    }

    key = (round(float(lat), 5), round(float(lon), 5))
    if key in _cache:
        return dict(_cache[key])

    try:
        _respect_rate_limit()
        response = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18,
                    "addressdetails": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:                      # network, timeout, bad JSON
        fallback["error"] = f"Reverse geocoding unavailable ({exc.__class__.__name__})"
        return fallback

    if "error" in payload:
        fallback["error"] = str(payload["error"])
        return fallback

    addr = payload.get("address", {})
    result = {
        "address": payload.get("display_name") or fallback["address"],
        # Nominatim's administrative level varies by country, so fall back
        # through the plausible keys rather than assuming one exists.
        "district": (addr.get("suburb") or addr.get("city_district")
                     or addr.get("county") or addr.get("state_district") or ""),
        "city": (addr.get("city") or addr.get("town")
                 or addr.get("village") or addr.get("municipality") or ""),
        "state": addr.get("state", ""),
        "postcode": addr.get("postcode", ""),
        "error": "",
    }

    _cache[key] = dict(result)
    return result


def resolve_location(lat, lon, manual_address: str | None = None) -> dict:
    """
    Turn whatever location evidence is available into one location record.

    Precedence: valid GPS coordinates are reverse-geocoded; otherwise a manually
    typed address is used. A manual address is always kept alongside GPS when
    both are given, since the citizen may be adding a landmark the map lacks.

    Returns a dict ready to store on the complaint document.
    """
    manual = (manual_address or "").strip()

    has_coords = lat is not None and lon is not None and str(lat) != "" and str(lon) != ""
    if not has_coords:
        if manual:
            return {
                "latitude": None, "longitude": None,
                "address": manual, "district": "", "city": "", "state": "",
                "postcode": "", "source": "manual", "verified": False,
                "distance_km": None, "note": "Location typed by citizen; not GPS-verified",
            }
        return {
            "latitude": None, "longitude": None, "address": "Location not provided",
            "district": "", "city": "", "state": "", "postcode": "",
            "source": "none", "verified": False, "distance_km": None,
            "note": "No location captured",
        }

    check = validate_coordinates(lat, lon)
    if not check["valid"]:
        return {
            "latitude": None, "longitude": None,
            "address": manual or "Invalid coordinates rejected",
            "district": "", "city": "", "state": "", "postcode": "",
            "source": "manual" if manual else "rejected", "verified": False,
            "distance_km": check["distance_km"], "note": check["reason"],
        }

    lat, lon = float(lat), float(lon)
    geo = reverse_geocode(lat, lon)

    address = geo["address"]
    if manual:
        address = f"{manual} (near {address})"

    return {
        "latitude": lat,
        "longitude": lon,
        "address": address,
        "district": geo["district"],
        "city": geo["city"],
        "state": geo["state"],
        "postcode": geo["postcode"],
        "source": "gps",
        "verified": True,
        "distance_km": check["distance_km"],
        "note": geo["error"] or check["reason"],
    }


def map_link(lat, lon) -> str:
    """OpenStreetMap link so an admin can open the exact reported spot."""
    if lat is None or lon is None:
        return ""
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"
