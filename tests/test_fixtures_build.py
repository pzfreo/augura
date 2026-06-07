"""Smoke test: every declared fixture must build to a valid, non-empty solid.

This keeps the capability fixtures honest while their capability-specific
assertions are still waiting on the implementation (one tracking issue each).
"""

from __future__ import annotations

import pytest

from tests.fixtures import ALL, PartFixture


@pytest.mark.parametrize("fx", ALL, ids=lambda fx: fx.name)
def test_fixture_builds_to_valid_solid(fx: PartFixture) -> None:
    part = fx.build()
    assert part.volume > 0.0
    assert len(part.solids()) >= 1
