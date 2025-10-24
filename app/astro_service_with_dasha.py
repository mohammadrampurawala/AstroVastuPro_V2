"""
astro_service_with_dasha.py (updated)

FastAPI service that computes natal chart data and Vimshottari mahadasha + antardasha timelines
using pyswisseph (Swiss Ephemeris). This version integrates:
 - divisional_charts.generate_divisional_set
 - numerology.* functions
 - transits.compute_transit_vs_natal
 - vastu_mapper.analyze_vastu
 - optional timezone_helper.resolve_coordinates (if present)

Run:
    uvicorn astro_service_with_dasha:app --host 0.0.0.0 --port $PORT --app-dir app --workers 1
"""
from __future__ import annotations

# Standard lib
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

# Third party
import swisseph as swe
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dateutil import parser as dateutil_parser
import pytz

# Local modules (may raise ImportError if missing; we handle that gracefully)
try:
    from divisional_charts import generate_divisional_set
except Exception:
    generate_divisional_set = None

try:
    from numerology import (
        life_path_from_dob,
        name_vibration,
        soul_urge,
        personality_number,
        personal_year,
        suggest_name_tweaks,
        breakdown_full,
    )
except Exception:
    # Keep aliases so code can still run if numerology missing
    life_path_from_dob = name_vibration = soul_urge = personality_number = personal_year = suggest_name_tweaks = breakdown_full = None

try:
    from transits import compute_transit_vs_natal
except Exception:
    compute_transit_vs_natal = None

try:
    from vastu_mapper import analyze_vastu
except Exception:
    analyze_vastu = None

# optional timezone helper (non-blocking). If not present, we'll proceed without it
try:
    from timezone_helper import resolve_coordinates
except Exception:
    resolve_coordinates = None

app = FastAPI(title="Astro Vastu Pro - Service (with Dasha & helpers)")

# Swiss ephemeris setup
swe.set_ephe_path(".")  # keep default; override if you have ephemeris files elsewhere

# Minimal constants used by dasha logic (kept from original)
VIMSHOTTARI_ORDER = [
    "Ketu",
    "Venus",
    "Sun",
    "Moon",
    "Mars",
    "Rahu",
    "Jupiter",
    "Saturn",
    "Mercury",
]
VIMSHOTTARI_YEARS = {
    "Ketu": 7.0,
    "Venus": 20.0,
    "Sun": 6.0,
    "Moon": 10.0,
    "Mars": 7.0,
    "Rahu": 18.0,
    "Jupiter": 16.0,
    "Saturn": 19.0,
    "Mercury": 17.0,
}
TOTAL_CYCLE_YEARS = sum(VIMSHOTTARI_YEARS.values())
NAK_LEN = 360.0 / 27.0
NAK_TO_START_PLANET_INDEX = [
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
]

# Planets map for natal computation (we compute core planets + mean node)
PLANETS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
    "Rahu": swe.MEAN_NODE,
}

# Geocoding fallback (if timezone_helper not present)
from geopy.geocoders import Nominatim

geolocator = Nominatim(user_agent="astrovastu_pro")

# -----------------------
# Models
# -----------------------
class BirthData(BaseModel):
    date: str
    time: str
    place: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    timezone: Optional[str] = None
    sidereal: Optional[bool] = False
    vastu: Optional[Dict[str, Any]] = None
    name: Optional[str] = None


# -----------------------
# Helpers
# -----------------------
def normalize_angle(deg: Optional[float]) -> Optional[float]:
    try:
        d = float(deg) % 360.0
        if d < 0:
            d += 360.0
        return d
    except Exception:
        return None


