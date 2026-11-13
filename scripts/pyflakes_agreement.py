"""Compare the undefined-name and unused-import analysis with pyflakes on real blocks.

    python scripts/pyflakes_agreement.py DATA.json [DATA2.json ...]

Needs pyflakes (in the dev extra). Both tools only parse the code. For every Python
block that parses, the sets of (name, line) pairs are compared; a block agrees when
the two sets are equal.
"""

from __future__ import annotations

import ast
import sys
import warnings

from pyflakes import checker, messages

from snippetcheck.extract import extract_blocks
from snippetcheck.pycheck import prepare
from snippetcheck.records import Record, iter_lines, read_jsonl
from snippetcheck.scope import analyse


def compare(path: str) -> None:
    blocks = same_undef = same_unused = 0
    ours_only = theirs_only = 0
    with open(path, encoding="utf-8") as handle:
        for item in read_jsonl(iter_lines(handle)):
            if not isinstance(item, Record):
                continue
            for turn in item.turns:
                for block in extract_blocks(turn.answer):
                    if block.lang != "python":
                        continue
                    prep = prepare(block.code)
                    if prep.skip:
                        continue
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        try:
                            tree = ast.parse(prep.source)
                        except (SyntaxError, ValueError, RecursionError, MemoryError):
                            continue
                        found = checker.Checker(tree, filename="<snippet>").messages
                    report = analyse(tree)
                    ours = {(i.name, i.line) for i in report.undefined}
                    theirs = {(m.message_args[0], m.lineno) for m in found
                              if isinstance(m, messages.UndefinedName)}
                    ours_unused = {i.line for i in report.unused_imports}
                    theirs_unused = {m.lineno for m in found
                                     if isinstance(m, messages.UnusedImport)}
                    blocks += 1
                    same_undef += ours == theirs
                    same_unused += ours_unused == theirs_unused
                    ours_only += bool(ours - theirs)
                    theirs_only += bool(theirs - ours)
    print(f"{path.rsplit('/', 1)[-1]}: {blocks} parsing Python blocks; "
          f"undefined names agree on {same_undef} ({100 * same_undef / blocks:.2f} %), "
          f"unused imports agree on {same_unused} ({100 * same_unused / blocks:.2f} %); "
          f"blocks with a name only snippetcheck reports: {ours_only}, "
          f"only pyflakes reports: {theirs_only}")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        compare(arg)
