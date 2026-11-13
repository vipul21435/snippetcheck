"""Checks that compare the prompt with the answer, and blocks across records."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from .extract import Block

# Language names as prompts write them. Each pattern must name the language unambiguously.
_PROMPT_LANGS: list[tuple[str, re.Pattern[str]]] = [
    ("python", re.compile(r"\bpython\b", re.I)),
    ("javascript", re.compile(r"\b(javascript|node\.?js|js)\b", re.I)),
    ("typescript", re.compile(r"\btypescript\b", re.I)),
    ("java", re.compile(r"\bjava\b(?!\s*script)", re.I)),
    ("cpp", re.compile(r"\bc\+\+|\bcpp\b", re.I)),
    ("csharp", re.compile(r"\bc#|\bc sharp\b|\bcsharp\b", re.I)),
    ("c", re.compile(r"\b(in|using|a|the|write)\s+C\b(?![+#])|"
                     r"\bC (program|code|function|language)\b")),
    ("go", re.compile(r"\bgolang\b|\b(in|using)\s+Go\b|\bGo (program|code|function)\b")),
    ("rust", re.compile(r"\brust\b", re.I)),
    ("ruby", re.compile(r"\bruby\b", re.I)),
    ("php", re.compile(r"\bphp\b", re.I)),
    ("swift", re.compile(r"\bswift\b", re.I)),
    ("kotlin", re.compile(r"\bkotlin\b", re.I)),
    ("sql", re.compile(r"\bsql\b|\bmysql\b|\bpostgres(ql)?\b", re.I)),
    ("shell", re.compile(r"\b(bash|shell script)\b", re.I)),
    ("r", re.compile(r"\b(in|using)\s+R\b|\bR (program|code|function|script)\b")),
    ("html", re.compile(r"\bhtml\b", re.I)),
    ("css", re.compile(r"\bcss\b", re.I)),
    ("scala", re.compile(r"\bscala\b", re.I)),
    ("perl", re.compile(r"\bperl\b", re.I)),
    ("haskell", re.compile(r"\bhaskell\b", re.I)),
]

# Blocks in these languages do not count as an answer in another language.
AUXILIARY = {"", "text", "shell", "json", "yaml", "toml", "xml", "markdown", "diff", "ini",
             "dockerfile", "makefile", "powershell", "batch"}

# Languages accepted for a prompt that names the key.
COMPATIBLE: dict[str, set[str]] = {
    "c": {"c", "cpp"},
    "cpp": {"c", "cpp"},
    "javascript": {"javascript", "typescript", "jsx", "html"},
    "typescript": {"javascript", "typescript", "jsx"},
    "html": {"html", "css", "javascript", "xml"},
    "css": {"css", "scss", "html"},
    "shell": {"shell"},
    "sql": {"sql"},
}

_ASKS_CODE = re.compile(
    r"\b(write|create|implement|generate|develop|build|construct|code|compose|program)\b"
    r"[^.?!\n]{0,60}?\b(function|program|script|code|class|method|algorithm|query|snippet|"
    r"module|routine|subroutine|api|app|application)s?\b",
    re.I,
)


def languages_asked(prompt: str) -> set[str]:
    return {lang for lang, pattern in _PROMPT_LANGS if pattern.search(prompt)}


def language_mismatch(prompt: str, blocks: Sequence[Block]) -> tuple[bool, str, str] | None:
    """None when the check does not apply; else (mismatch, message, language asked for)."""
    asked = languages_asked(prompt)
    if len(asked) != 1:
        return None
    [want] = asked
    main = [b.lang for b in blocks if b.lang not in AUXILIARY]
    if not main:
        return None
    ok = COMPATIBLE.get(want, {want})
    if any(lang in ok for lang in main):
        return False, "", want
    got = ", ".join(sorted(set(main)))
    return True, f"prompt asks for {want}, code blocks are {got}", want


def asks_for_code(prompt: str) -> bool:
    return bool(_ASKS_CODE.search(prompt))


def normalise_code(code: str) -> str:
    lines = [line.rstrip() for line in code.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip("\n")


def block_key(code: str, min_lines: int = 3) -> str | None:
    """A hash of the normalised code, or None for blocks too short to count as duplicates."""
    norm = normalise_code(code)
    if sum(1 for line in norm.split("\n") if line.strip()) < min_lines:
        return None
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()
