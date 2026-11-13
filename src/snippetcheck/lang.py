"""Language names: normalising fence info strings and guessing from the code itself.

The guess is a weighted keyword score, not a classifier. It only has to separate the
languages that dominate code-instruction data (Python, JavaScript, shell, JSON, C-like,
Java, SQL, HTML) well enough to route a block to the right static check.
"""

from __future__ import annotations

import json
import re

_ALIASES: dict[str, tuple[str, ...]] = {
    "python": ("python", "py", "python3", "py3", "python2", "py2", "ipython", "ipython3",
               "pycon", "pyi", "sage"),
    "javascript": ("javascript", "js", "node", "nodejs", "mjs", "cjs"),
    "jsx": ("jsx",),
    "typescript": ("typescript", "ts", "tsx"),
    "shell": ("shell", "sh", "bash", "zsh", "ksh", "console", "shell-session", "shellsession",
              "terminal"),
    "powershell": ("powershell", "ps1", "pwsh", "ps"),
    "batch": ("bat", "batch", "cmd"),
    "json": ("json",),
    "c": ("c", "h"),
    "cpp": ("cpp", "c++", "cc", "cxx", "hpp", "hxx"),
    "csharp": ("csharp", "cs", "c#"),
    "java": ("java",),
    "kotlin": ("kotlin", "kt"),
    "go": ("go", "golang"),
    "rust": ("rust", "rs"),
    "ruby": ("ruby", "rb"),
    "php": ("php",),
    "sql": ("sql", "mysql", "postgresql", "postgres", "psql", "sqlite", "plsql", "tsql"),
    "html": ("html", "htm", "xhtml"),
    "xml": ("xml", "svg"),
    "css": ("css", "scss", "sass", "less"),
    "yaml": ("yaml", "yml"),
    "toml": ("toml",),
    "markdown": ("markdown", "md"),
    "text": ("text", "txt", "plaintext", "plain", "output", "none", "nohighlight"),
    "swift": ("swift",),
    "r": ("r",),
    "scala": ("scala",),
    "perl": ("perl", "pl"),
    "lua": ("lua",),
    "haskell": ("haskell", "hs"),
    "julia": ("julia", "jl"),
    "dart": ("dart",),
    "matlab": ("matlab", "octave"),
    "diff": ("diff", "patch"),
    "dockerfile": ("dockerfile", "docker"),
    "makefile": ("makefile", "make"),
}

_ALIAS_TO_LANG = {alias: lang for lang, aliases in _ALIASES.items() for alias in aliases}

_INFO_TOKEN = re.compile(r"[^\s{}=,]+")


def normalise_info(info: str) -> str:
    """Map a fence info string to a language name, or "" when it names none.

    Handles ``python``, ``Python3``, ``{.python}``, ``language-python``,
    ``python title="x.py"`` and ``py:example.py``. An unknown first word is
    returned lowercased, so ``elixir`` stays ``elixir``.
    """
    info = info.strip()
    if not info:
        return ""
    match = _INFO_TOKEN.search(info.replace("{", " ").replace("}", " "))
    if match is None:
        return ""
    token = match.group(0).lower().lstrip(".")
    if token.startswith("language-"):
        token = token[len("language-"):]
    token = token.split(":", 1)[0]
    if not token:
        return ""
    return _ALIAS_TO_LANG.get(token, token)


