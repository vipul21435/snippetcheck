import shutil
from pathlib import Path

import pytest

from snippetcheck.cli import main

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("bash") is None, reason="the sample has a shell block")
def test_readme_quickstart_matches_a_real_run(capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    assert main(["check", "examples/sample.jsonl"]) == 0
    out = capsys.readouterr().out
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert out in readme
