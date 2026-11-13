import json
import math

import pytest

from snippetcheck.check import check_block, check_json, check_record
from snippetcheck.cli import main
from snippetcheck.extract import extract_blocks
from snippetcheck.records import read_jsonl
from snippetcheck.report import Z95, summarise, wilson_interval

FENCE = "`" * 3


def test_wilson_closed_form_edges():
    n = 10
    lo, hi = wilson_interval(0, n)
    assert lo == pytest.approx(0.0)
    assert hi == pytest.approx(Z95**2 / (n + Z95**2))
    lo, hi = wilson_interval(n, n)
    assert lo == pytest.approx(n / (n + Z95**2))
    assert hi == pytest.approx(1.0)


def test_wilson_symmetric_at_half():
    lo, hi = wilson_interval(50, 100)
    assert lo + hi == pytest.approx(1.0)
    # p = 0.5, n = 100: half-width z*sqrt(0.25/n + z^2/(4n^2)) / (1 + z^2/n)
    half = Z95 * math.sqrt(0.25 / 100 + Z95**2 / 40000) / (1 + Z95**2 / 100)
    assert hi - 0.5 == pytest.approx(half)


def test_wilson_empty_and_invalid():
    assert wilson_interval(0, 0) == (0.0, 1.0)
    with pytest.raises(ValueError):
        wilson_interval(3, 2)


def test_check_json_trailing_comma_and_truncation():
    [finding] = check_json('{"a": 1,}')
    assert finding.rule == "json-invalid"
    rules = {f.rule for f in check_json('{"a": [1, 2')}
    assert rules == {"json-invalid", "truncated"}
    assert check_json('{"a": [1, 2]}') == []


def test_unterminated_fence_finding():
    [block] = extract_blocks(f"{FENCE}python\nx = 1\n")
    result = check_block(block)
    assert [f.rule for f in result.findings] == ["unterminated-fence"]
    assert result.checker == "python"


def test_markdown_block_has_no_checker():
    [block] = extract_blocks(f"{FENCE}markdown\n# Title\n{FENCE}")
    assert check_block(block).checker is None


def _sample(tmp_path):
    rows = [
        {"id": 1, "instruction": "Square a number.", "input": "",
         "output": f"{FENCE}python\ndef square(x):\n    return x * x\n{FENCE}"},
        {"id": 2, "instruction": "Print.", "input": "",
         "output": f"{FENCE}python\nprint 'hi'\n{FENCE}"},
        {"id": 3, "instruction": "Explain.", "input": "", "output": "Plain prose only here."},
    ]
    path = tmp_path / "data.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    return path


def test_summary_counts(tmp_path):
    path = _sample(tmp_path)
    with open(path) as fh:
        results = [check_record(r) if not hasattr(r, "reason") else r for r in read_jsonl(fh)]
    summary = summarise(results)
    assert summary.records == 3
    assert summary.bad_lines == 1
    assert summary.blocks == 2
    assert summary.rules["py-syntax"].count == 1
    assert summary.rules["py-syntax"].units == 2
    assert summary.rules["py2-syntax"].examples == ["2#0.0"]


def test_cli_check_json(tmp_path, capsys):
    path = _sample(tmp_path)
    assert main(["check", str(path), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["records"] == 3
    assert data["rules"]["py-syntax"]["count"] == 1
    assert data["rules"]["py-syntax"]["share"] == 0.5


def test_cli_check_markdown(tmp_path, capsys):
    path = _sample(tmp_path)
    assert main(["check", str(path)]) == 0
    out = capsys.readouterr().out
    assert "| py2-syntax | 1 | 2 python blocks | 50.0 % |" in out


def test_cli_extract_filters_by_language(tmp_path, capsys):
    path = _sample(tmp_path)
    assert main(["extract", str(path), "--lang", "python"]) == 0
    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.out.splitlines()]
    assert [row["record"] for row in lines] == ["1", "2"]
    assert "line 4" in captured.err


def test_cli_explain(capsys):
    assert main(["explain"]) == 0
    assert "py-syntax" in capsys.readouterr().out
    assert main(["explain", "truncated"]) == 0
    assert "Counted over: checked blocks" in capsys.readouterr().out
    assert main(["explain", "nope"]) == 2


def test_cli_missing_file(tmp_path, capsys):
    assert main(["check", str(tmp_path / "missing.jsonl")]) == 2
