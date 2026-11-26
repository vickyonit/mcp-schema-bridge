import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe import classify  # noqa: E402
from providers import scrub  # noqa: E402


def test_classify_enforced_requires_violating_baseline_and_full_compliance() -> None:
    assert classify([False, False, True], [True, True, True]) == "enforced"


def test_classify_stripped_on_any_violation() -> None:
    assert classify([False, False], [True, False]) == "stripped"


def test_classify_inconclusive_when_baseline_never_violates() -> None:
    assert classify([True, True], [True, True]) == "inconclusive"


def test_classify_error_when_constrained_calls_fail() -> None:
    assert classify([False], [None]) == "error"


def test_scrub_removes_request_ids_and_long_tokens() -> None:
    s = scrub("bad request req_abc123XYZ for org-AbC123 key sk-" + "x" * 40)
    assert "req_abc123XYZ" not in s
    assert "org-AbC123" not in s
    assert "x" * 40 not in s
