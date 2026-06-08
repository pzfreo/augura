"""Integration test: the shared fixtures, round-tripped through the CLI.

Exports each ``tests/fixtures`` part to a real STEP file and runs it through the
``augura`` CLI (load -> analyze -> render), exercising the full pipeline against
the curated geometry — not just the Python ``analyze()`` API.

Assertions are at the *finding-kind* level: a STEP export/import round-trip can
nudge a borderline value (e.g. the cantilever's exactly-45 deg chamfer), so we
check that the right capability fires, not byte-exact numbers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from build123d import export_step

from augura.cli import main
from tests.fixtures import ALL, PartFixture


def _by_name(name: str) -> PartFixture:
    return next(fx for fx in ALL if fx.name == name)


def _analyze_json(
    fx: PartFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str], *extra: str
) -> dict[str, Any]:
    path = tmp_path / f"{fx.name}.step"
    export_step(fx.build(), path)
    rc = main(["analyze", str(path), "--format", "json", *extra])
    data: dict[str, Any] = json.loads(capsys.readouterr().out)
    data["_rc"] = rc
    data["_source"] = path.name
    return data


@pytest.mark.parametrize("fx", ALL, ids=lambda fx: fx.name)
def test_cli_round_trips_every_fixture(
    fx: PartFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _analyze_json(fx, tmp_path, capsys)
    assert data["_rc"] == 0
    assert data["source"] == data["_source"]
    assert isinstance(data["findings"], list)


@pytest.mark.parametrize(
    ("fx_name", "expected_kind"),
    [
        ("cantilever_bracket", "overhang"),
        ("tipping_mast", "tip_over"),
        ("tall_thin_pin", "brim"),
        ("thin_wall_tube", "thin_wall"),
        ("thin_lamina_block", "min_feature"),
    ],
)
def test_cli_reports_expected_kind(
    fx_name: str, expected_kind: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _analyze_json(_by_name(fx_name), tmp_path, capsys)
    assert data["_rc"] == 0
    assert expected_kind in {f["kind"] for f in data["findings"]}


def test_cli_bed_fit_and_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # oversized_plate (350x350) can't fit a 256^3 volume -> bed-fit ERROR -> exit 1.
    data = _analyze_json(
        _by_name("oversized_plate"),
        tmp_path,
        capsys,
        "--build-volume",
        "256",
        "256",
        "256",
        "--exit-code",
    )
    assert data["_rc"] == 1
    assert "bed_fit" in {f["kind"] for f in data["findings"]}
