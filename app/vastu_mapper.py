"""
vastu_mapper.py

Simple Vastu sector mapper & activation suggestion engine.

Input model (examples):
  {
    "plot_facing": "North",        # one of N, S, E, W or full names
    "main_entrance": "NE",        # compass sector or direction string
    "rooms": [
       {"name":"master_bed", "sector":"SW"},
       {"name":"kitchen", "sector":"SE"},
       {"name":"puja", "sector":"NE"},
    ],
    "plot_type": "apartment"      # optional: "house" | "apartment"
  }

Outputs:
  {
    "sectors": { "NE": {...}, "SW": {...} },
    "weak_sectors": ["NW", ...],
    "recommended_activations": [
       {"sector":"NE", "action":"place water element", "priority":1, "why":"Entrance faces north-east"},
       ...
    ]
  }

This is intentionally deterministic and conservative (no magical claims).
"""

from typing import Dict, Any, List

# canonical sector names (N, NE, E, SE, S, SW, W, NW)
SECTORS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# simple mapping of sectors -> element & qualities
SECTOR_QUALITIES = {
    "N": {"element": "water", "qualities": ["career", "flow"]},
    "NE": {"element": "earth", "qualities": ["spirituality", "study"]},
    "E": {"element": "air", "qualities": ["health", "family"]},
    "SE": {"element": "fire", "qualities": ["wealth", "kitchen"]},
    "S": {"element": "fire", "qualities": ["fame", "energy"]},
    "SW": {"element": "earth", "qualities": ["stability", "relationships"]},
    "W": {"element": "water", "qualities": ["children", "creativity"]},
    "NW": {"element": "air", "qualities": ["network", "travel"]},
}

# light-weight rules for activations (these are suggestions — kept short)
DEFAULT_ACTIVATIONS = {
    "NE": [{"action": "keep clutter free", "reason": "NE supports spiritual/study activities", "priority": 1}],
    "SW": [{"action": "strengthen with heavy furniture or earth tones", "reason": "SW supports stability and relationships", "priority": 1}],
    "SE": [{"action": "kitchen or fire element here is good; if not, use bright lights", "reason": "SE represents fire and wealth", "priority": 1}],
    "N":  [{"action": "water features (small) or mirror carefully", "reason": "N supports flow and career", "priority": 2}],
    "E":  [{"action": "place plants, morning light area", "reason": "E supports health", "priority": 2}],
    "W":  [{"action": "use creative displays for children and hobbies", "reason": "W supports creativity/children", "priority": 3}],
    "NW": [{"action": "keep for guest/transport functions; avoid heavy storage", "reason": "NW supports movement/network", "priority": 3}],
    "S":  [{"action": "avoid heavy water in south; use colors for fame", "reason": "S supports reputation", "priority": 3}],
}

def normalize_sector(s: str) -> str:
    if not s:
        return None
    s2 = s.strip().upper()
    # Accept full names (NORTH -> N), or initials
    mapping = {
        "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
        "NORTHEAST": "NE", "NORTH-EAST": "NE", "SOUTHWEST": "SW",
        "SOUTH-WEST": "SW", "SOUTHEAST": "SE", "SOUTH-EAST": "SE",
        "NORTHWEST": "NW", "NORTH-WEST": "NW"
    }
    if s2 in SECTORS:
        return s2
    return mapping.get(s2, None)

def map_rooms_to_sectors(rooms: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return a mapping sector -> list of rooms placed there.
    """
    out = {sec: [] for sec in SECTORS}
    for r in rooms:
        sec = normalize_sector(r.get("sector") or r.get("direction"))
        if not sec:
            continue
        out.setdefault(sec, []).append(r)
    return out

def analyze_vastu(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point.
    payload fields (optional): plot_facing, main_entrance, rooms (list), plot_type.
    """
    plot_facing = normalize_sector(payload.get("plot_facing") or payload.get("facing") or "")
    entrance = normalize_sector(payload.get("main_entrance") or payload.get("entrance") or "")
    rooms = payload.get("rooms", []) or []
    plot_type = (payload.get("plot_type") or "house").lower()

    room_map = map_rooms_to_sectors(rooms)

    # Count occupancy per sector
    occupancy = {sec: len(room_map.get(sec, [])) for sec in SECTORS}

    # Simple heuristics to identify weak sectors:
    # - sectors with zero rooms and not the entrance are weak candidates
    weak_sectors = [sec for sec, cnt in occupancy.items() if cnt == 0 and sec != entrance]

    # Build recommended activations: prioritize entrance-facing + weak sectors + important room-specific fixes
    recs = []

    # If entrance is present, suggest entrance-specific activation
    if entrance:
        recs.append({
            "sector": entrance,
            "action": DEFAULT_ACTIVATIONS.get(entrance, [{"action":"keep clean","reason":"entrance"}])[0]["action"],
            "priority": 0,
            "why": f"Main entrance is at {entrance}"
        })

    # Weak sectors activation
    for idx, sec in enumerate(weak_sectors):
        act = DEFAULT_ACTIVATIONS.get(sec, [{"action": "declutter", "reason": "balance"}])[0]
        recs.append({
            "sector": sec,
            "action": act["action"],
            "priority": 2 + idx,
            "why": f"Sector {sec} currently has no rooms; suggested activation to balance energy."
        })

    # Room-specific rules (e.g., kitchen not in NE)
    for sec, rlist in room_map.items():
        for r in rlist:
            name = (r.get("name") or "").lower()
            if "kitchen" in name and sec == "NE":
                recs.append({
                    "sector": sec,
                    "action": "Consider relocating kitchen (NE not ideal for fire); if not possible, mitigate with white tiles and ventilation",
                    "priority": 1,
                    "why": "Kitchen (fire) in NE (spiritual sector) - mitigation suggested"
                })
            if "puja" in name or "altar" in name or "temple" in name:
                if sec not in ("NE", "E"):
                    recs.append({
                        "sector": sec,
                        "action": "Prefer moving puja/meditation to NE/E if possible; otherwise keep clean and elevated",
                        "priority": 1,
                        "why": "Puja best suited to NE/E"
                    })

    # Add sector qualities to output
    sectors_info = {}
    for sec in SECTORS:
        sectors_info[sec] = {
            "element": SECTOR_QUALITIES.get(sec, {}).get("element"),
            "qualities": SECTOR_QUALITIES.get(sec, {}).get("qualities"),
            "occupancy_count": occupancy.get(sec, 0),
            "rooms": room_map.get(sec, [])
        }

    # Sort recommendations by priority ascending
    recs_sorted = sorted(recs, key=lambda x: x.get("priority", 99))

    return {
        "plot_facing": plot_facing,
        "entrance": entrance,
        "plot_type": plot_type,
        "sectors": sectors_info,
        "weak_sectors": weak_sectors,
        "recommended_activations": recs_sorted
    }

# Quick CLI test
if __name__ == "__main__":
    import json
    sample = {
        "plot_facing": "North",
        "main_entrance": "NE",
        "rooms": [
            {"name": "master_bed", "sector": "SW"},
            {"name": "kitchen", "sector": "SE"},
            {"name": "puja", "sector": "NW"}
        ],
        "plot_type": "house"
    }
    print(json.dumps(analyze_vastu(sample), indent=2))
