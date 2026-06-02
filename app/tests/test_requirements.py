from __future__ import annotations

from pathlib import Path


def test_requirements_use_httpx_not_httpx2():
    requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()

    assert "httpx" in requirements
    assert "httpx2" not in requirements
