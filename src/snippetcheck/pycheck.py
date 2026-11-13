"""Static checks for Python blocks. Nothing here imports or executes the code."""

from __future__ import annotations

import ast
import io
import re
import textwrap
import tokenize
import warnings
from dataclasses import dataclass, field

from .rules import Finding
from .scan import ScanResult, scan
from .scope import PYTHON2_BUILTINS, analyse

NOTEBOOK_NAMES = frozenset({"display", "get_ipython", "In", "Out"})
_PLACEHOLDER_TEXT = re.compile(
    r"(?i)\b(your (own )?(code|implementation|solution|logic) (goes )?here|"
    r"(insert|add|write|put|place) (your )?code here|code goes here|implement (this|me)\b|"
    r"todo:?\s*implement|rest of (the|your) code|fill in (the|your) code)"
)
_STUB_EXEMPT_DECORATORS = {"abstractmethod", "abstractproperty", "overload", "abstractclassmethod",
                           "abstractstaticmethod"}
_STUB_EXEMPT_BASES = {"Protocol", "ABC", "ABCMeta", "Exception", "BaseException"}

_LINE_MAGIC = re.compile(r"^(?P<indent>\s*)(%|!)(?!=)\S")
_CELL_MAGIC = re.compile(r"^\s*%%(?P<name>\w+)(?P<args>.*)$")
_HELP_LINE = re.compile(r"^(?P<indent>\s*)[\w.]+\?{1,2}\s*$")
_PYTHON_CELLS = {"time", "timeit", "capture", "prun", "debug", "autoreload"}

_PY2_MARKERS: list[tuple[str, re.Pattern[str]]] = [
    ("print statement",
     re.compile(r"^\s*print\s+(?![\s=(.\[,)+\-*/%<>!&|^:;]|$)\S|^\s*print\s*>>")),
    ("'except X, e' clause", re.compile(r"^\s*except\s+(\([^)]*\)|[\w.]+)\s*,\s*\w+\s*:")),
    ("'raise E, msg' statement", re.compile(r"^\s*raise\s+[\w.]+\s*,")),
    ("backtick repr", re.compile(r"`")),
    ("<> operator", re.compile(r"<>")),
    ("exec statement", re.compile(r"^\s*exec\s+[\"'\w]")),
    ("octal literal", re.compile(r"(?<![\w.])0[0-7]*[1-7][0-7]*(?![\w.])")),
    ("long integer literal", re.compile(r"(?<![\w.])\d+[lL](?!\w)")),
    ("ur'' string prefix", re.compile(r"(?<!\w)[uU][rR][\"']")),
]

_HEADER = re.compile(
    r"^\s*(async\s+)?(def|class|if|elif|else|for|while|try|except|finally|with|match|case)\b"
    r".*:\s*$"
)
_DANGLING = re.compile(
    r"(\\|[-+*/%=<>&|^,.@~]|:=|\b(and|or|not|in|is|if|else|lambda|import|from|assert|del|"
    r"global|nonlocal|as|await))\s*$"
)
_CLOSER = {"(": ")", "[": "]", "{": "}"}


@dataclass
class Prepared:
    source: str
    notes: list[str] = field(default_factory=list)
    skip: str = ""  # non-empty when the block is not Python after all


def prepare(code: str) -> Prepared:
    """Dedent, unwrap a ``>>>`` transcript and neutralise notebook magics.

    Line numbers are preserved: removed lines become blank lines and magics become
    ``pass`` at the same indentation.
    """
    src = textwrap.dedent(code.replace("\r\n", "\n"))
    lines = src.split("\n")
    notes: list[str] = []
    if any(line.startswith(">>>") for line in lines):
        lines = _unwrap_transcript(lines)
        notes.append("interactive transcript unwrapped")
    first = next((line for line in lines if line.strip()), "")
    cell = _CELL_MAGIC.match(first)
    if cell:
        name, args = cell.group("name"), cell.group("args").strip()
        if name == "writefile" and not args.endswith(".py"):
            return Prepared(src, notes, skip=f"cell magic %%writefile {args}".strip())
        if name not in _PYTHON_CELLS and name != "writefile":
            return Prepared(src, notes, skip=f"cell magic %%{name}")
    out = []
    for line in lines:
        magic = _LINE_MAGIC.match(line) or _HELP_LINE.match(line)
        if magic:
            out.append(magic.group("indent") + "pass")
            if "notebook magics replaced" not in notes:
                notes.append("notebook magics replaced")
        else:
            out.append(line)
    return Prepared("\n".join(out), notes)


def _unwrap_transcript(lines: list[str]) -> list[str]:
    out: list[str] = []
    in_prompt = False
    for line in lines:
        if line.startswith(">>> ") or line == ">>>":
            out.append(line[4:])
            in_prompt = True
        elif in_prompt and (line.startswith("... ") or line == "..."):
            out.append(line[4:])
        else:
            out.append("")  # interpreter output
            in_prompt = False
    return out


def _parse(src: str) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(src)


def _parses(src: str) -> bool:
    try:
        _parse(src)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False
    return True


def _error_key(exc: BaseException) -> str:
    msg = getattr(exc, "msg", None) or str(exc)
    msg = re.sub(r"\s*\(detected at line \d+\)", "", msg)
    msg = re.sub(r" on line \d+", "", msg)
    return f"{type(exc).__name__}: {msg}"


def python2_markers(src: str, scanned: ScanResult | None = None) -> list[tuple[str, int]]:
    """Return (marker, line) for each Python 2 construct found outside strings and comments."""
    masked = (scanned or scan(src)).masked
    found: list[tuple[str, int]] = []
    for lineno, line in enumerate(masked.split("\n"), start=1):
        for name, pattern in _PY2_MARKERS:
            if pattern.search(line):
                found.append((name, lineno))
    return found


