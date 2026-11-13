"""Rule identifiers, what each one means, and the unit it is counted over."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """One problem found in one code block."""

    rule: str
    message: str
    line: int | None = None  # 1-based, relative to the block's code
    col: int | None = None  # 1-based
    detail: str = ""  # a short key for grouping, such as the syntax error class


@dataclass(frozen=True)
class Rule:
    id: str
    unit: str  # what the share is computed over: "python", "json", "fenced" or "checked"
    summary: str
    detail: str


_RULES = [
    Rule(
        "unterminated-fence",
        "fenced",
        "A code fence is opened and never closed.",
        "The answer ends inside a fenced block. This is the usual trace of a generation cut "
        "off at a token limit, though it can also be a missing closing fence after code that "
        "is otherwise complete.",
    ),
    Rule(
        "py-syntax",
        "python",
        "A Python block does not parse.",
        "ast.parse raised SyntaxError, IndentationError or TabError. The error class, message "
        "and position are reported. The grammar is that of the Python running snippetcheck, "
        "so syntax newer than that interpreter is reported as an error.",
    ),
    Rule(
        "py2-syntax",
        "python",
        "A Python block that does not parse uses Python 2 syntax.",
        "Recognised markers: the print statement, 'except X, e', 'raise E, msg', backtick "
        "repr, the <> operator, the exec statement, 0777 octal literals, 10L long literals "
        "and ur'' string prefixes. Only reported when the block also fails to parse.",
    ),
    Rule(
        "py-compile",
        "python",
        "A Python block parses but compile() rejects it.",
        "Errors the parser lets through and the compiler catches, such as 'return' outside "
        "a function or 'nonlocal' at module level. Snippets that show a function body "
        "without its def line land here.",
    ),
    Rule(
        "truncated",
        "checked",
        "The code stops mid-statement, inside a string or with brackets left open.",
        "Reported for a block that fails its parser when the failure is explained by the "
        "end of the text: the last line ends with an operator, a comma, a backslash or a "
        "block header with no body; a string is still open; or closing the open brackets "
        "makes the code parse.",
    ),
    Rule(
        "json-invalid",
        "json",
        "A JSON block does not parse.",
        "json.loads raised an error; the message and position are reported.",
    ),
]

RULES: dict[str, Rule] = {rule.id: rule for rule in _RULES}
