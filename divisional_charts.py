"""
divisional_charts.py

Compute Vedic divisional (Varga) charts Dn from natal planetary longitudes.

Expected input example:
  natal_planets = {
    "Sun": {"longitude": 123.45},
    "Moon": {"longitude": 210.23},
    ...
  }

Functions:
  - compute_divisional(natal_planets: dict, n: int) -> dict
      Returns mapping planet -> {"longitude": deg, "sign_index": 0..11, "sign": "Aries", "deg_in_sign": float}

  - generate_divisional_set(natal_planets: dict, d_list: list) -> dict
      Returns dict of Dn charts keyed by "D{n}".
"""

from typing import Dict, Any, List
import math

SIGNS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"
]

def normalize_angle(deg: float) -> float:
    d = float(deg) % 360.0
    if d < 0:
        d += 360.0
    return d

def sign_index_from_deg(deg: float) -> int:
    return int(math.floor(normalize_angle(deg) / 30.0)) % 12

def deg_in_sign(deg: float) -> float:
    deg = normalize_angle(deg)
    return deg % 30.0

def compute_divisional(natal_planets: Dict[str, Dict[str, Any]], n: int) -> Dict[str, Dict[str, Any]]:
    """
    Compute Dn chart where each sign (30deg) is subdivided into n equal parts.
    This maps each planet to one of the 12*n slots and returns an approximate Dn longitude.
    """
    if not isinstance(n, int) or n <= 0:
        raise ValueError("n must be a positive integer (e.g., 2,3,9,10,12,16,30,60)")

    result = {}
    slot_width = 30.0 / n  # degrees within a sign

    for pname, pinfo in natal_planets.items():
        L = pinfo.get("longitude")
        if L is None:
            continue
        L = normalize_angle(float(L))
        sign_idx = sign_index_from_deg(L)
        pos_in_sign = L - (sign_idx * 30.0)  # 0..30
        # which sub-slot inside sign (0..n-1)
        sub_slot = int(math.floor(pos_in_sign / slot_width)) % n
        # fraction inside the sub-slot (0..1)
        fraction_inside_slot = (pos_in_sign - (sub_slot * slot_width)) / slot_width
        # Compute Dn expanded index and map back to 0..360
        expanded_index = sign_idx * n + sub_slot  # 0 .. 12*n-1
        dn_longitude = (expanded_index * slot_width) + (fraction_inside_slot * slot_width)
        dn_longitude = normalize_angle(dn_longitude)
        dn_sign_idx = sign_index_from_deg(dn_longitude)
        result[pname] = {
            "longitude": dn_longitude,
            "sign_index": dn_sign_idx,
            "sign": SIGNS[dn_sign_idx],
            "deg_in_sign": deg_in_sign(dn_longitude)
        }
    return result

def generate_divisional_set(natal_planets: Dict[str, Dict[str, Any]], d_list: List[int]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for d in d_list:
        out[f"D{d}"] = compute_divisional(natal_planets, d)
    return out

# Quick CLI smoke test (run: python divisional_charts.py)
if __name__ == "__main__":
    sample = {
        "Sun": {"longitude": 45.0},    # Taurus 15deg
        "Moon": {"longitude": 210.0},  # Scorpio 0deg
        "Mars": {"longitude": 359.5},  # Pisces 29.5deg
    }
    import json
    print("Sample D9 (Navamsa):")
    print(json.dumps(compute_divisional(sample, 9), indent=2))
    print("\nSample D10 (Dashamsa):")
    print(json.dumps(compute_divisional(sample, 10), indent=2))
