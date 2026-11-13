# Changelog

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