def _extract_from_res(res) -> Dict[str, Optional[float]]:
    """
    Parse result from swe.calc_ut which typically returns (pos_array, serr) or similar.
    Returns dict with longitude, latitude, speed_long (may be None).
    """
    out = {"longitude": None, "latitude": None, "speed_long": None}
    try:
        if res is None:
            return out
        # Some pyswisseph versions return a list/tuple where first item is a sequence
        # and other metadata follows; others return (pos, serr).
        # Try common shapes:
        if isinstance(res, (list, tuple)):
            # If first item is list-like (pos array)
            first = res[0] if len(res) > 0 else None
            if isinstance(first, (list, tuple)):
                pos = first
                # longitude
                if len(pos) >= 1:
                    out["longitude"] = float(pos[0])
                if len(pos) >= 2:
                    out["latitude"] = float(pos[1])
                if len(pos) >= 4:
                    out["speed_long"] = float(pos[3])
            else:
                # res looks like a flat sequence of numbers
                if len(res) >= 1:
                    out["longitude"] = float(res[0])
                if len(res) >= 2:
                    out["latitude"] = float(res[1])
                if len(res) >= 4:
                    out["speed_long"] = float(res[3])
        else:
            # scalar numeric
            out["longitude"] = float(res)
    except Exception as e:
        print("Warning: _extract_from_res failed:", e, "res:", res)
    return out


def _parse_datetime_to_utc_jd(date_str: str, time_str: str, tz_name: Optional[str] = None):
    """
    Parse local date/time to timezone-aware UTC datetime and Julian Day (UT) for Swiss Ephemeris.
    If tz_name is not provided, naive datetime is treated as UTC to avoid accidental local offsetging.
    """
    dt_local = dateutil_parser.parse(f"{date_str} {time_str}")
    if tz_name:
        try:
            tz = pytz.timezone(tz_name)
            if dt_local.tzinfo is None:
                dt_local = tz.localize(dt_local)
            else:
                dt_local = dt_local.astimezone(tz)
        except Exception as e:
            # fallback: proceed with dt_local as-is (will be treated as UTC)
            print(f"Warning: timezone parse failed ({tz_name}) -> {e}")
    # Ensure timezone-aware and convert to UTC
    if dt_local.tzinfo is None:
        dt_utc = dt_local.replace(tzinfo=pytz.UTC)
    else:
        dt_utc = dt_local.astimezone(pytz.UTC)
    # decimal hour
    h = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0 + dt_utc.microsecond / 3_600_000_000.0
    jd_ut = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, h)
    return dt_utc, jd_ut


def _parse_place_to_latlon(place_str: Optional[str]):
    if not place_str:
        return None, None
    # allow explicit "lat,lon"
    try:
        parts = [p.strip() for p in place_str.split(",")]
        if len(parts) >= 2:
            lat = float(parts[0])
            lon = float(parts[1])
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
    except Exception:
        pass
    return None, None


async def _resolve_place_if_needed(place: Optional[str], lat: Optional[float], lon: Optional[float]):
    """
    If lat/lon are not present, attempt to resolve using timezone_helper.resolve_coordinates (async) if available,
    otherwise use geopy.Nominatim synchronously inside a thread. Returns (lat, lon, tzname or None).
    """
    if lat is not None and lon is not None:
        return lat, lon, None

    if not place:
        return None, None, None

    # Try the async timezone_helper (preferred, if present)
    if resolve_coordinates:
        try:
            rl = await resolve_coordinates(place)
            # resolve_coordinates returns (lat, lon, tzname)
            if isinstance(rl, (tuple, list)) and len(rl) >= 2:
                lat_r, lon_r = rl[0], rl[1]
                tz_r = rl[2] if len(rl) >= 3 else None
                return lat_r, lon_r, tz_r
        except Exception as e:
            print("timezone_helper.resolve_coordinates failed:", e)

    # fallback to synchronous geopy geocoding in a thread
    try:
        from asyncio import to_thread

        def _sync_geo(p):
            g = geolocator.geocode(p, timeout=10)
            return g

        g = await to_thread(_sync_geo, place)
        if g:
            return g.latitude, g.longitude, None
    except Exception as e:
        print("geopy geocode failed:", e)

    return None, None, None


# -----------------------
# Endpoints
# -----------------------
@app.get("/", tags=["meta"])
def root():
    return {
        "service": "AstroVastu Pro API",
        "version": "2.0",
        "status": "running",
        "endpoints": ["/compute_chart", "/compute_dasha", "/health", "/docs", "/openapi.json"],
    }

# ==========================================================
# NEW ENDPOINT: Generate Complete GPT + Report
# ==========================================================
from app.gpt_client import interpret_normalized
from app.report_generator import save_report
import traceback

