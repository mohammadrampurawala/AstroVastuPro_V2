"""
numerology.py

Simple numerology utilities for AstroVastuPro.

Features:
 - Pythagorean letter->number mapping
 - Life Path calculation
 - Name vibration (destiny), Soul Urge (vowels), Personality (consonants)
 - Personal year calculation
 - Suggest minimal name tweaks (single-letter initials) to reach a target vibration
   with friendly, idempotent suggestions and optional full explanation.
"""

from typing import List, Tuple, Dict, Any
import re
import datetime

# Pythagorean mapping A-Z -> 1..9
PYTHA_MAP = {
    **dict.fromkeys(list("A J S".split()), 1),
    **dict.fromkeys(list("B K T".split()), 2),
    **dict.fromkeys(list("C L U".split()), 3),
    **dict.fromkeys(list("D M V".split()), 4),
    **dict.fromkeys(list("E N W".split()), 5),
    **dict.fromkeys(list("F O X".split()), 6),
    **dict.fromkeys(list("G P Y".split()), 7),
    **dict.fromkeys(list("H Q Z".split()), 8),
    **dict.fromkeys(list("I R".split()), 9),
}

VOWELS = set(list("AEIOU"))
CONSONANTS = set(chr(c) for c in range(65, 91)) - VOWELS

# ----------------------
# Basic utilities
# ----------------------
def clean_name(name: str) -> str:
    """Uppercase and remove non-letters."""
    if not name:
        return ""
    return re.sub(r"[^A-Z]", "", name.upper())

def name_to_numbers(name: str) -> List[int]:
    s = clean_name(name)
    return [PYTHA_MAP.get(ch, 0) for ch in s if ch.isalpha()]

def reduce_to_core(n: int) -> int:
    """
    Reduce a number to a core numerology number:
    Keep master numbers 11 and 22 (do not reduce them further).
    Otherwise, reduce to 1..9.
    """
    if n in (11, 22):
        return n
    s = abs(int(n))
    while s > 9:
        s = sum(int(d) for d in str(s))
    return s

# ----------------------
# Numerology calculations
# ----------------------
def life_path_from_dob(dob_iso: str) -> int:
    """
    dob_iso expected in YYYY-MM-DD or a parseable ISO format.
    Life path = reduce_to_core(sum of digits of day + month + year).
    """
    if not dob_iso:
        raise ValueError("dob_iso required")
    dt = datetime.date.fromisoformat(dob_iso.split("T")[0])
    total = sum(int(ch) for ch in dt.strftime("%Y%m%d"))
    return reduce_to_core(total)

def name_vibration(name: str) -> int:
    nums = name_to_numbers(name)
    if not nums:
        return 0
    total = sum(nums)
    return reduce_to_core(total)

def soul_urge(name: str) -> int:
    s = clean_name(name)
    nums = [PYTHA_MAP[ch] for ch in s if ch in VOWELS]
    if not nums:
        return 0
    return reduce_to_core(sum(nums))

def personality_number(name: str) -> int:
    s = clean_name(name)
    nums = [PYTHA_MAP[ch] for ch in s if ch in CONSONANTS]
    if not nums:
        return 0
    return reduce_to_core(sum(nums))

def personal_year(dob_iso: str, year: int = None) -> int:
    """
    Personal year for a calendar year = reduce_to_core(sum of month + day + digits of target year).
    """
    if not dob_iso:
        raise ValueError("dob_iso required")
    if year is None:
        year = datetime.date.today().year
    dt = datetime.date.fromisoformat(dob_iso.split("T")[0])
    md = sum(int(d) for d in "{:02d}{:02d}".format(dt.month, dt.day))
    ysum = sum(int(ch) for ch in str(year))
    return reduce_to_core(md + ysum)

# ----------------------
# Breakdown utilities (for explanation)
# ----------------------
def breakdown_full(name_str: str) -> Dict[str, Any]:
    """
    Return a detailed breakdown for a name:
      - letters: list of (letter, value)
      - total_raw: sum of letter values
      - reduced: reduced vibration (core)
    """
    s = clean_name(name_str)
    letters = [(ch, PYTHA_MAP.get(ch, 0)) for ch in s if ch.isalpha()]
    total = sum(v for _, v in letters)
    reduced = reduce_to_core(total)
    return {"letters": letters, "total_raw": total, "reduced": reduced}

