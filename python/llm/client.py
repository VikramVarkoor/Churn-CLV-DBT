"""
A single LLMClient interface with two implementations, per docs/design.md's Phase 4 lock:
StubClient (deterministic, offline, no network or API key) and GroqClient (the real Groq API).
The orchestration script (python/run_phase4.py) and the verification script
(python/llm/verify.py) are identical either way -- only which client is constructed changes,
selected by a --stub flag.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass
from typing import Optional, Protocol

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


@dataclass
class LLMOutput:
    """Every call records what produced it -- model name, the exact prompt sent, and the
    date -- alongside the text, per docs/design.md, so this is auditable later without
    re-running anything."""

    text: str
    model: str
    prompt: str
    generated_at: str
    temperature: float


class LLMClient(Protocol):
    def complete(self, prompt: str) -> LLMOutput: ...


def _extract_number(prompt: str, field: str) -> Optional[float]:
    """Pulls the value out of a `field: value` line in a prompt built by
    python/llm/prompts.py.build_prompt(). Used only by StubClient, which (deliberately) never
    sees the segment dict directly -- it only ever sees the same prompt text a real LLM would,
    so it cannot cheat by reading data the real model wouldn't have."""
    m = re.search(rf"^{re.escape(field)}:\s*(-?\d+\.?\d*)", prompt, re.MULTILINE)
    return float(m.group(1)) if m else None


class StubClient:
    """Deterministic, offline client for testing the Phase 4 pipeline without calling Groq.
    It extracts the segment's own numbers back out of the prompt text (the same text a real
    LLM would receive) and composes a template summary that restates exactly those numbers --
    no invented numbers, no causal language -- so it passes verification by construction for
    every segment except BROKEN_SEGMENT_ID.

    That one segment is deliberately given a broken response instead (a dollar figure not in
    its data, and a reference to a segment that does not exist), so an end-to-end sandbox run
    against this stub produces a realistic mixed pass/fail verification report rather than an
    all-pass run that would never have exercised the verifier's failure path. See
    tests/test_phase4_verify.py for the verifier being proven against this and other
    deliberately broken fixtures.
    """

    BROKEN_SEGMENT_ID = 1
    MODEL_NAME = "stub-deterministic-v1"

    def __init__(self) -> None:
        self.call_count = 0

    def complete(self, prompt: str) -> LLMOutput:
        self.call_count += 1
        segment_id = _extract_number(prompt, "segment_id")
        if segment_id is not None and int(segment_id) == self.BROKEN_SEGMENT_ID:
            text = self._broken_summary(segment_id)
        else:
            text = self._good_summary(prompt, segment_id)
        return LLMOutput(
            text=text,
            model=self.MODEL_NAME,
            prompt=prompt,
            generated_at=dt.date.today().isoformat(),
            temperature=0.0,
        )

    def _good_summary(self, prompt: str, segment_id: Optional[float]) -> str:
        n_customers = _extract_number(prompt, "n_customers")
        share_of_customers = _extract_number(prompt, "share_of_customers")
        share_of_revenue = _extract_number(prompt, "share_of_revenue")
        churn = _extract_number(prompt, "predicted_churn_rate")
        clv = _extract_number(prompt, "predicted_clv_245d")
        seg_label = "unknown" if segment_id is None else int(segment_id)
        return (
            f"Segment {seg_label} has {int(n_customers) if n_customers is not None else 'an unknown number of'} "
            f"customers, {share_of_customers * 100:.1f}% of the customer base, generating "
            f"{share_of_revenue * 100:.1f}% of revenue. Predicted churn rate is "
            f"{churn * 100:.1f}%, and predicted customer value over the next 245 days is "
            f"${clv:,.2f} per customer."
        )

    def _broken_summary(self, segment_id: float) -> str:
        # Deliberately broken: a dollar figure not present in this segment's data, and a
        # reference to a segment ID that does not exist in the JSON -- one example each of
        # the "unsupported number" and "unsupported segment" checks the verifier runs.
        return (
            f"Segment {int(segment_id)} is a standout group worth $999,999.00 in projected "
            "value, similar to segment 97's performance last quarter."
        )


class GroqClient:
    """Calls the real Groq API. Requires the `groq` package (python/requirements.txt) and a
    GROQ_API_KEY environment variable -- read at call time, never hardcoded or committed.
    Model is configurable via the GROQ_MODEL environment variable; defaults to
    llama-3.3-70b-versatile, one of Groq's current production chat models as checked against
    Groq's own docs (see docs/design.md)."""

    def __init__(self, model: Optional[str] = None) -> None:
        import groq  # imported here, not at module level, so StubClient usage never requires
        # the package to be installed or any network access

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Get a key at https://console.groq.com/keys and run "
                "`export GROQ_API_KEY=...` before using GroqClient -- see README.md's Phase 4 "
                "live-run instructions."
            )
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self._client = groq.Groq(api_key=api_key)

    def complete(self, prompt: str) -> LLMOutput:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        text = response.choices[0].message.content
        return LLMOutput(
            text=text,
            model=self.model,
            prompt=prompt,
            generated_at=dt.date.today().isoformat(),
            temperature=0.0,
        )
