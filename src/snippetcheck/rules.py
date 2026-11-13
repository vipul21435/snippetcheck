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
        "py-undefined-name",
        "python",
        "A Python block uses a name it never defines or imports.",
        "From a scope analysis of the AST (module and class bodies in order, function bodies "
        "after the enclosing body, class scopes skipped from functions, comprehension scopes, "
        "global/nonlocal, star imports, NameError guards, string annotations). Builtins of the "
        "running Python count as defined, Python 2 builtins such as xrange do not. Only for "
        "blocks that parse. A snippet that refers to a variable named in the prompt is "
        "flagged too: the check reads the code alone.",
    ),
    Rule(
        "py-unused-import",
        "python",
        "A Python block imports a name it never uses.",
        "From the same scope analysis. 'from __future__' imports are never reported, and an "
        "unused import that is rebound (as in a try/except ImportError fallback) counts as a "
        "redefinition, not as unused.",
    ),
    Rule(
        "placeholder",
        "python",
        "A Python block holds a stub instead of code.",
        "A function whose body is only pass, '...' or a docstring (abstract methods, "
        "overloads, Protocol/ABC members and exception classes excepted), a bare '...' "
        "statement at module level, or a comment or string such as 'your code here' or "
        "'TODO: implement'. Only for blocks that parse.",
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
        "shell-syntax",
        "shell",
        "A shell block fails bash -n.",
        "bash -n reads the script without running any command. '$ ' prompts are removed and "
        "the output lines of a console session blanked first. Skipped, and reported as "
        "skipped, when bash is not installed. zsh-only syntax is reported as an error.",
    ),
    Rule(
        "js-syntax",
        "javascript",
        "A JavaScript block fails node --check.",
        "node --check compiles the file without running it; a block with import/export "
        "statements or top-level await is checked as an ES module, anything else as "
        "CommonJS. JSX and TypeScript are not sent to node. Skipped, and reported as "
        "skipped, when node is not installed.",
    ),
    Rule(
        "unbalanced-brackets",
        "balance",
        "A block in another language has unbalanced brackets or an open string.",
        "For C, C++, C#, Java, Go, Rust, TypeScript, JSX, Kotlin, Swift, Scala, PHP, Dart, CSS, "
        "Ruby, Perl, R, Julia and PowerShell, only brackets, strings and comments are "
        "scanned: this is a balance check, not a parse.",
    ),
    Rule(
        "lang-mismatch",
        "asks-language",
        "The prompt names one language and the code blocks are in another.",
        "Counted over answers whose prompt names exactly one language and that contain a "
        "block in a main language (shell, JSON, YAML, plain text and similar blocks are "
        "ignored). C and C++ are accepted for each other, as are JavaScript, TypeScript "
        "and JSX; HTML accepts CSS and JavaScript blocks.",
    ),
    Rule(
        "no-code",
        "asks-code",
        "The prompt asks for code and the answer has no code block.",
        "A prompt asks for code when a verb such as write, create or implement is followed "
        "within a clause by function, program, script, code, class, query and similar "
        "nouns. An answer that is entirely code counts as having a block.",
    ),
    Rule(
        "duplicate-block",
        "block",
        "A code block repeats a block of an earlier record.",
        "Blocks are compared after removing trailing whitespace; blocks under three "
        "non-blank lines are not compared. The first occurrence is not flagged, so --fix "
        "with this rule keeps one copy.",
    ),
    Rule(
        "json-invalid",
        "json",
        "A JSON block does not parse.",
        "json.loads raised an error; the message and position are reported.",
    ),
]

RULES: dict[str, Rule] = {rule.id: rule for rule in _RULES}
