"""
Tests for python/llm/prompts.py and python/llm/client.py. No warehouse or network needed.

Covers: build_prompt round-trips every field as `name: value` so StubClient's regex
extraction actually works; StubClient's "good" path restates exactly the numbers it was given
(no invention); StubClient's one deliberately-broken segment (BROKEN_SEGMENT_ID) really does
cite a number not in the input and a nonexistent segment, so the verifier (tested separately
in tests/test_phase4_verify.py) has something real to catch; and GroqClient refuses to
construct without GROQ_API_KEY set, so a live run can't silently proceed key-less.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from llm.client import GroqClient, StubClient  # noqa: E402
from llm.prompts import CAUSAL_MARKERS, build_prompt  # noqa: E402

SAMPLE_SEGMENT = {
    "segment_id": 2,
    "n_customers": 860,
    "share_of_customers": 0.1646,
    "share_of_revenue": 0.681,
    "mean_recency_days": 33.2,
    "mean_frequency": 19.27,
    "mean_monetary_net": 10314.8,
    "predicted_churn_rate": 0.1532,
    "predicted_clv_245d": 9800.21,
}

BROKEN_SEGMENT = {**SAMPLE_SEGMENT, "segment_id": StubClient.BROKEN_SEGMENT_ID}


def test_build_prompt_contains_every_field_as_name_value():
    prompt = build_prompt(SAMPLE_SEGMENT)
    for key, value in SAMPLE_SEGMENT.items():
        assert f"{key}: {value}" in prompt
    for marker in CAUSAL_MARKERS:
        assert marker in prompt  # listed in the instructions telling the model to avoid them


def test_stub_good_summary_restates_given_numbers_only():
    prompt = build_prompt(SAMPLE_SEGMENT)
    output = StubClient().complete(prompt)
    assert output.model == StubClient.MODEL_NAME
    assert output.temperature == 0.0
    assert str(SAMPLE_SEGMENT["n_customers"]) in output.text
    assert "999,999" not in output.text
    assert "segment 97" not in output.text.lower()
    for marker in CAUSAL_MARKERS:
        assert marker not in output.text.lower()


def test_stub_broken_segment_cites_unsupported_number_and_segment():
    prompt = build_prompt(BROKEN_SEGMENT)
    output = StubClient().complete(prompt)
    assert "999,999" in output.text or "999999" in output.text
    assert "97" in output.text  # references a segment id not in the JSON
    assert "999999" not in str(BROKEN_SEGMENT.values())  # confirms this number isn't real data


def test_groq_client_requires_api_key():
    env_backup = os.environ.pop("GROQ_API_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            GroqClient()
    finally:
        if env_backup is not None:
            os.environ["GROQ_API_KEY"] = env_backup
