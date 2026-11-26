import pytest

from mcp_schema_bridge.core.report import Report, ReportEntry, Severity, severity_at_least


def _entry(**kw: object) -> ReportEntry:
    base: dict[str, object] = {
        "rule": "core/x",
        "tid": "T1",
        "source_path": "",
        "keyword": "k",
        "action": "dropped",
        "severity": "info",
    }
    base.update(kw)
    return ReportEntry(**base)  # type: ignore[arg-type]


def test_severity_ordering() -> None:
    order: list[Severity] = ["info", "reversible", "lossy", "fatal"]
    for i, s in enumerate(order):
        for j, t in enumerate(order):
            assert severity_at_least(s, t) == (i >= j)


def test_entry_to_dict_has_all_fields_in_schema_shape() -> None:
    e = _entry(tool="t", target_path="/a", instance_path="/a", original=0, hinted=True, message="m")
    assert e.to_dict() == {
        "rule": "core/x",
        "tid": "T1",
        "tool": "t",
        "source_path": "",
        "target_path": "/a",
        "instance_path": "/a",
        "keyword": "k",
        "action": "dropped",
        "severity": "info",
        "original": 0,
        "hinted": True,
        "message": "m",
    }


def test_report_sorts_entries_totally_with_utf16_ordering() -> None:
    entries = [
        _entry(tool=None, source_path="/b"),
        _entry(tool="z", source_path="/a"),
        _entry(tool=None, source_path="/a", rule="core/b"),
        _entry(tool=None, source_path="/a", rule="core/a", keyword=None),
        _entry(tool=None, source_path="/a", rule="core/a", keyword="k", target_path="/2"),
        _entry(tool=None, source_path="/a", rule="core/a", keyword="k", target_path="/1"),
        _entry(tool=None, source_path="/\U0001f600"),
        _entry(tool=None, source_path="/דּ"),
    ]
    report = Report(target="openai-strict", entries=list(reversed(entries)))
    got = [(e.tool, e.source_path, e.rule, e.keyword, e.target_path) for e in report.sorted()]
    assert got == [
        (None, "/a", "core/a", None, None),
        (None, "/a", "core/a", "k", "/1"),
        (None, "/a", "core/a", "k", "/2"),
        (None, "/a", "core/b", "k", None),
        (None, "/b", "core/x", "k", None),
        (None, "/\U0001f600", "core/x", "k", None),
        (None, "/דּ", "core/x", "k", None),
        ("z", "/a", "core/x", "k", None),
    ]


def test_report_to_dict_envelope() -> None:
    report = Report(target="gemini-json", entries=[_entry()])
    d = report.to_dict(library_version="0.1.0", rules_version="2026.11.26")
    assert d["library_version"] == "0.1.0"
    assert d["rules_version"] == "2026.11.26"
    assert d["target"] == "gemini-json"
    assert d["entries"] == [_entry().to_dict()]


def test_report_max_severity_and_fatal() -> None:
    r = Report(target="openai", entries=[_entry(severity="lossy"), _entry(severity="info")])
    assert r.max_severity() == "lossy"
    assert not r.has_fatal()
    assert Report(target="openai", entries=[]).max_severity() is None


def test_invalid_severity_rejected() -> None:
    with pytest.raises(ValueError, match="severity"):
        _entry(severity="bad")
