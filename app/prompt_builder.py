"""
prompt_builder.py

Builds a structured GPT prompt from the normalized output of AstroVastuPro backend.
This prompt feeds the GPT model to generate an interpretive report combining:
- Astro (planetary & dasha insights)
- Vastu (sectors & remedies)
- Numerology (name & DOB alignment)
"""

import json
from typing import Dict, Any, List

def summarize_chart(chart: Dict[str, Any]) -> str:
    """Summarize key chart details for GPT (houses + ascendant + major planets)."""
    if not chart or not chart.get("planets"):
        return "No chart data available."

    asc = chart.get("ascendant")
    planets = chart.get("planets", {})
    out = [f"Ascendant at {asc:.2f}°" if asc else "Ascendant not computed"]

    for pname, pdata in planets.items():
        if pdata.get("longitude") is not None:
            out.append(f"{pname} at {pdata['longitude']:.2f}°")
    return "; ".join(out)

def summarize_vastu(vastu: Dict[str, Any]) -> str:
    """Summarize Vastu findings into short GPT-friendly text."""
    if not vastu:
        return "No Vastu data provided."

    facing = vastu.get("plot_facing") or "Unknown"
    weak = vastu.get("weak_sectors") or []
    recs = vastu.get("recommended_activations") or []

    text = [f"Plot facing: {facing}."]
    if weak:
        text.append(f"Weak sectors: {', '.join(weak)}.")
    if recs:
        text.append("Key activations/remedies:")
        for r in recs[:5]:  # top 5
            text.append(f" - {r['sector']}: {r['action']} ({r['why']})")
