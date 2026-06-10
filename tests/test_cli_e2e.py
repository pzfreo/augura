"""End-to-end CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from build123d import Box, Pos, export_step, export_stl

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


@pytest.fixture
def upside_down_t(tmp_path: Path) -> Path:
    # An upside-down T: the plate's underside ring overhangs as imported, and
    # flipping 180 deg (plate on the bed) is the only candidate with none.
    path = tmp_path / "upside_down_t.step"
    export_step(Box(5, 5, 10) + Pos(0, 0, 7.5) * Box(20, 20, 5), path)
    return path


@pytest.fixture
def tall_t(tmp_path: Path) -> Path:
    # A tall T: flipped plate-down it is overhang-free but 55 mm tall; on its
    # side it fits a 40 mm-Z volume at the cost of supporting the stem.
    path = tmp_path / "tall_t.step"
    export_step(Box(5, 5, 50) + Pos(0, 0, 27.5) * Box(30, 30, 5), path)
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


def test_analyze_estampo_clean(step_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", str(step_box), "--format", "estampo"]) == 0
    out = capsys.readouterr().out
    assert "from box.step" in out  # provenance in the header comment
    assert "enable_support = false" in out
    assert 'brim_type = "no_brim"' in out
    assert "[slicer.overrides]" not in out  # clean report -> minimal fragment


def test_analyze_estampo_with_findings(step_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A 20 mm box can't fit a 5 mm build volume -> bed-fit advisory.
    cmd = ["analyze", str(step_box), "--format", "estampo", "--build-volume", "5", "5", "5"]
    assert main(cmd) == 0
    out = capsys.readouterr().out
    assert "[slicer.overrides]" in out
    assert "exceeds build volume" in out


def test_analyze_estampo_best_orientation(
    upside_down_t: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["analyze", str(upside_down_t), "--format", "estampo"]
    assert main(base) == 0
    assert "enable_support = true" in capsys.readouterr().out  # as imported

    assert main([*base, "--best-orientation"]) == 0
    out = capsys.readouterr().out
    # The fragment must emit the flip AND describe the flipped part.
    assert "orient = [180, 0, 0]" in out
    assert "enable_support = false" in out


def test_best_orientation_text_json_md(
    upside_down_t: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Every format must report the flip and the flipped part's (clean) findings.
    base = ["analyze", str(upside_down_t), "--best-orientation"]

    assert main(base) == 0  # text is the default
    out = capsys.readouterr().out
    assert "analysed at rotation [180, 0, 0]" in out
    assert "No printability issues found" in out

    assert main([*base, "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rotation"] == [180, 0, 0]
    assert data["findings"] == []

    assert main([*base, "--format", "md"]) == 0
    out = capsys.readouterr().out
    assert "analysed at rotation [180, 0, 0]" in out
    assert "No printability issues found" in out


def test_analyze_orient_explicit(upside_down_t: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A user-chosen pose (e.g. picked from `augura orientations`) flows through
    # the same rotate-and-analyse path as --best-orientation.
    cmd = ["analyze", str(upside_down_t), "--format", "estampo", "--orient", "180", "0", "0"]
    assert main(cmd) == 0
    out = capsys.readouterr().out
    assert "orient = [180, 0, 0]" in out
    assert "enable_support = false" in out


def test_orient_and_best_orientation_are_exclusive(step_box: Path) -> None:
    with pytest.raises(SystemExit):
        main(["analyze", str(step_box), "--best-orientation", "--orient", "0", "0", "0"])


def test_best_orientation_prefers_pose_that_fits(
    tall_t: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["analyze", str(tall_t), "--format", "estampo", "--best-orientation"]

    assert main(base) == 0
    assert "orient = [180, 0, 0]" in capsys.readouterr().out  # unconstrained: flip wins

    assert main([*base, "--build-volume", "60", "60", "40"]) == 0
    out = capsys.readouterr().out
    assert "orient = [180, 0, 0]" not in out  # the 55 mm flip doesn't fit
    assert "exceeds build volume" not in out  # the chosen pose does


def test_orientations_build_volume(tall_t: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The orientations frontier must rank with the same feasibility-first key
    # --best-orientation uses, and say which poses fit.
    cmd = ["orientations", str(tall_t), "--format", "json", "--build-volume", "60", "60", "40"]
    assert main(cmd) == 0
    data = json.loads(capsys.readouterr().out)
    first = data["orientations"][0]
    assert first["fits_build_volume"] is True
    assert first["rotation"] != [180, 0, 0]  # the 55 mm flip is demoted

    assert main(["orientations", str(tall_t), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "fits_build_volume" not in data["orientations"][0]  # not asked for

    assert main(["orientations", str(tall_t), "--build-volume", "60", "60", "40"]) == 0
    assert "(exceeds build volume)" in capsys.readouterr().out  # text marks misfits


def test_json_without_best_orientation_has_no_rotation_key(
    step_box: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["analyze", str(step_box), "--format", "json"]) == 0
    assert "rotation" not in json.loads(capsys.readouterr().out)


def test_best_orientation_rejects_mesh(stl_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cmd = ["analyze", str(stl_box), "--format", "estampo", "--best-orientation"]
    assert main(cmd) == 2
    assert "mesh" in capsys.readouterr().err


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
    first = data["orientations"][0]
    assert "rotation" in first
    assert "overhang_area" in first
    assert "z_height_mm" in first
    assert "bed_contact_mm2" in first


def test_orientations_text_and_md(step_box: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["orientations", str(step_box)]) == 0
    out = capsys.readouterr().out
    assert "best first" in out
    assert "mm tall" in out
    assert main(["orientations", str(step_box), "--format", "md"]) == 0
    out = capsys.readouterr().out
    assert "| Rank |" in out
    assert "Z-height" in out


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
