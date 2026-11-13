"""Shell and JavaScript syntax checks through ``bash -n`` and ``node --check``, and
bracket balance for every other language.

``bash -n`` reads the script without executing any command, and ``node --check``
compiles the file without running it. The code is written to a temporary file that
is removed afterwards. When either tool is missing the block is skipped and the
report says so.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

from .rules import Finding
from .scan import C_LIKE, HASH_COMMENT, JS_LIKE, RUST, Syntax, scan

TIMEOUT = 10.0

BALANCE_SYNTAX: dict[str, Syntax] = {
    **{lang: C_LIKE for lang in ("c", "cpp", "csharp", "java", "kotlin", "swift", "scala",
                                 "php", "dart", "css", "objective-c", "groovy")},
    **{lang: JS_LIKE for lang in ("typescript", "jsx", "go")},
    "rust": RUST,
    **{lang: HASH_COMMENT for lang in ("ruby", "perl", "r", "julia", "powershell")},
}

_ESM = re.compile(r"^\s*(import\s.+\sfrom\s|import\s+['\"]|export\s)", re.M)
_SHELL_PROMPT = re.compile(r"^\s*\$ ")


def tool(name: str) -> str | None:
    return shutil.which(name)


def _run(cmd: list[str], code: str, suffix: str) -> subprocess.CompletedProcess[str]:
    handle, path = tempfile.mkstemp(suffix=suffix, prefix="snippet")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(code)
            if not code.endswith("\n"):
                fh.write("\n")
        return subprocess.run(cmd + [path], capture_output=True, text=True, timeout=TIMEOUT,
                              stdin=subprocess.DEVNULL, env={"PATH": os.environ.get("PATH", "")})
    finally:
        os.unlink(path)


def unwrap_console(code: str) -> str:
    """Keep the commands of a ``$ command`` session, blank the output lines."""
    lines = code.split("\n")
    if not any(_SHELL_PROMPT.match(line) for line in lines):
        return code
    return "\n".join(_SHELL_PROMPT.sub("", line, count=1) if _SHELL_PROMPT.match(line) else ""
                     for line in lines)


def check_shell(code: str) -> tuple[list[Finding] | None, str]:
    """Return (findings, note); findings is None when bash is not available."""
    bash = tool("bash")
    if bash is None:
        return None, "skipped: bash not found"
    try:
        proc = _run([bash, "-n"], unwrap_console(code), ".sh")
    except subprocess.TimeoutExpired:
        return None, "skipped: bash -n timed out"
    if proc.returncode == 0:
        return [], ""
    first = next((line for line in proc.stderr.splitlines() if line.strip()), "syntax error")
    match = re.search(r"line (\d+): (.*)$", first)
    line = int(match.group(1)) if match else None
    msg = match.group(2) if match else first
    key = re.sub(r"`[^']*'", "`...'", msg)
    findings = [Finding("shell-syntax", f"bash -n: {msg}", line, detail=key)]
    if "unexpected end of file" in msg:
        findings.append(Finding("truncated", "ends inside an open construct (bash -n)", line,
                                detail="ends inside an open construct"))
    return findings, ""


def check_javascript(code: str) -> tuple[list[Finding] | None, str]:
    """Return (findings, note); findings is None when node is not available."""
    node = tool("node")
    if node is None:
        return None, "skipped: node not found"
    suffix = ".mjs" if _ESM.search(code) or re.search(r"^\s*await\s", code, re.M) else ".cjs"
    try:
        proc = _run([node, "--check"], code, suffix)
    except subprocess.TimeoutExpired:
        return None, "skipped: node --check timed out"
    if proc.returncode == 0:
        return [], ""
    err = proc.stderr.splitlines()
    line = None
    for text in err:
        match = re.search(r"\.[cm]js:(\d+)$", text.strip())
        if match:
            line = int(match.group(1))
            break
    msg = next((t.strip() for t in err if re.match(r"\s*SyntaxError\b", t)), "SyntaxError")
    findings = [Finding("js-syntax", f"node --check: {msg}", line, detail=msg)]
    if "Unexpected end of input" in msg or "Unterminated" in msg:
        findings.append(Finding("truncated", "ends mid-statement (node --check)", line,
                                detail="ends mid-statement"))
    return findings, ""


def check_balance(code: str, lang: str) -> list[Finding] | None:
    """Bracket and string balance only; None when the language has no scanner entry."""
    syntax = BALANCE_SYNTAX.get(lang)
    if syntax is None:
        return None
    res = scan(code, syntax)
    findings: list[Finding] = []
    if res.mismatched:
        ch, line, _ = res.mismatched[0]
        findings.append(Finding("unbalanced-brackets", f"unmatched '{ch}' at line {line}", line,
                                detail="unmatched closing bracket"))
    elif res.open_brackets or res.open_string:
        if res.open_string:
            line = res.open_string[1]
            what = "ends inside a string"
        else:
            line = res.open_brackets[-1][1]
            what = "ends with brackets still open"
        findings.append(Finding("unbalanced-brackets", f"{what} (line {line})", line,
                                detail=what))
        findings.append(Finding("truncated", f"{what} (line {line})", line, detail=what))
    return findings
