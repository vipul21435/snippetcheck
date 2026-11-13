import json
import random
import shutil

import pytest

from snippetcheck.check import Options, check_block, check_record, check_records
from snippetcheck.cli import main
from snippetcheck.crosscheck import asks_for_code, language_mismatch, languages_asked
from snippetcheck.external import check_balance, unwrap_console
from snippetcheck.extract import extract_blocks
from snippetcheck.records import Record, Turn, iter_lines

FENCE = "`" * 3
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def rules_of(code: str, lang: str) -> set[str]:
    [block] = extract_blocks(f"{FENCE}{lang}\n{code}\n{FENCE}")
    return {f.rule for f in check_block(block).findings}


@needs_bash
def test_bash_n():
    assert rules_of("for f in *.txt; do\n  echo \"$f\"\ndone", "bash") == set()
    assert rules_of("if [ -f x ]; then\n  echo hi\n", "bash") == {"shell-syntax", "truncated"}
    assert rules_of("$ ls -la\ntotal 0\n$ echo done", "console") == set()


@needs_node
def test_node_check():
    assert rules_of("const add = (a, b) => a + b;\nconsole.log(add(1, 2));", "js") == set()
    assert rules_of("import fs from 'fs';\nexport const x = 1;", "js") == set()
    assert "js-syntax" in rules_of("function f( {\n  return 1;\n}", "js")
    assert rules_of("const xs = [1, 2,", "js") == {"js-syntax", "truncated"}


def test_external_checks_can_be_switched_off():
    [block] = extract_blocks(f"{FENCE}bash\nfi\n{FENCE}")
    result = check_block(block, options=Options(external=False))
    assert result.checker is None
    assert result.notes == ["skipped: external checks off"]


def test_unwrap_console():
    assert unwrap_console("$ ls\nfile.txt\n$ pwd") == "ls\n\npwd"
    assert unwrap_console("ls -la") == "ls -la"


def test_bracket_balance_other_languages():
    assert check_balance("int main() { return 0; }", "c") == []
    assert check_balance("// (\n/* { */ int x = 1;", "cpp") == []
    found = {f.rule for f in check_balance("public class A {\n  void f() {", "java")}
    assert found == {"unbalanced-brackets", "truncated"}
    [finding] = check_balance("fn main() { let x = (1]; }", "rust")
    assert finding.detail == "unmatched closing bracket"
    assert check_balance("fn f<'a>(x: &'a str) {}", "rust") == []
    assert check_balance("anything", "brainfuck") is None


def test_languages_asked():
    assert languages_asked("Write a Python function to sort a list") == {"python"}
    assert languages_asked("Write a JavaScript snippet") == {"javascript"}
    assert languages_asked("Write it in Java") == {"java"}
    assert languages_asked("Write a C++ program") == {"cpp"}
    assert languages_asked("Write a C program that prints") == {"c"}
    assert languages_asked("Explain closures") == set()


def test_language_mismatch():
    js = extract_blocks(f"{FENCE}js\nconsole.log(1)\n{FENCE}")
    py = extract_blocks(f"{FENCE}python\nprint(1)\n{FENCE}")
    bad, message, asked = language_mismatch("Write a Python function", js)
    assert bad and asked == "python" and "javascript" in message
    assert language_mismatch("Write a Python function", py)[0] is False
    assert language_mismatch("Write a function", js) is None
    shell_only = extract_blocks(f"{FENCE}bash\npip install x\n{FENCE}")
    assert language_mismatch("Install a Python package", shell_only) is None


def test_asks_for_code():
    assert asks_for_code("Write a function that reverses a string.")
    assert asks_for_code("Create a SQL query to count rows.")
    assert not asks_for_code("What is the capital of France?")


def test_no_code_and_mismatch_in_record():
    rec = Record("9", 1, "alpaca", (
        Turn("Write a Python function that adds two numbers.", "Just add them together."),
    ))
    result = check_record(rec)
    assert [(c.unit, c.finding.rule if c.finding else None) for c in result.turn_checks] == [
        ("asks-code", "no-code")]


def test_duplicate_blocks_across_records():
    code = f"{FENCE}python\ndef f(x):\n    y = x + 1\n    return y\n{FENCE}"
    recs = [Record(str(i), i, "alpaca", (Turn("q", code),)) for i in (1, 2, 3)]
    results = list(check_records(recs))
    flags = [[f.detail for b in r.blocks for f in b.findings if f.rule == "duplicate-block"]
             for r in results]
    assert flags == [[], ["1"], ["1"]]
    short = [Record(str(i), i, "alpaca", (Turn("q", f"{FENCE}python\nx = 1\n{FENCE}"),))
             for i in (1, 2)]
    assert all(not b.findings for r in check_records(short) for b in r.blocks)


