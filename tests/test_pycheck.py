import pytest

from snippetcheck.pycheck import check_python, prepare, python2_markers, truncation_reason
from snippetcheck.scan import JSON, scan


def rules(code: str) -> set[str]:
    return {f.rule for f in check_python(code).findings}


def test_clean_code_has_no_findings():
    assert rules("def add(a, b):\n    return a + b\n\nprint(add(1, 2))") == set()


def test_syntax_error_class_and_position():
    [finding] = check_python("x = 1\nif x == 1\n    print(x)").findings
    assert finding.rule == "py-syntax"
    assert finding.detail.startswith("SyntaxError")
    assert finding.line == 2


def test_indentation_error_class():
    [finding] = check_python("def f():\n    x = 1\n      y = 2\n    return x").findings
    assert finding.detail.startswith("IndentationError")
    assert finding.line == 3


def test_tab_error_class():
    [finding] = check_python("if True:\n        x = 1\n\ty = 2").findings
    assert finding.detail.startswith("TabError")


@pytest.mark.parametrize(
    "code, marker",
    [
        ('print "hello"', "print statement"),
        ("x = 3\nprint x", "print statement"),
        ("try:\n    pass\nexcept ValueError, e:\n    pass", "'except X, e' clause"),
        ("raise ValueError, 'bad'", "'raise E, msg' statement"),
        ("if a <> b:\n    pass", "<> operator"),
        ("exec 'x = 1'", "exec statement"),
        ("mode = 0755", "octal literal"),
        ("n = 10L", "long integer literal"),
        ("s = ur'abc'", "ur'' string prefix"),
    ],
)
def test_python2_markers(code, marker):
    result = check_python(code)
    found = {f.rule: f for f in result.findings}
    assert "py-syntax" in found
    assert found["py2-syntax"].detail == marker


def test_markdown_inline_code_is_not_python2():
    found = {f.rule for f in check_python("The `swap` function first checks the input.").findings}
    assert "py2-syntax" not in found


def test_python2_markers_ignore_strings_and_comments():
    assert python2_markers("s = 'print x'  # print y <> z") == []


def test_valid_print_with_space_is_not_python2():
    assert rules("print (1)") == set()


def test_compile_error_return_outside_function():
    [finding] = check_python("x = 1\nreturn x").findings
    assert finding.rule == "py-compile"
    assert "outside function" in finding.message


def test_transcript_is_unwrapped():
    code = ">>> x = [1, 2]\n>>> for v in x:\n...     print(v)\n...\n1\n2\n>>> len(x)\n2"
    result = check_python(code)
    assert result.findings == []
    assert "interactive transcript unwrapped" in result.notes


def test_notebook_magics_are_neutralised():
    code = "%matplotlib inline\n!pip install numpy\nimport numpy as np\nx = np.arange(3)"
    result = check_python(code)
    assert result.findings == []
    assert "notebook magics replaced" in result.notes


def test_non_python_cell_magic_is_skipped():
    result = check_python("%%bash\necho hi\nls -l")
    assert result.skip == "cell magic %%bash"
    assert result.findings == []


def test_dedent_before_parse():
    assert rules("    x = 1\n    y = x + 1") == set()


@pytest.mark.parametrize(
    "code, reason",
    [
        ("def f(a, b):\n    return a +", "ends mid-statement"),
        ("result = compute(a,\n                 b", "ends with brackets still open"),
        ("items = [1, 2, 3,", "ends with brackets still open"),
        ("for i in range(", "ends with brackets still open"),
        ('doc = """Start of a docstring\nthat never ends', "ends inside a string"),
        ("name = 'unfinished", "ends inside a string"),
        ("class A:\n    def method(self):", "ends after a block header with no body"),
        ("total = price * \\", "ends mid-statement"),
    ],
)
def test_truncation_detected(code, reason):
    found = {f.rule: f for f in check_python(code).findings}
    assert "py-syntax" in found
    assert found["truncated"].detail == reason


