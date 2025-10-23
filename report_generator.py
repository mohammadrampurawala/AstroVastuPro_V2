"""
report_generator.py

Generate HTML and PDF reports from a normalized payload + GPT interpretation.

Functions:
 - render_report_html(normalized: dict, gpt_text: str, title: str) -> str
     Returns the rendered HTML string.

 - save_report(normalized: dict, gpt_text: str, title: str, out_dir: str=None, name_prefix: str='report') -> dict
     Renders and writes HTML and (optionally) PDF to disk. Returns dict with paths.

 - generate_report_bytes(normalized: dict, gpt_text: str, as_pdf: bool=True) -> bytes
     Returns report bytes (PDF if as_pdf and WeasyPrint present, otherwise HTML bytes).

Notes:
 - Requires `jinja2` (already in requirements). If `weasyprint` is installed, PDF will be generated.
 - The report uses inline CSS (no external resources).
"""

from typing import Dict, Any, Optional
from jinja2 import Template, Environment, FileSystemLoader, select_autoescape
from datetime import datetime
from pathlib import Path
import html
import os

# Try importing WeasyPrint (optional)
try:
    from weasyprint import HTML, CSS  # type: ignore
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False

# Inline CSS used by the template (simple, print-friendly)
DEFAULT_CSS = """
body { font-family: Arial, Helvetica, sans-serif; color: #222; line-height: 1.4; padding: 24px; }
.header { display:flex; justify-content:space-between; align-items:center; }
.brand { font-size: 20px; font-weight: 700; color: #1f4e79; }
.meta { font-size: 12px; color: #555; }
.section { margin-top: 18px; padding: 12px; border-radius:8px; background: #fbfbfb; box-shadow: 0 1px 0 rgba(0,0,0,0.04); }
.section h2 { margin: 0 0 8px 0; font-size: 16px; color: #0b3355; }
.kv { display:flex; gap:8px; margin:6px 0; }
.kv .k { width:160px; color:#444; font-weight:600 }
.kv .v { color:#111; }
.remedy { margin:6px 0; padding:8px; border-left:4px solid #e7e7e7; background:#fff; }
.foot { margin-top:24px; font-size:12px; color:#666; }
.small { font-size:11px; color:#777; }
@media print { body { padding: 8px } .section { box-shadow:none; } }
"""

# Jinja2 template string (self-contained)
TEMPLATE_STR = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{{ title | e }}</title>
  <style>{{ css }}</style>
</head>
<body>
  <div class="header">
    <div class="brand">Astro Vastu Pro — Personalized Report</div>
    <div class="meta">
      Generated: {{ gen_time }}<br/>
      Client: {{ person.name or "Unknown" }} • DOB: {{ person.date or "-" }} • TOB: {{ person.time or "-" }}
    </div>
  </div>

  <div class="section">
    <h2>Executive Summary</h2>
    <p class="small">{{ summary|e }}</p>
  </div>

  <div class="section">
    <h2>Astrology Snapshot</h2>
    <div class="kv"><div class="k">Ascendant</div><div class="v">{{ chart.ascendant or "-" }}</div></div>
    {% if chart.planets %}
      <h3>Planets</h3>
      {% for pname, pinfo in chart.planets.items() %}
        <div class="kv"><div class="k">{{ pname }}</div><div class="v">{{ pinfo.longitude|default('-', true) }}°</div></div>
      {% endfor %}
    {% endif %}
    {% if divisional %}
      <h3>Divisional Charts (sample)</h3>
      <div class="small">Showing D9 and D10 if available</div>
      {% for dname in divisional.keys() | list | sort %}
        {% if dname in ['D9','D10'] %}
          <div class="kv"><div class="k">{{ dname }}</div>
            <div class="v">
              {% for pname, p in divisional[dname].items() %}
                <div>{{ pname }}: {{ p.sign }} {{ p.deg_in_sign|round(2) }}°</div>
              {% endfor %}
            </div>
          </div>
        {% endif %}
      {% endfor %}
    {% endif %}
  </div>

  <div class="section">
    <h2>Vastu Highlights</h2>
    {% if vastu.plot_facing %}
      <div class="kv"><div class="k">Plot Facing</div><div class="v">{{ vastu.plot_facing }}</div></div>
    {% endif %}
    {% if vastu.weak_sectors %}
      <div class="kv"><div class="k">Weak Sectors</div><div class="v">{{ vastu.weak_sectors | join(', ') }}</div></div>
    {% endif %}
    {% if vastu.recommended_activations %}
      <h3>Top Activations</h3>
      {% for r in vastu.recommended_activations[:6] %}
        <div class="remedy"><strong>{{ r.sector }}:</strong> {{ r.action }} <div class="small">({{ r.why }})</div></div>
      {% endfor %}
    {% else %}
      <div class="small">No Vastu data provided.</div>
    {% endif %}
  </div>

  <div class="section">
    <h2>Numerology</h2>
    {% if numerology %}
      <div class="kv"><div class="k">Life Path</div><div class="v">{{ numerology.life_path or "-" }}</div></div>
      <div class="kv"><div class="k">Name Vibration</div><div class="v">{{ numerology.name_vibration or "-" }}</div></div>
      <div class="kv"><div class="k">Personal Year</div><div class="v">{{ numerology.personal_year or "-" }}</div></div>
    {% else %}
      <div class="small">No numerology data.</div>
    {% endif %}
  </div>

  <div class="section">
    <h2>Interpretation (AI)</h2>
    <pre style="white-space:pre-wrap; font-family:inherit;">{{ gpt_text }}</pre>
  </div>

  <div class="foot">
    <div class="small">This report is for guidance only. Remedies are suggested based on classical Vedic principles and modern heuristics. Not a substitute for professional services.</div>
  </div>