def test_json_array_input():
    lines = list(iter_lines(['[{"instruction": "a", "output": "b"},\n', ' {"x": 1}]\n']))
    assert [json.loads(line) for line in lines] == [{"instruction": "a", "output": "b"},
                                                   {"x": 1}]
    assert list(iter_lines(['{"a": 1}\n', '{"b": 2}\n'])) == ['{"a": 1}\n', '{"b": 2}\n']


def _write(tmp_path, rows):
    path = tmp_path / "in.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_fix_drops_only_named_rules(tmp_path, capsys):
    rows = [
        {"id": 1, "instruction": "a", "output": f"{FENCE}python\nprint 'x'\n{FENCE}"},
        {"id": 2, "instruction": "b", "output": f"{FENCE}python\nimport os\n{FENCE}"},
        {"id": 3, "instruction": "c", "output": f"{FENCE}python\nprint('ok')\n{FENCE}"},
    ]
    src = _write(tmp_path, rows)
    out = tmp_path / "out.jsonl"
    assert main(["check", str(src), "--fix", str(out), "--drop", "py-syntax"]) == 0
    kept = [json.loads(line)["id"] for line in out.read_text().splitlines()]
    assert kept == [2, 3]
    assert "kept 2 records, dropped 1" in capsys.readouterr().err


def test_fix_and_drop_need_each_other(tmp_path):
    src = _write(tmp_path, [{"instruction": "a", "output": "b"}])
    assert main(["check", str(src), "--drop", "py-syntax"]) == 2
    assert main(["check", str(src), "--fix", str(tmp_path / "o.jsonl")]) == 2


def test_thresholds_set_exit_code(tmp_path):
    rows = [{"instruction": "a", "output": f"{FENCE}python\nprint 'x'\n{FENCE}"},
            {"instruction": "b", "output": f"{FENCE}python\nprint('x')\n{FENCE}"}]
    src = _write(tmp_path, rows)
    assert main(["check", str(src), "--max", "py-syntax=60%"]) == 0
    assert main(["check", str(src), "--max", "py-syntax=0.4"]) == 1
    with pytest.raises(SystemExit):
        main(["check", str(src), "--max", "nonsense=1"])


# -- fuzzing of the fence extractor --------------------------------------------------

_PIECES = ["```", "```python", "~~~", "~~~~ js", "````", "    ", "\t", "text", "x = (1,",
           "`", "``", "", "  ```", "- item", "1. step", "\r", "def f():", "    return 1"]


def _random_text(rng: random.Random) -> str:
    return "\n".join("".join(rng.choice(_PIECES) for _ in range(rng.randint(0, 3)))
                     for _ in range(rng.randint(0, 12)))


def test_fuzz_extractor_invariants():
    rng = random.Random(20261113)
    for _ in range(3000):
        text = _random_text(rng)
        blocks = extract_blocks(text)
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        starts = [b.start_line for b in blocks]
        assert starts == sorted(starts)
        for block in blocks:
            assert 1 <= block.start_line <= len(lines) + 1
            assert block.kind in {"fenced", "indented", "whole"}
            # every code line comes from the text, minus at most its leading indentation
            for code_line in block.code.split("\n"):
                assert any(line.endswith(code_line) for line in lines), (text, block)
        unterminated = [b for b in blocks if not b.terminated]
        assert len(unterminated) <= 1
        if unterminated:
            assert unterminated[0] is [b for b in blocks if b.kind == "fenced"][-1]


def test_fuzz_round_trip_of_generated_fences():
    rng = random.Random(7)
    for _ in range(500):
        bodies = [[f"v{rng.randint(0, 99)} = {rng.randint(0, 9)}"
                   for _ in range(rng.randint(1, 4))] for _ in range(rng.randint(1, 4))]
        parts = []
        for body in bodies:
            fence = rng.choice(["```", "~~~", "````"])
            parts.append(f"Some prose {rng.randint(0, 9)}.\n{fence}python\n"
                         + "\n".join(body) + f"\n{fence}")
        blocks = extract_blocks("\n".join(parts))
        assert [b.code.split("\n") for b in blocks] == bodies
        assert all(b.terminated and b.lang == "python" for b in blocks)