@pytest.mark.parametrize(
    "code",
    [
        "print(foo(1)\nx = 2\ny = 3\nz = 4",  # missing paren in the middle
        "x = = 1\ny = 2",
        "def f(:\n    return 1",
        "def f():\n    return 1\nThis function doesn't do much",
        "def f():\n    # the body goes here",
        "for x in items:\n    total +=\nprint(total)\nThe loop adds every item to the total.",
    ],
)
def test_broken_but_not_truncated(code):
    found = rules(code)
    assert "py-syntax" in found
    assert "truncated" not in found


def test_truncation_reason_needs_text():
    assert truncation_reason("", None) is None


def test_scanner_masks_strings_and_comments():
    res = scan("a = '(' + \"[\"  # {\nb = (1,\n")
    assert res.open_brackets == [("(", 2, 4)]
    assert res.mismatched == []
    assert "(" not in res.masked.split("\n")[0]


def test_scanner_mismatch_and_open_string():
    res = scan("x = (1]\ny = '''abc")
    assert res.mismatched == [("]", 1, 6)]
    assert res.open_string == ("'''", 2, 4)


def test_scanner_json_syntax():
    res = scan('{"a": "b # not a comment", "c": [1, 2', JSON)
    assert [ch for ch, _, _ in res.open_brackets] == ["{", "["]


def test_prepare_keeps_line_numbers():
    prep = prepare("%time\nx = 1\n!ls\ny = 2")
    assert prep.source.split("\n") == ["pass", "x = 1", "pass", "y = 2"]


def test_undefined_and_unused_in_check():
    result = check_python("import os\nprint(xrange(3), value)")
    found = {(f.rule, f.detail) for f in result.findings}
    assert ("py-undefined-name", "xrange") in found
    assert ("py-undefined-name", "value") in found
    assert ("py-unused-import", "os") in found


def test_notebook_names_count_as_defined_only_in_notebook_code():
    assert "py-undefined-name" not in rules("%matplotlib inline\ndisplay(1)")
    assert "py-undefined-name" in rules("display(1)")


@pytest.mark.parametrize(
    "code, what",
    [
        ("def solve(nums):\n    pass", "function 'solve' has an empty body"),
        ("def solve(nums):\n    '''Return the answer.'''\n    ...",
         "function 'solve' has an empty body"),
        ("x = 1\n...", "'...' in place of code"),
        ("def f():\n    # your code here\n    return None", "placeholder text"),
        ("def f():\n    return 1  # TODO: implement properly", "placeholder text"),
    ],
)
def test_placeholders(code, what):
    found = [f for f in check_python(code).findings if f.rule == "placeholder"]
    assert [f.detail for f in found] == [what]


@pytest.mark.parametrize(
    "code",
    [
        "from abc import ABC, abstractmethod\nclass Shape(ABC):\n    @abstractmethod\n"
        "    def area(self):\n        pass",
        "class NotFound(Exception):\n    pass",
        "from typing import Protocol\nclass P(Protocol):\n    def run(self) -> None: ...",
        "from typing import overload\n@overload\ndef f(x: int) -> int: ...\n"
        "def f(x):\n    return x",
    ],
)
def test_legitimate_stubs_are_not_placeholders(code):
    assert "placeholder" not in rules(code)


@pytest.mark.parametrize(
    "code",
    [
        "total = " + " + ".join(["1"] * 500),
        "if x == 0:\n    y = 0\n"
        + "".join(f"elif x == {i}:\n    y = {i}\n" for i in range(1, 500)),
        "r = q" + ".f()" * 300,
    ],
)
def test_deep_but_valid_code_does_not_abort(code):
    result = check_python(code)
    assert "skipped: scope analysis (expression nested too deeply)" in result.notes
    assert not any(f.rule == "py-syntax" for f in result.findings)


def test_valid_python_is_not_rewritten():
    code = 'name = "x"\nmsg = ("Hello %s"\n       %name)'
    result = check_python(code)
    assert result.findings == [] and result.notes == []
    doc = 'def f(x):\n    """Double x.\n\n>>> f(1)\n2\n    """\n    return 2 * x'
    result = check_python(doc)
    assert result.findings == [] and result.notes == []