# ----------------------
# Improved suggestion routine (user-friendly and idempotent)
# ----------------------
def suggest_name_tweaks(name: str, target: int, max_changes: int = 1, explain: bool = False, full_map: bool = False) -> Dict[str, Any]:
    """
    Suggest minimal tweaks (single-letter initials) to move name vibration toward `target`.

    Returns a dict:
    {
      "status": "already_matching" | "ok" | "no_suggestion" | "no_name",
      "original_vibration": int or None,
      "target": int,
      "suggestions": [ ... ]   # depending on explain/full_map flags
    }

    Behavior:
    - If the base name already equals the target vibration => status "already_matching".
    - Avoids suggesting initials that are already present as the initial token.
    - Prefers exact matches; otherwise nearest vibration.
    - Deduplicates by resulting vibration.
    - explain=True returns short human-friendly explanations; full_map=True adds full breakdown dicts.
    """
    base = name.strip()
    if not base:
        return {"status": "no_name", "original_vibration": None, "target": target, "suggestions": []}

    base_br = breakdown_full(base)
    base_vib = base_br["reduced"]

    # If already matching target, return early (idempotent behavior)
    if base_vib == target:
        return {
            "status": "already_matching",
            "original_vibration": base_vib,
            "target": target,
            "suggestions": []
        }

    # Prepare detection of existing initial(s) to avoid re-suggesting
    base_tokens = set()
    try:
        tokens = [t for t in name.split() if t]
        if tokens:
            base_tokens.add(tokens[0])        # first token (e.g., "I" or "IMohammad")
            base_tokens.add(tokens[0][0])    # first letter token (e.g., "I")
    except Exception:
        pass

    letters = [chr(c) for c in range(65, 91)]
    candidates: List[Dict[str, Any]] = []
    seen_vibs = set()

    for ch in letters:
        # patterns to try
        for pattern, method in ((f"{ch} {base}", f"add initial '{ch} '"), (f"{ch}{base}", f"add initial '{ch}' (no space)")):
            # Skip if the added initial likely already present
            if ch in base_tokens or pattern == base:
                continue
            new_br = breakdown_full(pattern)
            new_vib = new_br["reduced"]
            if new_vib in seen_vibs:
                continue
            seen_vibs.add(new_vib)
            dist = abs(new_vib - target)
            delta = new_vib - base_vib
            candidates.append({
                "pattern": pattern,
                "method": method,
                "new_vibration": new_vib,
                "distance_to_target": dist,
                "delta": delta,
                "breakdown_before": base_br,
                "breakdown_after": new_br,
                "added_letter": ch,
                "added_value": PYTHA_MAP.get(ch, 0)
            })

    if not candidates:
        return {
            "status": "no_suggestion",
            "original_vibration": base_vib,
            "target": target,
            "suggestions": []
        }

    # Sort: exact matches first, then by closeness to target, then by smallest absolute delta
    candidates.sort(key=lambda x: (0 if x["distance_to_target"] == 0 else 1, x["distance_to_target"], abs(x["delta"]), x["new_vibration"]))

    selected = candidates[:max_changes]
    suggestions_out = []

    for c in selected:
        if not explain:
            suggestions_out.append((c["pattern"], c["new_vibration"], c["method"]))
        else:
            expl = {
                "suggested_name": c["pattern"],
                "method": c["method"],
                "added_letter": c["added_letter"],
                "added_value": c["added_value"],
                "original_vibration": base_vib,
                "new_vibration": c["new_vibration"],
                "delta": c["delta"],
                "distance_to_target": c["distance_to_target"],
            }
            if full_map:
                expl["breakdown_before"] = c["breakdown_before"]
                expl["breakdown_after"] = c["breakdown_after"]
            suggestions_out.append(expl)

    return {
        "status": "ok",
        "original_vibration": base_vib,
        "target": target,
        "suggestions": suggestions_out
    }

# ----------------------
# CLI demo & testing (user-friendly output)
# ----------------------
if __name__ == "__main__":
    import json, sys

    print("Numerology CLI demo")
    name = input("Enter full name (e.g., John Doe): ").strip()
    dob = input("Enter DOB (YYYY-MM-DD): ").strip()

    try:
        lp = life_path_from_dob(dob)
    except Exception as e:
        print("DOB parse error:", e)
        lp = None

    out = {
        "name": name,
        "life_path": lp,
        "name_vibration": name_vibration(name),
        "soul_urge": soul_urge(name),
        "personality": personality_number(name),
        "personal_year": personal_year(dob) if dob else None
    }

    print(json.dumps(out, indent=2))

    if lp:
        # Show a concise original breakdown (single-line)
        br = breakdown_full(name)
        before_map = ", ".join(f"{L}:{V}" for L, V in br["letters"])
        print(f"\nOriginal name raw total = {br['total_raw']}, vibration = {br['reduced']}")
        print(f"Letter->value (original): {before_map}")

        # Get a single best suggestion with concise explanation (no full map by default)
        resp = suggest_name_tweaks(name, lp, max_changes=1, explain=True, full_map=False)

        if resp["status"] == "already_matching":
            print("\nYour name already matches the Life Path vibration. No changes needed.")
        elif resp["status"] == "no_suggestion":
            print("\nNo practical single-letter initial suggestion found to reach the target vibration.")
        elif resp["status"] == "ok" and resp["suggestions"]:
            s = resp["suggestions"][0]
            print("\nSuggestion to align with Life Path (single best option):")
            print(f" → Suggested name: {s['suggested_name']}")
            print(f"   Method: {s['method']} (added letter '{s['added_letter']}' = {s['added_value']})")
            print(f"   Original vibration: {s['original_vibration']}, New vibration: {s['new_vibration']} (delta {s['delta']:+d})")
            if s["distance_to_target"] == 0:
                print("   This suggestion exactly matches your Life Path vibration.")
            else:
                print(f"   This suggestion moves you {abs(s['distance_to_target'])} step(s) closer to the target vibration.")
            print("\nNext step: try applying the suggested initial and re-run this check. If your name then matches the vibration, no further suggestions will be provided.")
        else:
            print("\nNo suggestion available.")
    else:
        print("\nNo life path available; cannot suggest name tweaks.")
