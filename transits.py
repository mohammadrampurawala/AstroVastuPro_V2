"""
transits.py

Compute planetary transit positions (using pyswisseph / swe) and compare with natal planets.

Functions:
 - jd_from_datetime(dt: datetime) -> float  : convert a timezone-aware UTC datetime to Julian Day (UT)
 - compute_transit_positions(dt: datetime, planets: list = DEFAULT_PLANETS) -> dict
 - compute_transit_vs_natal(natal_planets: dict, dt: datetime, orb: float = 2.0) -> dict

Output formats are simple JSON-compatible dictionaries intended to be merged into the normalized payload.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
import math
import swisseph as swe

# Default list of planets used commonly in Vedic astrology (including nodes)
DEFAULT_PLANETS = [
    "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
    "Rahu", "Ketu"
]

# Map planet name -> swe constant
SWE_MAP = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
    # for nodes, pyswisseph uses MEAN_* or TRUE_*, but we use mean node:
    "Rahu": swe.MEAN_NODE,  # ascending node (Rahu)
    "Ketu": None  # Ketu is 180° opposite Rahu; compute from Rahu when needed
}

ASPECTS = {
    "conjunction": 0.0,
    "opposition": 180.0,
    "square": 90.0,
    "trine": 120.0,
    "sextile": 60.0,
    "quincunx": 150.0
}

def normalize_angle(deg: float) -> float:
    d = float(deg) % 360.0
    if d < 0:
        d += 360.0
    return d

def shortest_angular_distance(a: float, b: float) -> float:
    diff = abs(normalize_angle(a) - normalize_angle(b))
    return min(diff, 360.0 - diff)

def jd_from_datetime(dt: datetime) -> float:
    """
    Convert a timezone-aware datetime (UTC) to Julian Day (UT) for swe.julday.
    If dt is naive, it's assumed to be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60.0 + dt.second / 3600.0)

def compute_planet_longitude_at_jd(jd: float, planet_const: int) -> float:
    """
    Return ecliptic longitude of planet (geocentric) in degrees.
    pyswisseph.swe.calc_ut returns (pos_array, serr).
    pos_array[0] is the longitude (in degrees).
    """
    pos, serr = swe.calc_ut(jd, planet_const)
    # pos should be a sequence; take first element as longitude
    lon = pos[0]
    return normalize_angle(float(lon))


def compute_transit_positions(dt: datetime, planets: List[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Compute transit longitudes for the specified planets at datetime dt (UTC assumed).
    Returns: {planet_name: {"longitude": deg}}
    """
    if planets is None:
        planets = DEFAULT_PLANETS
    jd = jd_from_datetime(dt)
    out: Dict[str, Dict[str, Any]] = {}
    # compute Rahu (mean node) and Ketu (opposite)
    # We compute all named planets; if a planet mapping is None, skip it.
    for pname in planets:
        if pname == "Ketu":
            # compute Rahu and subtract 180
            # Ensure we have a valid mapping for Rahu
            rahu_const = SWE_MAP.get("Rahu")
            if rahu_const is None:
                continue
            rahu_pos, _ = swe.calc_ut(jd, rahu_const)
            rahu_lon = normalize_angle(float(rahu_pos[0]))
            ketu_lon = normalize_angle(rahu_lon + 180.0)
            out["Ketu"] = {"longitude": ketu_lon}
        else:
            pconst = SWE_MAP.get(pname)
            if pconst is None:
                continue
            # use compute_planet_longitude_at_jd which now handles swe.calc_ut return shape
            lon = compute_planet_longitude_at_jd(jd, pconst)
            out[pname] = {"longitude": lon}
    return out

def find_aspect_between(deg1: float, deg2: float, orb: float = 2.0) -> Tuple[str, float]:
    """
    Check which major aspect (if any) exists between deg1 and deg2 within 'orb' degrees.
    Returns (aspect_name, exact_diff) with exact_diff = actual angular separation - ideal_angle
    If no aspect found within orb, returns (None, None)
    """
    sep = shortest_angular_distance(deg1, deg2)
    for name, angle in ASPECTS.items():
        diff = abs(sep - angle)
        if diff <= orb:
            return name, diff
    return None, None

def compute_transit_vs_natal(natal_planets: Dict[str, Dict[str, Any]], dt: datetime, orb: float = 2.0) -> Dict[str, Any]:
    """
    Compare transit planets at dt with natal planets and return detected close aspects.
    Output format:
    {
      "date_utc": "...",
      "aspects": [
         {"transit": "Jupiter", "natal": "Moon", "aspect": "trine", "sep_deg": 119.8, "orb": 0.2},
         ...
      ],
      "transit_positions": { "Jupiter": {"longitude": ...}, ...}
    }
    """
    transits = compute_transit_positions(dt)
    aspects = []
    # Normalize natal lookup for names -> lon
    natal_lons = {p: float(info.get("longitude")) for p, info in natal_planets.items() if info.get("longitude") is not None}
    for tname, tinfo in transits.items():
        t_lon = tinfo.get("longitude")
        for nname, n_lon in natal_lons.items():
            aspect_name, diff = find_aspect_between(t_lon, n_lon, orb=orb)
            if aspect_name:
                sep = shortest_angular_distance(t_lon, n_lon)
                aspects.append({
                    "transit": tname,
                    "natal": nname,
                    "aspect": aspect_name,
                    "separation": round(sep, 4),
                    "orb": round(diff, 4),
                    "transit_longitude": round(t_lon, 6),
                    "natal_longitude": round(n_lon, 6)
                })
    return {
        "date_utc": dt.astimezone(timezone.utc).isoformat(),
        "transit_positions": transits,
        "aspects": aspects
    }

# --- CLI demo for quick local testing ---
if __name__ == "__main__":
    import json, sys
    print("Transit module CLI demo")
    # Accept optional ISO datetime as first arg, else use now UTC
    if len(sys.argv) > 1:
        dt = datetime.fromisoformat(sys.argv[1])
    else:
        dt = datetime.now(timezone.utc)
    print("Compute transits for:", dt.isoformat())
    trans = compute_transit_positions(dt)
    print(json.dumps(trans, indent=2))
    print("\nSample natal comparison (demo natal Sun 45deg, Moon 210deg):")
    natal_demo = {"Sun": {"longitude": 45.0}, "Moon": {"longitude": 210.0}}
    cmp = compute_transit_vs_natal(natal_demo, dt)
    print(json.dumps(cmp, indent=2))