def truncation_reason(src: str, error_line: int | None,
                      scanned: ScanResult | None = None) -> tuple[str, int] | None:
    """Explain a parse failure by the end of the text, or return None.

    Returns (reason, line). ``error_line`` is the line the parser reported.
    """
    res = scanned or scan(src)
    masked_lines = res.masked.split("\n")
    last = max((i for i, line in enumerate(masked_lines, 1) if line.strip()), default=0)
    if last == 0:
        return None
    if res.open_string is not None:
        return "ends inside a string", res.open_string[1]
    if res.broken_strings and res.broken_strings[-1][0] == last:
        return "ends inside a string", last
    if res.open_brackets and not res.mismatched:
        if _closing_brackets_parses(src, res) or res.open_brackets[-1][1] == last:
            return "ends with brackets still open", res.open_brackets[-1][1]
        return None
    if error_line is not None and error_line < last:
        return None
    tail = masked_lines[last - 1].rstrip()
    if _HEADER.match(tail):
        return "ends after a block header with no body", last
    if _DANGLING.search(tail):
        return "ends mid-statement", last
    return None


def _closing_brackets_parses(src: str, res: ScanResult) -> bool:
    cut = len(res.masked.rstrip())
    base = src[:cut]
    closers = "".join(_CLOSER[ch] for ch, _, _ in reversed(res.open_brackets))
    first_line = src.split("\n")[res.open_brackets[0][1] - 1]
    body_indent = first_line[: len(first_line) - len(first_line.lstrip())] + "    "
    for filler in ("", " 0", " x"):
        for tail in ("", ":\n" + body_indent + "pass", "\n" + body_indent + "pass"):
            if _parses(base + filler + closers + tail):
                return True
    return False


@dataclass
class PythonResult:
    findings: list[Finding]
    notes: list[str]
    skip: str = ""
    tree: ast.Module | None = None


def check_python(code: str) -> PythonResult:
    """Run the Python checks on one block."""
    prep = prepare(code)
    if prep.skip:
        return PythonResult([], prep.notes, skip=prep.skip)
    src = prep.source
    findings: list[Finding] = []
    try:
        tree = _parse(src)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        line = getattr(exc, "lineno", None)
        col = getattr(exc, "offset", None)
        key = _error_key(exc)
        where = f" at line {line}" if line else ""
        findings.append(Finding("py-syntax", f"{key}{where}", line, col, detail=key))
        scanned = scan(src)
        markers = python2_markers(src, scanned)
        if markers:
            name, mline = markers[0]
            findings.append(Finding("py2-syntax", f"Python 2 {name} at line {mline}", mline,
                                    detail=name))
        reason = truncation_reason(src, line, scanned)
        if reason is not None:
            text, rline = reason
            findings.append(Finding("truncated", f"{text} (line {rline})", rline, detail=text))
        return PythonResult(findings, prep.notes)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            compile(tree, "<snippet>", "exec", dont_inherit=True)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        line = getattr(exc, "lineno", None)
        key = _error_key(exc)
        where = f" at line {line}" if line else ""
        findings.append(Finding("py-compile", f"{key}{where}", line,
                                getattr(exc, "offset", None), detail=key))
    extra = NOTEBOOK_NAMES if prep.notes else frozenset()
    try:
        report = analyse(tree, extra)
    except RecursionError:
        notes = prep.notes + ["skipped: scope analysis (expression nested too deeply)"]
        return PythonResult(findings, notes, tree=tree)
    for issue in report.undefined:
        note = " (a Python 2 builtin)" if issue.name in PYTHON2_BUILTINS else ""
        findings.append(Finding("py-undefined-name",
                                f"undefined name '{issue.name}'{note} at line {issue.line}",
                                issue.line, issue.col, detail=issue.name))
    for issue in report.unused_imports:
        findings.append(Finding("py-unused-import",
                                f"'{issue.name}' imported but unused at line {issue.line}",
                                issue.line, issue.col, detail=issue.name))
    for what, line in placeholders(tree, src):
        findings.append(Finding("placeholder", f"{what} at line {line}", line, detail=what))
    return PythonResult(findings, prep.notes, tree=tree)


def _is_stub_body(body: list[ast.stmt]) -> bool:
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return all(
        isinstance(stmt, ast.Pass)
        or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is Ellipsis)
        for stmt in body
    )


def _name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        return _name_of(node.value)
    return ""


def placeholders(tree: ast.Module, src: str) -> list[tuple[str, int]]:
    """Find stub bodies, a bare ``...`` standing for omitted code, and "your code here"."""
    found: list[tuple[str, int]] = []
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            names = {_name_of(b) for b in node.bases} | {_name_of(k.value) for k in node.keywords}
            if names & _STUB_EXEMPT_BASES or any(n.endswith(("Error", "Exception"))
                                                  for n in names):
                exempt.update(id(child) for child in node.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and id(node) not in exempt:
            decorators = {_name_of(d) for d in node.decorator_list}
            if not decorators & _STUB_EXEMPT_DECORATORS and _is_stub_body(node.body):
                found.append((f"function '{node.name}' has an empty body", node.lineno))
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                and stmt.value.value is Ellipsis:
            found.append(("'...' in place of code", stmt.lineno))
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING) and _PLACEHOLDER_TEXT.search(
                    tok.string):
                found.append(("placeholder text", tok.start[0]))
    except (tokenize.TokenError, SyntaxError):
        pass
    found.sort(key=lambda item: item[1])
    return found
