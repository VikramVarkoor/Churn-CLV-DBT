"""
Builds the per-segment prompt sent to the LLM. See docs/design.md, Phase 4 implementation
decisions: the prompt lists the segment's own numbers explicitly by name, so the model is
never asked to recall or guess them, and so the verification step (python/llm/verify.py) has
an unambiguous source of truth to check the response against.
"""

from __future__ import annotations

CAUSAL_MARKERS = [
    "because",
    "due to",
    "causes",
    "drives",
    "leads to",
    "results in",
    "so that",
    "therefore",
    "as a result",
]

SYSTEM_INSTRUCTIONS = (
    "You are writing a short, plain-language summary of one customer segment for a "
    "non-technical marketing reader. Use ONLY the numbers given below for this segment. Do "
    "not invent, estimate, or recall any number that is not given here. Do not mention any "
    "segment other than this one. Do not use causal language -- avoid words like "
    + ", ".join(f"'{m}'" for m in CAUSAL_MARKERS)
    + " -- describe what the numbers show, not why they are what they are. Keep it to 2-4 "
    "sentences."
)


def build_prompt(segment: dict) -> str:
    """`segment` is one entry from docs/evidence/segment_stats.json's "segments" list (a flat
    dict of field name -> already-rounded number). Every field is listed explicitly as
    `name: value` so both a real LLM and the deterministic StubClient (which parses these
    lines back out of the prompt) see exactly the same numbers, and so the verifier can check
    the response against this same source of truth."""
    lines = [SYSTEM_INSTRUCTIONS, "", "Segment data:"]
    for key, value in segment.items():
        lines.append(f"{key}: {value}")
    lines.append("")
    lines.append("Write the summary now.")
    return "\n".join(lines)