@app.post("/generate_report", tags=["astro", "gpt", "report"])
async def generate_report(payload: BirthData):
    """
    Full workflow:
      1. Compute natal, numerology, vastu, transits, etc. (normalized payload)
      2. Send to GPT for holistic interpretation
      3. Render AstroVastu report (HTML + PDF)
    """
    try:
        # Reuse compute_chart logic
        lat = payload.lat
        lon = payload.lon
        if (lat is None or lon is None) and payload.place:
            lat, lon, _ = await _resolve_place_if_needed(payload.place, lat, lon)

        if lat is None or lon is None:
            raise HTTPException(status_code=422, detail="Missing valid coordinates for chart generation.")

        # Build minimal normalized payload (reuse core logic)
        data = await compute_chart(payload)
        if isinstance(data, JSONResponse):
            normalized = data.body
        else:
            normalized = data.get("normalized") if isinstance(data, dict) else None

        if not normalized:
            raise HTTPException(status_code=500, detail="Failed to generate normalized data.")

        # Step 2: Call GPT
        gpt_result = interpret_normalized(normalized)
        gpt_text = gpt_result["response"]

        # Step 3: Generate report
        paths = save_report(normalized, gpt_text, name_prefix=(payload.name or "astro_report"))
        return {
            "status": "success",
            "message": f"Report generated successfully for {payload.name or 'client'}.",
            "html_path": paths.get("html"),
            "pdf_path": paths.get("pdf"),
            "gpt_summary": gpt_text[:300] + "..." if len(gpt_text) > 300 else gpt_text,
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.post("/compute_chart", tags=["astro"])
async def compute_chart(payload: BirthData):
    """
    Compute natal chart + derived outputs.
    Input (JSON fields):
      - date (YYYY-MM-DD)
      - time (HH:MM[:SS])
      - place (optional; "lat,lon" or place name)
      - lat, lon (optional floats)
      - timezone (optional tz database name)
      - sidereal (optional bool)
      - name (optional string)
      - vastu (optional dict)
    Returns normalized payload: planets, houses, ascendant, divisional charts, numerology, transits, vastu
    """
    data = payload.dict()
    # 1) Resolve lat/lon (async-friendly)
    lat = payload.lat
    lon = payload.lon
    tzname = payload.timezone

    if (lat is None or lon is None) and payload.place:
        lat, lon, tz_from_res = await _resolve_place_if_needed(payload.place, lat, lon)
        if tz_from_res and not tzname:
            tzname = tz_from_res

    if lat is None or lon is None:
        return JSONResponse(
            status_code=422,
            content={
                "error": "missing_latlon",
                "message": "Please provide latitude and longitude via 'lat' and 'lon' or provide a geocodable 'place'.",
            },
        )

    # 2) Parse date/time -> UTC and JD
    try:
        dt_utc, jd_ut = _parse_datetime_to_utc_jd(payload.date, payload.time, tzname)
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": "invalid_datetime", "message": str(e)})

    # 3) (Optional) set sidereal mode
    try:
        if payload.sidereal:
            swe.set_sid_mode(swe.SIDM_LAHIRI)
        else:
            swe.set_sid_mode(0)
    except Exception:
        pass

    # 4) Compute planetary positions
    planets_out: Dict[str, Dict[str, Any]] = {}
    for pname, pid in PLANETS.items():
        try:
            res = swe.calc_ut(jd_ut, pid)
        except Exception as e:
            print(f"Ephemeris error for {pname}: {e}")
            res = None
        vals = _extract_from_res(res)
        lon_deg = normalize_angle(vals["longitude"])
        planets_out[pname] = {
            "longitude": lon_deg,
            "latitude": vals.get("latitude"),
            "speed_long": vals.get("speed_long"),
        }

    # compute Ketu from Rahu if present
    rahu_val = planets_out.get("Rahu", {}).get("longitude")
    if rahu_val is not None:
        planets_out["Ketu"] = {"longitude": normalize_angle(rahu_val + 180.0), "latitude": None, "speed_long": None}
    else:
        planets_out.setdefault("Ketu", {"longitude": None, "latitude": None, "speed_long": None})

    # 5) Houses & Ascendant
    try:
        cusps, ascmc = swe.houses(jd_ut, lat, lon)
        houses = {str(i): normalize_angle(cusps[i]) if len(cusps) > i and cusps[i] is not None else None for i in range(1, 13)}
        asc_value = normalize_angle(ascmc[0]) if ascmc and len(ascmc) > 0 else None
    except Exception as e:
        print("House calc failed:", e)
        houses = {str(i): None for i in range(1, 13)}
        asc_value = None

    # Basic validation
    missing = []
    if planets_out.get("Jupiter", {}).get("longitude") is None:
        missing.append("planet:Jupiter")
    if houses.get("5") is None:
        missing.append("house:5")
    if asc_value is None:
        missing.append("ascendant")
    if missing:
        return JSONResponse(
            status_code=500,
            content={"error": "incomplete_chart", "missing_fields": missing, "input": data},
        )

    # 6) Divisional charts (if module present)
    natal_planets_simple = {p: {"longitude": v["longitude"]} for p, v in planets_out.items() if v.get("longitude") is not None}
    divisions_out = {}
    if generate_divisional_set:
        try:
            divisions_out = generate_divisional_set(natal_planets_simple, [2, 3, 4, 7, 9, 10, 12, 16, 30, 45, 60])
        except Exception as e:
            print("Divisional generation failed:", e)
            divisions_out = {}

    # 7) Numerology
    numerology_out = {}
    if life_path_from_dob and payload.name:
        try:
            numerology_out["life_path"] = life_path_from_dob(payload.date)
        except Exception:
            numerology_out["life_path"] = None
        numerology_out.update(
            {
                "name_vibration": name_vibration(payload.name),
                "soul_urge": soul_urge(payload.name),
                "personality": personality_number(payload.name),
                "personal_year": personal_year(payload.date),
            }
        )
    else:
        # still compute name vibration if possible
        if name_vibration and payload.name:
            numerology_out["name_vibration"] = name_vibration(payload.name)

    # 8) Transit vs natal (if module present)
    transit_report = {}
    if compute_transit_vs_natal:
        try:
            transit_report = compute_transit_vs_natal(natal_planets_simple, datetime.now(timezone.utc), orb=2.0)
        except Exception as e:
            print("Transit compute failed:", e)
            transit_report = {}

    # 9) Vastu analysis (if provided and module present)
    vastu_report = {}
    if analyze_vastu and payload.vastu:
        try:
            vastu_report = analyze_vastu(payload.vastu)
        except Exception as e:
            print("Vastu analyze failed:", e)
            vastu_report = {}

    # 10) Build normalized payload
    normalized_payload = {
        "person": {"name": payload.name, "date": payload.date, "time": payload.time, "place": payload.place, "lat": lat, "lon": lon},
        "chart": {"utc_birth": dt_utc.isoformat(), "jd_ut": jd_ut, "planets": planets_out, "houses": houses, "ascendant": asc_value},
        "divisional": divisions_out,
        "numerology": numerology_out,
        "transits": transit_report,
        "vastu": vastu_report,
    }

    return JSONResponse({"normalized": normalized_payload})


# ---- Dasha / Nakshatra utilities (kept largely from original file) ----
def moon_to_nakshatra_index(moon_longitude_deg: float):
    moon = normalize_angle(moon_longitude_deg)
    nak_index_float = moon / NAK_LEN
    nak_index = int(math.floor(nak_index_float))
    frac_in_nak = nak_index_float - nak_index
    return nak_index, frac_in_nak


def build_mahadasha_sequence(moon_lon_deg: float, birth_utc_dt: datetime):
    nak_index, frac = moon_to_nakshatra_index(moon_lon_deg)
    start_idx = NAK_TO_START_PLANET_INDEX[nak_index]
    ordered_planets = []
    for i in range(len(VIMSHOTTARI_ORDER)):
        ordered_planets.append(VIMSHOTTARI_ORDER[(start_idx + i) % len(VIMSHOTTARI_ORDER)])

    seq = []
    running_start = birth_utc_dt
    for idx, planet in enumerate(ordered_planets):
        full_years = VIMSHOTTARI_YEARS[planet]
        if idx == 0:
            years = full_years * (1.0 - frac)
        else:
            years = full_years
        days = years * 365.2425
        running_end = running_start + timedelta(days=days)
        seq.append(
            {
                "planet": planet,
                "start_utc": running_start.isoformat(),
                "end_utc": running_end.isoformat(),
                "duration_years": years,
            }
        )
        running_start = running_end
    return {"nakshatra_index": nak_index, "nakshatra_fraction": frac, "mahadasha_sequence": seq}


def build_antardashas_for_mahadasha(maha_planet: str, maha_start_dt: datetime, maha_years: float):
    try:
        start_index = VIMSHOTTARI_ORDER.index(maha_planet)
    except ValueError:
        start_index = 0
    antardashas = []
    maha_days = maha_years * 365.2425
    running_start = maha_start_dt
    for i in range(len(VIMSHOTTARI_ORDER)):
        sub_index = (start_index + i) % len(VIMSHOTTARI_ORDER)
        subplanet = VIMSHOTTARI_ORDER[sub_index]
        sub_years = maha_years * (VIMSHOTTARI_YEARS[subplanet] / TOTAL_CYCLE_YEARS)
        sub_days = sub_years * 365.2425
        running_end = running_start + timedelta(days=sub_days)
        antardashas.append(
            {
                "planet": subplanet,
                "start_utc": running_start.isoformat(),
                "end_utc": running_end.isoformat(),
                "duration_years": sub_years,
            }
        )
        running_start = running_end
    return antardashas


@app.post("/compute_dasha", tags=["astro"])
def compute_dasha(data: BirthData):
    """
    Compute Vimshottari mahadasha sequence (and nested antardashas) for given birth data.
    This uses the moon longitude computed via pyswisseph.
    """
    # Resolve lat/lon similar to compute_chart (prefer explicit lat/lon)
    lat = data.lat
    lon = data.lon
    if (lat is None or lon is None) and data.place:
        # try parse lat,lon from string
        latlon = _parse_place_to_latlon(data.place)
        if latlon != (None, None):
            lat, lon = latlon
        else:
            # fallback to geocoding synchronously (best-effort)
            try:
                g = geolocator.geocode(data.place, timeout=10)
                if g:
                    lat, lon = g.latitude, g.longitude
            except Exception:
                pass

    if lat is None or lon is None:
        raise HTTPException(status_code=422, detail="Please provide 'lat' and 'lon' or a geocodable 'place' for dasha computation.")

    # Determine timezone name (prefer explicit)
    tz_name = data.timezone

    # Parse local date/time -> UTC and JD
    try:
        utc_dt, jd_ut = _parse_datetime_to_utc_jd(data.date, data.time, tz_name)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid date/time/timezone: {e}")

    # Sidereal / tropical selection
    try:
        if data.sidereal:
            swe.set_sid_mode(swe.SIDM_LAHIRI)
        else:
            swe.set_sid_mode(0)
    except Exception:
        pass

    # Compute Moon longitude
    try:
        moon_res = swe.calc_ut(jd_ut, swe.MOON)
        moon_vals = _extract_from_res(moon_res)
        moon_lon = normalize_angle(moon_vals["longitude"]) if moon_vals["longitude"] is not None else None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ephemeris error computing Moon: {e}")

    if moon_lon is None:
        raise HTTPException(status_code=500, detail="Unable to compute Moon longitude.")

    # Build mahadasha sequence and antardashas
    maha_info = build_mahadasha_sequence(moon_lon, utc_dt)
    for maha in maha_info["mahadasha_sequence"]:
        start_dt = datetime.fromisoformat(maha["start_utc"])
        duration_years = maha["duration_years"]
        maha["antardashas"] = build_antardashas_for_mahadasha(maha["planet"], start_dt, duration_years)

    return {
        "input": {"date": data.date, "time": data.time, "place": data.place, "lat": lat, "lon": lon, "timezone": tz_name},
        "utc_birth": utc_dt.isoformat(),
        "moon_longitude": moon_lon,
        "nakshatra_index": maha_info["nakshatra_index"],
        "nakshatra_fraction": maha_info["nakshatra_fraction"],
        "mahadasha_sequence": maha_info["mahadasha_sequence"],
    }
