"""
Proves python/llm/verify.py genuinely catches violations rather than trivially passing
everything -- same discipline as Phases 1-3's leak-plant/revert tests. One deliberately
broken fixture per check (unsupported number, unsupported segment, causal language), each
checked in isolation so a pass on one check can't hide a miss on another, plus a genuinely
clean summary that must pass all three, and the number/field-name tolerance decisions
documented in verify.py's own docstring.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from llm.client import StubClient  # noqa: E402
from llm.prompts import build_prompt  # noqa: E402
from llm.verify import (  # noqa: E402
    allowed_numbers,
    check_causal_language,
    check_unsupported_numbers,
    check_unsupported_segments,
    extract_numbers,
    verify_summary,
)

SEGMENT = {
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
ALL_SEGMENT_IDS = {0, 1, 2, 3}

CLEAN_SUMMARY = (
    "Segment 2 has 860 customers, about 16.5% of the customer base, and generates 68.1% of "
    "revenue. Average order frequency is 19.27 and average recency is 33.2 days. Predicted "
    "churn rate for this group is 15.3%, with a predicted value of $9,800.21 per customer "
    "over the next 245 days."
)

BROKEN_NUMBER_SUMMARY = (
    "Segment 2 has 860 customers and is worth an estimated $45,000.00 per customer over the "
    "next 245 days."
)

BROKEN_SEGMENT_SUMMARY = (
    "Segment 2 has 860 customers, performing similarly to segment 99's results last quarter."
)

BROKEN_CAUSAL_SUMMARY = (
    "Segment 2 has 860 customers. Churn is low because frequency is high, which drives "
    "predicted value up."
)


def test_extract_numbers_handles_dollar_percent_comma_decimal():
    text = "about $9,800.21 per customer, 15.3% churn, -2.5 adjustment"
    assert extract_numbers(text) == [9800.21, 15.3, -2.5]


def test_allowed_numbers_includes_percentage_form_and_field_name_digits():
    allowed = allowed_numbers(SEGMENT)
    assert 0.1532 in allowed  # raw churn rate
    assert any(abs(a - 15.32) < 1e-6 for a in allowed)  # x100 percentage form
    assert 245.0 in allowed  # embedded in the "predicted_clv_245d" field name, not a value


def test_clean_summary_passes_all_three_checks():
    result = verify_summary(CLEAN_SUMMARY, SEGMENT, ALL_SEGMENT_IDS)
    assert result["passed"] is True
    assert result["unsupported_numbers"] == []
    assert result["unsupported_segments"] == []
    assert result["causal_markers"] == []


def test_catches_unsupported_number():
    flagged = check_unsupported_numbers(BROKEN_NUMBER_SUMMARY, SEGMENT)
    assert 45000.0 in flagged
    result = verify_summary(BROKEN_NUMBER_SUMMARY, SEGMENT, ALL_SEGMENT_IDS)
    assert result["passed"] is False
    assert 45000.0 in result["unsupported_numbers"]


def test_catches_unsupported_segment_reference():
    flagged = check_unsupported_segments(BROKEN_SEGMENT_SUMMARY, ALL_SEGMENT_IDS)
    assert flagged == [99]
    result = verify_summary(BROKEN_SEGMENT_SUMMARY, SEGMENT, ALL_SEGMENT_IDS)
    assert result["passed"] is False
    assert result["unsupported_segments"] == [99]


def test_catches_causal_language():
    flagged = check_causal_language(BROKEN_CAUSAL_SUMMARY)
    assert "because" in flagged
    assert "drives" in flagged
    result = verify_summary(BROKEN_CAUSAL_SUMMARY, SEGMENT, ALL_SEGMENT_IDS)
    assert result["passed"] is False
    assert set(result["causal_markers"]) == {"because", "drives"}


def test_a_summary_that_passes_one_check_can_still_fail_another():
    # Clean on numbers and segments, but fails causal language -- proves the three checks
    # are independent, not short-circuited by an early pass.
    text = "Segment 2 has 860 customers. Value is high therefore it is a priority group."
    result = verify_summary(text, SEGMENT, ALL_SEGMENT_IDS)
    assert result["unsupported_numbers"] == []
    assert result["unsupported_segments"] == []
    assert result["causal_markers"] == ["therefore"]
    assert result["passed"] is False


def test_stub_broken_segment_output_fails_verification_end_to_end():
    broken_segment = {**SEGMENT, "segment_id": StubClient.BROKEN_SEGMENT_ID}
    prompt = build_prompt(broken_segment)
    output = StubClient().complete(prompt)
    result = verify_summary(output.text, broken_segment, ALL_SEGMENT_IDS)
    assert result["passed"] is False
    assert result["unsupported_numbers"]  # the $999,999.00 figure
    assert result["unsupported_segments"]  # the "segment 97" reference


def test_stub_good_segment_output_passes_verification_end_to_end():
    good_segment = {**SEGMENT, "segment_id": 2}  # not StubClient.BROKEN_SEGMENT_ID
    prompt = build_prompt(good_segment)
    output = StubClient().complete(prompt)
    result = verify_summary(output.text, good_segment, ALL_SEGMENT_IDS)
    assert result["passed"] is True