</body>
</html>
"""

env = Environment(autoescape=select_autoescape(["html", "xml"]))


def _safe_get(d: Dict[str, Any], key: str, default=None):
    return d.get(key, default) if isinstance(d, dict) else default


def render_report_html(normalized: Dict[str, Any], gpt_text: str, title: str = "Astro Vastu Pro Report", css: Optional[str] = None) -> str:
    """
    Render the HTML report string using the template and the normalized data.
    """
    css_use = css or DEFAULT_CSS
    tpl = Template(TEMPLATE_STR)
    person = _safe_get(normalized, "person", {})
    chart = _safe_get(normalized, "chart", {})
    divisional = _safe_get(normalized, "divisional", {})
    vastu = _safe_get(normalized, "vastu", {})
    numerology = _safe_get(normalized, "numerology", {})

    # Build a short summary for the top of report: prefer GPT summary if present (first line),
    # otherwise infer from numerology/chart
    summary = ""
    if gpt_text:
        # take first 240 chars of GPT text as summary
        summary = (gpt_text.strip().split("\n\n")[0])[:240]
    else:
        summary_parts = []
        if numerology and numerology.get("life_path"):
            summary_parts.append(f"Life Path {numerology.get('life_path')}")
        asc = chart.get("ascendant")
        if asc:
            summary_parts.append(f"Ascendant {asc:.1f}°")
        summary = " • ".join(summary_parts) or "Personalized guidance based on chart, vastu, and numerology."

    html_out = tpl.render(
        title=title,
        css=css_use,
        gen_time=datetime.utcnow().isoformat() + "Z",
        person=person,
        chart=chart,
        divisional=divisional,
        vastu=vastu,
        numerology=numerology,
        gpt_text=gpt_text or "No interpretation available.",
        summary=summary,
    )
    return html_out


def save_report(normalized: Dict[str, Any], gpt_text: str, title: str = "Astro Vastu Pro Report", out_dir: Optional[str] = None, name_prefix: str = "report") -> Dict[str, str]:
    """
    Render and save HTML and PDF (if available) to disk.

    Returns a dict:
      {"html": "<path>", "pdf": "<path>" or None}
    """
    out_dir = out_dir or os.path.join(os.getcwd(), "reports")
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # safe filename prefix
    safe_prefix = "".join([c for c in name_prefix if c.isalnum() or c in ("-", "_")]).strip() or "report"
    timestr = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    html_path = Path(out_dir) / f"{safe_prefix}_{timestr}.html"
    pdf_path = Path(out_dir) / f"{safe_prefix}_{timestr}.pdf"

    html_content = render_report_html(normalized, gpt_text, title=title)
    html_path.write_text(html_content, encoding="utf-8")

    pdf_written = None
    if WEASYPRINT_AVAILABLE:
        try:
            HTML(string=html_content).write_pdf(str(pdf_path))
            pdf_written = str(pdf_path)
        except Exception as e:
            # fallback: don't raise here; return HTML only
            print("WeasyPrint PDF creation failed:", e)
            pdf_written = None

    return {"html": str(html_path), "pdf": pdf_written}


def generate_report_bytes(normalized: Dict[str, Any], gpt_text: str, as_pdf: bool = True) -> bytes:
    """
    Return report as bytes. If as_pdf and WeasyPrint available -> PDF bytes.
    Otherwise returns HTML bytes (utf-8).
    """
    html_content = render_report_html(normalized, gpt_text)
    if as_pdf and WEASYPRINT_AVAILABLE:
        try:
            pdf_bytes = HTML(string=html_content).write_pdf()
            return pdf_bytes
        except Exception as e:
            print("WeasyPrint render error:", e)
            # fall back to HTML bytes
    return html_content.encode("utf-8")


# -------------------------
# CLI demo
# -------------------------
if __name__ == "__main__":
    import json, sys

    print("Report Generator CLI demo")
    sample_norm = {
        "person": {"name": "Ravi Kumar", "date": "1990-01-01", "time": "06:30", "place": "Mumbai"},
        "chart": {"ascendant": 30.0, "planets": {"Sun": {"longitude": 45.0, "sign": "Taurus", "deg_in_sign": 15.0}, "Moon": {"longitude": 200.0, "sign": "Scorpio", "deg_in_sign": 20.0}}},
        "divisional": {
            "D9": {"Sun": {"sign": "Aries", "deg_in_sign": 5.0}, "Moon": {"sign": "Libra", "deg_in_sign": 12.0}},
            "D10": {"Sun": {"sign": "Leo", "deg_in_sign": 8.5}, "Moon": {"sign": "Aquarius", "deg_in_sign": 2.5}},
        },
        "vastu": {"plot_facing": "North", "weak_sectors": ["NW"], "recommended_activations": [{"sector": "NW", "action": "Place wind chimes", "why": "improves movement"}]},
        "numerology": {"life_path": 6, "name_vibration": 7, "personal_year": 9},
    }
    sample_gpt = "Summary: You have a strong Saturn influence; focus on stability and slow steady work...\n\n(A) Remedies: ...\n(B) Vastu: ...\n(C) Numerology: ..."

    res = save_report(sample_norm, sample_gpt, name_prefix="demo_report")
    print("Saved:", res)
    if res.get("pdf"):
        print("PDF created at:", res["pdf"])
    print("HTML created at:", res["html"])
