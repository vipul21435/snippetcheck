"""Find the code blocks inside a free-text answer.

Three kinds of block are recognised, in this order:

* fenced blocks, opened by three or more backticks or tildes with an optional info
  string, closed by a fence of the same character that is at least as long. A fence
  that is never closed runs to the end of the text and is marked ``terminated=False``.
  Unlike CommonMark, a fence may be indented by any amount (list items in model output
  often indent fences by four or more spaces); the opening indent is removed from the
  content lines.
* indented blocks (four spaces or a tab) that follow a blank line and are not the
  continuation of a list item, outside any fence.
* the whole answer, when it has no blocks of the first two kinds and reads as code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .lang import guess_language, looks_like_code, normalise_info

_FENCE_OPEN = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_LIST_ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s+\S")


@dataclass(frozen=True)
class Block:
    """One code block found in a text."""

    code: str
    kind: str  # "fenced", "indented" or "whole"
    info: str  # raw info string of a fenced block, "" otherwise
    lang: str  # normalised language name, "" when unknown
    lang_source: str  # "info", "heuristic" or "none"
    start_line: int  # 1-based line of the first code line in the text
    terminated: bool = True


def _closes(line: str, char: str, length: int) -> bool:
    stripped = line.strip()
    return (
        len(stripped) >= length
        and set(stripped) == {char}
    )


def _strip_indent(line: str, indent: str) -> str:
    """Remove up to ``len(indent)`` leading whitespace characters."""
    n = 0
    while n < len(indent) and n < len(line) and line[n] in " \t":
        n += 1
    return line[n:]


def _make_block(code: str, kind: str, info: str, start: int, terminated: bool = True) -> Block:
    lang = normalise_info(info)
    source = "info" if lang else "none"
    if not lang:
        lang = guess_language(code)
        source = "heuristic" if lang else "none"
    return Block(code=code, kind=kind, info=info, lang=lang, lang_source=source,
                 start_line=start, terminated=terminated)


def _fenced(lines: list[str]) -> tuple[list[Block], list[bool]]:
    """Return fenced blocks and a mask of the lines they occupy (fences included)."""
    blocks: list[Block] = []
    inside = [False] * len(lines)
    i = 0
    while i < len(lines):
        match = _FENCE_OPEN.match(lines[i])
        if match is None:
            i += 1
            continue
        fence = match.group("fence")
        info = match.group("info").strip()
        if fence[0] == "`" and "`" in info:
            i += 1  # inline code such as ```x``` on one line, not a fence
            continue
        indent = match.group("indent")
        char, length = fence[0], len(fence)
        body: list[str] = []
        j = i + 1
        closed = False
        while j < len(lines):
            if _closes(lines[j], char, length):
                closed = True
                break
            body.append(_strip_indent(lines[j], indent))
            j += 1
        end = j if closed else len(lines) - 1
        for k in range(i, end + 1):
            inside[k] = True
        blocks.append(_make_block("\n".join(body), "fenced", info, i + 2, terminated=closed))
        i = end + 1
    return blocks, inside


def _is_indented(line: str) -> bool:
    return line.startswith("    ") or line.startswith("\t")


def _indented(lines: list[str], taken: list[bool]) -> list[Block]:
    blocks: list[Block] = []
    i = 0
    prev_text = ""  # last non-blank line outside any code block
    while i < len(lines):
        line = lines[i]
        starts_block = (
            not taken[i]
            and _is_indented(line)
            and line.strip()
            and (i == 0 or not lines[i - 1].strip())
            and not _LIST_ITEM.match(prev_text)
            and not _is_indented(prev_text)
        )
        if not starts_block:
            if not taken[i] and line.strip():
                prev_text = line
            i += 1
            continue
        j = i
        body: list[str] = []
        while j < len(lines) and not taken[j] and (_is_indented(lines[j]) or not lines[j].strip()):
            body.append(lines[j][4:] if lines[j].startswith("    ") else lines[j][1:])
            j += 1
        while body and not body[-1].strip():
            body.pop()
        blocks.append(_make_block("\n".join(body), "indented", "", i + 1))
        prev_text = lines[j - 1]
        i = j
    return blocks


def extract_blocks(text: str) -> list[Block]:
    """Return the code blocks of ``text`` in order of appearance."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    fenced, taken = _fenced(lines)
    indented = _indented(lines, taken)
    blocks = sorted(fenced + indented, key=lambda b: b.start_line)
    if not blocks and looks_like_code(text):
        stripped = text.strip("\n")
        first = len(text) - len(text.lstrip("\n"))
        blocks.append(_make_block(stripped, "whole", "", text[:first].count("\n") + 1))
    return blocks
