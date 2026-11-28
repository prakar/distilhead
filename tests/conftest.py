import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def toy(tmp_path) -> Path:
    dst = tmp_path / "toy"
    shutil.copytree(REPO / "packs" / "toy", dst, ignore=shutil.ignore_patterns("bar.lock"))
    return dst