# (pattern, weight) per language; patterns run with re.MULTILINE.
_CUES: dict[str, list[tuple[re.Pattern[str], float]]] = {
    "python": [
        (re.compile(r"^\s*def \w+\s*\(.*\)\s*(->\s*[^:]+)?:\s*$", re.M), 3.0),
        (re.compile(r"^\s*class \w+(\(.*\))?:\s*$", re.M), 3.0),
        (re.compile(r"^\s*(import [\w.]+(\s+as\s+\w+)?|from [\w.]+ import .+)\s*$", re.M), 2.0),
        (re.compile(r"^\s*(elif .+|else|try|except.*|finally|for .+ in .+|while .+|with .+):\s*$",
                    re.M), 1.5),
        (re.compile(r"^\s*if .+:\s*$", re.M), 1.0),
        (re.compile(r"\bself\.\w+"), 1.0),
        (re.compile(r"\bprint\s*\("), 1.0),
        (re.compile(r"^\s*print\s+[\"'\w]", re.M), 1.0),
        (re.compile(r"\b(None|True|False)\b"), 0.5),
        (re.compile(r"\b__name__\b|\b__init__\b"), 2.0),
        (re.compile(r"^\s*>>> ", re.M), 3.0),
        (re.compile(r"\blambda \w*:"), 1.0),
        (re.compile(r"\b(len|range|enumerate|isinstance)\("), 0.5),
    ],
    "javascript": [
        (re.compile(r"\bconsole\.log\("), 3.0),
        (re.compile(r"\bfunction\s*\w*\s*\([^)]*\)\s*\{"), 3.0),
        (re.compile(r"^\s*(const|let|var)\s+[\w{}\[\], ]+\s*=", re.M), 2.0),
        (re.compile(r"=>"), 1.0),
        (re.compile(r"\b(document|window)\.\w+"), 2.0),
        (re.compile(r"\brequire\(['\"]|\bmodule\.exports\b"), 2.0),
        (re.compile(r"^\s*import .+ from ['\"]", re.M), 2.0),
        (re.compile(r"===|!=="), 1.0),
    ],
    "shell": [
        (re.compile(r"^#!\s*/(usr/)?bin/(env\s+)?(ba|z|k)?sh\b", re.M), 4.0),
        (re.compile(r"^\s*\$ \S", re.M), 2.0),
        (re.compile(r"^\s*(sudo |pip3? install |npm (install|run|i) |yarn |"
                    r"git (clone|add|commit|push|checkout|pull) |cd |ls\b|mkdir |rm -|echo |"
                    r"export \w+=|curl |wget |apt(-get)? |brew |conda |chmod |docker )",
                    re.M), 2.0),
        (re.compile(r"^\s*(fi|done|esac)\s*$", re.M), 2.0),
        (re.compile(r"\$\{?\w+\}?"), 0.5),
    ],
    "java": [
        (re.compile(r"\bpublic\s+(static\s+)?(final\s+)?(class|void|int|String)\b"), 3.0),
        (re.compile(r"\bSystem\.out\.print"), 3.0),
        (re.compile(r"^\s*import java\.", re.M), 3.0),
        (re.compile(r"\bString\[\]\s+args\b"), 2.0),
    ],
    "cpp": [
        (re.compile(r"^\s*#include\s*<\w+>", re.M), 2.5),
        (re.compile(r"\bstd::"), 3.0),
        (re.compile(r"\bcout\s*<<|\bcin\s*>>"), 3.0),
        (re.compile(r"^\s*using namespace std;", re.M), 3.0),
    ],
    "c": [
        (re.compile(r"^\s*#include\s*<\w+\.h>", re.M), 2.5),
        (re.compile(r"\bprintf\s*\("), 1.5),
        (re.compile(r"\bint\s+main\s*\("), 1.5),
        (re.compile(r"\bmalloc\s*\(|\bfree\s*\("), 1.5),
        (re.compile(r"^\s*(static\s+)?(int|void|char|float|double|long|unsigned|bool|size_t)"
                    r"\s+\*?\w+\s*\([^;]*\)\s*\{?\s*$", re.M), 2.0),
    ],
    "ruby": [
        (re.compile(r"^\s*def \w+[!?]?(\(.*\))?\s*$", re.M), 1.5),
        (re.compile(r"^\s*end\s*$", re.M), 2.0),
        (re.compile(r"^\s*puts\b", re.M), 1.5),
        (re.compile(r"\.each(_with_index)? do\b|\bdo \|\w+(, *\w+)*\|"), 2.0),
    ],
    "css": [
        (re.compile(r"^\s*[.#]?[A-Za-z][\w-]*([\s,>+~]+[.#]?[\w-]+)*\s*\{\s*$", re.M), 1.5),
        (re.compile(r"^\s*[a-z-]+\s*:\s*[^;{}]+;\s*$", re.M), 2.0),
    ],
    "perl": [
        (re.compile(r"\bmy\s+[$@%]\w+"), 3.0),
        (re.compile(r"^\s*use (strict|warnings);", re.M), 3.0),
    ],
    "scala": [
        (re.compile(r"^\s*object \w+", re.M), 2.0),
        (re.compile(r"\bdef \w+\(.*\)\s*:\s*\w+.*="), 2.0),
    ],
    "r": [
        (re.compile(r"^\s*[\w.]+\s*<-\s*\S", re.M), 2.5),
        (re.compile(r"\b(paste0?|library|data\.frame|runif|rnorm)\("), 1.5),
    ],
    "vhdl": [
        (re.compile(r"\bentity \w+ is\b", re.I), 3.0),
        (re.compile(r"\barchitecture \w+ of\b", re.I), 3.0),
    ],
    "sql": [
        (re.compile(r"^\s*SELECT\b[\s\S]*?\bFROM\b", re.M | re.I), 3.0),
        (re.compile(r"^\s*(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE\s+TABLE|"
                    r"ALTER\s+TABLE|DROP\s+TABLE)\b", re.M | re.I), 3.0),
        (re.compile(r"\b(WHERE|GROUP BY|ORDER BY|JOIN)\b"), 1.0),
    ],
    "html": [
        (re.compile(r"<!DOCTYPE html>|<html\b", re.I), 4.0),
        (re.compile(r"</?(div|span|body|head|script|p|a|ul|li|table|form|input)\b[^>]*>",
                    re.I), 1.5),
    ],
}

