from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
MODULES = FIXTURES / "modules"


@pytest.fixture
def modules_root() -> Path:
    return MODULES


@pytest.fixture
def identity_path(modules_root: Path) -> Path:
    return modules_root / "identity" / "guard.md"
