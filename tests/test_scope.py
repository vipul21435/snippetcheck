import ast

import pytest
from pyflakes import checker, messages
from scope_corpus import CORPUS

from snippetcheck.scope import analyse


def ours(src: str) -> tuple[set, set]:
    report = analyse(ast.parse(src))
    return ({(i.name, i.line) for i in report.undefined},
            {i.line for i in report.unused_imports})


def pyflakes(src: str) -> tuple[set, set]:
    found = checker.Checker(ast.parse(src), filename="<snippet>").messages
    undefined = {(m.message_args[0], m.lineno) for m in found
                 if isinstance(m, messages.UndefinedName)}
    unused = {m.lineno for m in found if isinstance(m, messages.UnusedImport)}
    return undefined, unused


def agreement(corpus: list[str]) -> tuple[float, float, list[str]]:
    same_undefined = same_unused = 0
    differ = []
    for src in corpus:
        (u1, i1), (u2, i2) = ours(src), pyflakes(src)
        same_undefined += u1 == u2
        same_unused += i1 == i2
        if u1 != u2:
            differ.append(src)
    return same_undefined / len(corpus), same_unused / len(corpus), differ


def test_agreement_with_pyflakes_on_corpus():
    undefined_rate, unused_rate, differ = agreement(CORPUS)
    print(f"\nprograms: {len(CORPUS)}, undefined-name agreement {undefined_rate:.3f}, "
          f"unused-import agreement {unused_rate:.3f}")
    # The one known difference: pyflakes lets a comprehension in a class body see the
    # class's names; Python does not (NameError at run time), and neither does snippetcheck.
    assert differ == ["class A:\n    k = 3\n    vals = [k for _ in range(2)]"]
    assert unused_rate == 1.0


@pytest.mark.parametrize(
    "src, expected",
    [
        ("print(y)\ny = 2", {"y"}),
        ("def f():\n    return later\n\nlater = 3", set()),
        ("class A:\n    x = 1\n    def m(self):\n        return x", {"x"}),
        ("squares = [n for n in range(3)]\nprint(n)", {"n"}),
        ("try:\n    maybe\nexcept NameError:\n    pass", set()),
        ("from math import *\nprint(sqrt(2))", set()),
        ("def f(x: 'Foo'):\n    return x\n\nclass Foo:\n    pass", set()),
        ("def f(x: 'Missing'):\n    return x", {"Missing"}),
    ],
)
def test_undefined_cases(src, expected):
    assert {i.name for i in analyse(ast.parse(src)).undefined} == expected


def test_unused_import_labels():
    report = analyse(ast.parse("import os\nfrom a.b import c as d\nimport sys\nsys.exit()"))
    assert [i.name for i in report.unused_imports] == ["os", "a.b.c as d"]


def test_extra_builtins():
    tree = ast.parse("display(df)\ndf = 1")
    assert {i.name for i in analyse(tree, extra_builtins={"display"}).undefined} == {"df"}
