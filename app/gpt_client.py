"""
gpt_client.py

Handles communication with GPT models (OpenAI or Azure endpoints) for AstroVastu Pro.
This module:
 - Builds system + user messages.
 - Sends the prompt created by prompt_builder.build_prompt().
 - Handles retries, errors, and response cleaning.
"""

import os
import time
import json
import openai
from typing import Dict, Any, Optional

# -----------------------------
# Configuration
# -----------------------------
# Make sure your environment variable is set:
#   setx OPENAI_API_KEY "sk-XXXX..."
openai.api_key = os.getenv("OPENAI_API_KEY")

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_RETRIES = 3
TEMPERATURE_DEFAULT = 0.6

# System message (AstroVastu Pro tone)
SYSTEM_PROMPT = """
You are **AstroVastu Pro**, an expert astrologer, vastu consultant, and numerologist.
Your goal is to provide calm, actionable, and spiritually aligned guidance.

Tone:
- Empathetic, encouraging, and insightful.
- Avoid fatalistic predictions.
- Use clear, professional language.
- Always end with a positive, empowering message.

Response Structure:
1. Summary of chart & numerology.
2. Observations (strengths, challenges).
3. Remedies:
   (A) Planetary / Dasha-based guidance
   (B) Vastu activations
   (C) Numerology corrections
4. Balanced Conclusion
"""

# -----------------------------
# Core functions
# -----------------------------
def call_gpt(prompt: str, model: Optional[str] = None, temperature: float = TEMPERATURE_DEFAULT) -> str:
    """
    Sends a message to the GPT model and returns the response text.
    Retries automatically on rate-limit or transient errors.
    """
    model = model or DEFAULT_MODEL
    if not openai.api_key:
        raise ValueError("OPENAI_API_KEY not found in environment. Please set it before running.")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.strip()},
        {"role": "user", "content": prompt.strip()},
    ]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=1500,
                top_p=1.0,
                presence_penalty=0.0,
                frequency_penalty=0.0,
            )

            # Extract message text (works for all OpenAI chat models)
            msg = response.choices[0].message.content.strip()
            return clean_response(msg)

        except openai.error.RateLimitError:
            wait_time = attempt * 2
            print(f"[GPT] Rate limit — retrying in {wait_time}s...")
            time.sleep(wait_time)
        except openai.error.APIConnectionError as e:
            print(f"[GPT] Connection error: {e}. Retrying...")
            time.sleep(2)
        except Exception as e:
            print(f"[GPT] Error on attempt {attempt}: {e}")
            if attempt == MAX_RETRIES:
                raise e
    raise RuntimeError("GPT request failed after maximum retries.")

def clean_response(text: str) -> str:
    """
    Cleans GPT output: trims repeated words, removes artifacts, ensures neat formatting.
    """
    text = text.replace("**", "")  # remove bold markers
    text = text.replace("##", "")
    text = text.strip()

    # Remove duplicate sections or disclaimers
    lines = text.splitlines()
    seen = set()
    cleaned_lines = []
    for ln in lines:
        if ln.strip() and ln.strip() not in seen:
            cleaned_lines.append(ln.strip())
            seen.add(ln.strip())
    return "\n".join(cleaned_lines)

# -----------------------------
# Combined helper
# -----------------------------
def interpret_normalized(normalized: Dict[str, Any], temperature: float = TEMPERATURE_DEFAULT) -> Dict[str, Any]:
    """
    Build prompt using prompt_builder and send to GPT model.
    Returns dict with {"prompt": ..., "response": ...}
    """
    from prompt_builder import build_prompt

    prompt = build_prompt(normalized)
    print("\n[Prompt Preview]\n", prompt[:600], "...\n")

    gpt_output = call_gpt(prompt, temperature=temperature)
    return {"prompt": prompt, "response": gpt_output}

# -----------------------------
# CLI test
# -----------------------------
if __name__ == "__main__":
    print("Testing GPT client...")
    from prompt_builder import build_prompt

    # Minimal sample data
    sample_norm = {
        "person": {"name": "Aarav Sharma", "date": "1990-01-01", "time": "06:30", "place": "Delhi"},
        "chart": {"ascendant": 45.0, "planets": {"Sun": {"longitude": 45.0}, "Moon": {"longitude": 190.0}}},
        "vastu": {"plot_facing": "North", "recommended_activations": [{"sector":"NE","action":"add bright light","why":"spiritual uplift"}]},
        "numerology": {"life_path": 5, "name_vibration": 9, "soul_urge": 3, "personality": 7, "personal_year": 8},
        "transits": {"transits":[{"planet":"Saturn","type":"square","natal_planet":"Sun","orb":1.5}]},
    }

    result = interpret_normalized(sample_norm, temperature=0.6)
    print("\n--- GPT OUTPUT ---\n")
    print(result["response"])
