"""A small lexical scanner: strings, comments and bracket balance.

It does not tokenise a language; it only knows where strings and comments start and
end, so that brackets and keywords inside them are ignored. The same scanner serves
Python (triple quotes, ``#`` comments) and JSON (double quotes, no comments).
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field

_OPEN = "([{"
_CLOSE = ")]}"
_PAIR = {")": "(", "]": "[", "}": "{"}


@dataclass(frozen=True)
class Syntax:
    quotes: str = "\"'"
    triple: bool = True
    line_comments: tuple[str, ...] = ("#",)
    block_comments: tuple[tuple[str, str], ...] = ()


PYTHON = Syntax()
JSON = Syntax(quotes='"', triple=False, line_comments=())
C_LIKE = Syntax(quotes="\"'", triple=False, line_comments=("//",),
                block_comments=(("/*", "*/"),))
JS_LIKE = Syntax(quotes="\"'`", triple=False, line_comments=("//",),
                 block_comments=(("/*", "*/"),))
RUST = Syntax(quotes='"', triple=False, line_comments=("//",), block_comments=(("/*", "*/"),))
HASH_COMMENT = Syntax(quotes="\"'", triple=False, line_comments=("#",))


@dataclass
class ScanResult:
    masked: str  # same length as the source; string contents and comments blanked
    open_brackets: list[tuple[str, int, int]] = field(default_factory=list)  # (char, line, col)
    mismatched: list[tuple[str, int, int]] = field(default_factory=list)
    open_string: tuple[str, int, int] | None = None  # string still open at the end
    broken_strings: list[tuple[int, int]] = field(default_factory=list)  # closed by a newline


class _Pos:
    def __init__(self, text: str) -> None:
        self._starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]

    def __call__(self, index: int) -> tuple[int, int]:
        line = bisect_right(self._starts, index)
        return line, index - self._starts[line - 1]


def scan(src: str, syntax: Syntax = PYTHON) -> ScanResult:
    pos = _Pos(src)
    out: list[str] = []
    stack: list[tuple[str, int]] = []
    result = ScanResult(masked="")
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        block = next((b for b in syntax.block_comments if src.startswith(b[0], i)), None)
        if block is not None:
            end = src.find(block[1], i + len(block[0]))
            end = n if end == -1 else end + len(block[1])
            out.append("".join("\n" if c == "\n" else " " for c in src[i:end]))
            i = end
            continue
        comment = next((c for c in syntax.line_comments if src.startswith(c, i)), None)
        if comment is not None:
            end = src.find("\n", i)
            end = n if end == -1 else end
            out.append(" " * (end - i))
            i = end
            continue
        if ch in syntax.quotes:
            quote = ch * 3 if syntax.triple and src.startswith(ch * 3, i) else ch
            start = i
            out.append(quote)
            i += len(quote)
            closed = False
            while i < n:
                c = src[i]
                if c == "\\" and i + 1 < n:
                    out.append(" \n" if src[i + 1] == "\n" else "  ")
                    i += 2
                    continue
                if src.startswith(quote, i):
                    out.append(quote)
                    i += len(quote)
                    closed = True
                    break
                if c == "\n" and len(quote) == 1:
                    result.broken_strings.append(pos(start))
                    closed = True  # the line ends the string; scanning resumes after it
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            if not closed:
                line, col = pos(start)
                result.open_string = (quote, line, col)
            continue
        if ch in _OPEN:
            stack.append((ch, i))
        elif ch in _CLOSE:
            if stack and stack[-1][0] == _PAIR[ch]:
                stack.pop()
            else:
                result.mismatched.append((ch, *pos(i)))
        out.append(ch)
        i += 1
    result.masked = "".join(out)
    result.open_brackets = [(ch, *pos(idx)) for ch, idx in stack]
    return result
