"""
Deterministic verification of an LLM-generated segment summary against the segment stats
JSON it was supposed to be built from. See docs/design.md, "Verification": a summary passes
only if none of three checks fire -- an unsupported number, a reference to a segment ID not
in the JSON, or causal language.

Two implementation decisions not spelled out in docs/design.md's lock, made here and
documented rather than silently decided:

1. Percentage form. The design lock says every number must match "some number in that
   segment's JSON entry after rounding to the same precision the JSON was built at." A
   plain-language summary for a marketing reader will very likely express a rate or share
   (predicted_churn_rate=0.1532, say) as "15.3%", not "0.1532". So for any field whose raw
   value is a proportion (between -1 and 1), the allowed-number set includes BOTH the raw
   value and its x100 percentage form. This is a deliberate widening of "matches some number
   in the JSON", not a loosening of the three checks themselves.
2. Numbers embedded in field names. predicted_clv_245d's "245" is only ever given to the
   model via the field's own name (python/llm/prompts.py lists `predicted_clv_245d: <value>`
   verbatim) -- there is no separate `clv_horizon_days` field inside each segment's own JSON
   entry. A summary that says "...value over the next 245 days..." is citing a number the
   prompt genuinely gave it, just via a key name rather than a value, so digit runs found
   inside field names are added to the allowed-number set too.

Known limitation, left honest rather than hidden: regex-based number extraction cannot tell
"the top segment" (no extracted number) from "segment #1 captured 15% more" (extracts 15,
1) -- any number in the summary that isn't a genuine citation can still coincidentally match
an allowed value. This verifier is tuned to catch real violations (proven in
tests/test_phase4_verify.py against deliberately broken fixtures), not to be adversarially
unbeatable; it is a second check, not the only one, same as every leakage test in this project
being reported as what it tests, not as a perfect guarantee.
"""

from __future__ import annotations

import re

from llm.prompts import CAUSAL_MARKERS

NUMBER_PATTERN = re.compile(r"-?\$?\d[\d,]*\.?\d*%?")
SEGMENT_MENTION_PATTERN = re.compile(r"segment\s*#?\s*(\d+)", re.IGNORECASE)

# Numbers within this absolute OR relative tolerance of an allowed value are treated as a
# match, to absorb the LLM rounding differently than the JSON did (e.g. "15%" for 0.1532*100
# = 15.32, or "$9,800" for 9800.21).
ABS_TOLERANCE = 0.5
REL_TOLERANCE = 0.01


def extract_numbers(text: str) -> list[float]:
    """Numbers in `text`, handling a leading $, internal commas, decimals, and a trailing %
    (the % sign itself is stripped -- its value is compared as given, e.g. "15.3%" -> 15.3,
    matched against the percentage-form allowed values, not divided by 100 here)."""
    out = []
    for raw in NUMBER_PATTERN.findall(text):
        cleaned = raw.replace("$", "").replace(",", "").replace("%", "")
        if cleaned in ("", "-", "."):
            continue
        try:
            out.append(float(cleaned))
        except ValueError:
            continue
    return out


def _digits_in_field_names(segment: dict) -> set[float]:
    found = set()
    for key in segment:
        for m in re.findall(r"\d+", key):
            found.add(float(m))
    return found


def allowed_numbers(segment: dict) -> set[float]:
    """Every number this segment's own JSON entry legitimately gives the model: each field's
    raw value, the x100 percentage form for proportion-shaped fields, and digit runs embedded
    in field names (see module docstring, decisions 1 and 2)."""
    allowed: set[float] = set()
    for key, value in segment.items():
        if not isinstance(value, (int, float)):
            continue
        allowed.add(float(value))
        if -1.0 <= value <= 1.0:
            allowed.add(round(value * 100, 10))
    allowed |= _digits_in_field_names(segment)
    return allowed


def _matches_any(x: float, allowed: set[float]) -> bool:
    for a in allowed:
        tol = max(ABS_TOLERANCE, abs(a) * REL_TOLERANCE)
        if abs(x - a) <= tol:
            return True
    return False


def check_unsupported_numbers(text: str, segment: dict) -> list[float]:
    """Numbers in `text` that don't match any number this segment's JSON entry gives."""
    allowed = allowed_numbers(segment)
    return [x for x in extract_numbers(text) if not _matches_any(x, allowed)]


def check_unsupported_segments(text: str, valid_segment_ids: set) -> list[int]:
    """Segment IDs mentioned in `text` (patterns like "segment 3", "Segment #12") that are
    not a real key in the JSON at all -- per the design lock's literal wording. This does NOT
    flag a summary that correctly cites a different, real segment ID; the prompt separately
    instructs the model not to mention other segments at all, but that is a prompting
    instruction, not one of the three checks locked in docs/design.md, and is not enforced
    here. Noted as a real gap, not hidden."""
    valid = {int(v) for v in valid_segment_ids}
    mentioned = {int(m) for m in SEGMENT_MENTION_PATTERN.findall(text)}
    return sorted(mentioned - valid)


def check_causal_language(text: str) -> list[str]:
    lower = text.lower()
    return [marker for marker in CAUSAL_MARKERS if marker in lower]


def verify_summary(text: str, segment: dict, valid_segment_ids: set) -> dict:
    """Runs all three checks. `passed` is True only if all three come back empty."""
    unsupported_numbers = check_unsupported_numbers(text, segment)
    unsupported_segments = check_unsupported_segments(text, valid_segment_ids)
    causal_markers = check_causal_language(text)
    return {
        "segment_id": segment.get("segment_id"),
        "passed": not (unsupported_numbers or unsupported_segments or causal_markers),
        "unsupported_numbers": unsupported_numbers,
        "unsupported_segments": unsupported_segments,
        "causal_markers": causal_markers,
    }
