"""End-to-end CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from build123d import Box, export_step, export_stl

from augura.cli import main


@pytest.fixture
def step_box(tmp_path: Path) -> Path:
    path = tmp_path / "box.step"
    export_step(Box(20, 20, 10), path)
    return path


@pytest.fixture
def stl_box(tmp_path: Path) -> Path:
    path = tmp_path / "box.stl"
    export_stl(Box(20, 20, 10), path)
    return path


def test_analyze_text_clean(step_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", str(step_box)]) == 0
    assert "No printability issues found" in capsys.readouterr().out


def test_analyze_json(step_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", str(step_box), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["source"] == "box.step"
    assert data["findings"] == []


def test_analyze_md_clean(step_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", str(step_box), "--format", "md"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# augura report")
    assert "No printability issues found" in out


def test_analyze_md_with_findings(step_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A 20 mm box can't fit a 5 mm build volume -> bed-fit ERROR.
    assert main(["analyze", str(step_box), "--format", "md", "--build-volume", "5", "5", "5"]) == 0
    out = capsys.readouterr().out
    assert "| Severity | Check | Detail |" in out
    assert "bed_fit" in out


def test_exit_code_on_error(step_box: Path) -> None:
    over = ["analyze", str(step_box), "--build-volume", "5", "5", "5"]
    assert main([*over, "--exit-code"]) == 1
    assert main(over) == 0  # same findings, but no --exit-code


def test_analyze_stl_mesh_path(stl_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", str(stl_box)]) == 0
    assert "box.stl" in capsys.readouterr().out


def test_orientations_json(step_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["orientations", str(step_box), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["orientations"]
    assert "rotation" in data["orientations"][0]


def test_orientations_text_and_md(step_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["orientations", str(step_box)]) == 0
    assert "best first" in capsys.readouterr().out
    assert main(["orientations", str(step_box), "--format", "md"]) == 0
    assert "| Rank |" in capsys.readouterr().out


def test_orientations_rejects_mesh(stl_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["orientations", str(stl_box)]) == 2
    assert "mesh" in capsys.readouterr().err


def test_unsupported_extension(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "thing.txt"
    bad.write_text("nope")
    assert main(["analyze", str(bad)]) == 2
    assert "unsupported" in capsys.readouterr().err


def test_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", str(tmp_path / "nope.step")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_corrupt_file_is_reported_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A garbage STL must produce a clean error + exit 2, never a traceback.
    bad = tmp_path / "garbage.stl"
    bad.write_bytes(b"not a real stl \x00\x01\x02")
    assert main(["analyze", str(bad)]) == 2
    assert "augura:" in capsys.readouterr().err
