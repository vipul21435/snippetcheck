# Changelog

## Unreleased

- Unfenced answers are taken whole before indented blocks are looked for, so an indented
  function body is no longer cut out of its answer; text that only parses into bare
  expressions is not called Python.
- Deeply nested but valid code no longer aborts a run (the scope analysis is skipped for it).
- Lone surrogates no longer abort a run.
- `--fix` refuses to overwrite its input and copies unreadable lines through.
- Truncation is not reported for prose after code, apostrophes in sentences or
  comment-only bodies; the backtick Python 2 marker is gone (it matched Markdown).
- Valid Python is parsed unchanged before any notebook rewrite.
- `__class__`, `type` aliases and `__all__` are handled by the scope analysis.
- JSX gets its own language and is not sent to node; a UTF-8 BOM is accepted and non-UTF-8
  input exits 2.
- More unfenced languages are recognised (C functions, Ruby, CSS, Perl, Scala, R, VHDL).

## 0.1.0 - 2026-11-13

First release.

- Extraction of fenced blocks (with info string, unterminated fences, fences indented in
  list items), indented blocks and answers that are entirely code; language from the info
  string, then from a keyword score.
- Python: `ast.parse` and `compile` with the error class and position, Python 2 syntax
  markers, `>>>` transcripts unwrapped, notebook magics neutralised, truncation signals,
  a scope analysis for undefined names and unused imports, placeholder bodies and text.
- JSON parse; shell through `bash -n`; JavaScript through `node --check`; bracket and
  string balance for other languages.
- Cross-checks: language asked for versus language given, a code request answered with no
  code, identical blocks across records.
- Reports in Markdown and JSON with Wilson intervals, per-language counts and example ids;
  `--max RULE=SHARE` thresholds for the exit code; `--fix OUT --drop RULE` for a filtered
  copy; `check`, `extract` and `explain` commands; JSON array input as well as JSONL.
