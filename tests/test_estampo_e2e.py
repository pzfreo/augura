"""Tests for the estampo.toml output adapter (operates on a Report)."""

from __future__ import annotations

from augura import Finding, Report, Severity, to_estampo_toml


def test_overhang_and_brim_report_emits_support_and_brim() -> None:
    report = Report(
        findings=(
            Finding(kind="overhang", severity=Severity.WARNING, message="needs support"),
            Finding(kind="brim", severity=Severity.WARNING, message="recommend a brim"),
        )
    )

    out = to_estampo_toml(report)
    assert "enable_support = true" in out
    assert 'brim_type = "brim"' in out


def test_clean_report_emits_no_support_no_brim() -> None:
    out = to_estampo_toml(Report())
    assert "enable_support = false" in out
    assert "brim_type" not in out