_MIN_SCORE = 2.0
_MARKUP = re.compile(r"</[A-Za-z][\w.]*>|<[A-Za-z][\w.]*(\s[^<>]*)?/>")
_HTML_DOC = re.compile(r"<!DOCTYPE|<html\b|<body\b|<head\b", re.I)


def guess_language(code: str) -> str:
    """Guess the language of unlabelled code; return "" when nothing scores high enough."""
    stripped = code.strip()
    if not stripped:
        return ""
    if stripped[0] in "{[":
        try:
            json.loads(stripped)
        except ValueError:
            if re.search(r'^\s*"[^"\n]*"\s*:', stripped, re.M):
                return "json"
        else:
            return "json"
    scores: dict[str, float] = {}
    for lang, cues in _CUES.items():
        score = 0.0
        for pattern, weight in cues:
            if pattern.search(code):
                score += weight
        scores[lang] = score
    best = max(scores, key=lambda k: scores[k])
    ranked = sorted(scores.values(), reverse=True)
    if ranked[0] < _MIN_SCORE or ranked[0] == ranked[1]:
        return ""
    if best == "c" and scores["cpp"] > 0:
        return "cpp"
    if best == "javascript" and _MARKUP.search(code):
        return "html" if _HTML_DOC.search(code) else "jsx"
    return best


_PROSE_LINE = re.compile(r"^[A-Z][^(){};=<>\[\]]*[.?!:]$")
_SHORT_PROSE = re.compile(r"^[A-Z][a-z]+( [\w']+)*[.:!?]$")
_CODE_CHARS = re.compile(r"[(){};=\[\]<>]|^\s*(#|//|\$ )|^\s+\S")


def looks_like_code(text: str) -> bool:
    """True when an unfenced answer reads as code rather than prose.

    Requires a language guess and at least 70 % of non-blank lines that are not
    prose sentences and carry code punctuation or indentation.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or not guess_language(text):
        return False
    code_like = 0
    for line in lines:
        words = line.split()
        if _PROSE_LINE.match(line.strip()) and len(words) >= 4:
            continue
        if _CODE_CHARS.search(line) or (len(words) <= 3 and not _SHORT_PROSE.match(line.strip())):
            code_like += 1
    return code_like / len(lines) >= 0.7
