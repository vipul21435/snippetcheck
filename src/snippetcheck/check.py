"""Run the checks over records and blocks."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import islice

from .crosscheck import asks_for_code, block_key, language_mismatch
from .external import check_balance, check_javascript, check_shell
from .extract import Block, extract_blocks
from .pycheck import check_python
from .records import BadLine, Record
from .rules import Finding
from .scan import JSON, scan


@dataclass
class BlockResult:
    record_id: str
    turn: int  # 0-based index of the answer within the record
    index: int  # 0-based index of the block within the answer
    block: Block
    checker: str | None  # "python", "json", "shell", "javascript", "balance" or None
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class TurnCheck:
    turn: int
    unit: str  # "asks-language" or "asks-code"
    finding: Finding | None


@dataclass
class RecordResult:
    record: Record
    blocks: list[BlockResult]
    turn_checks: list[TurnCheck] = field(default_factory=list)

    def rules(self) -> set[str]:
        found = {f.rule for b in self.blocks for f in b.findings}
        found.update(t.finding.rule for t in self.turn_checks if t.finding is not None)
        return found


def check_json(code: str) -> list[Finding]:
    try:
        json.loads(code)
    except ValueError as exc:
        line = getattr(exc, "lineno", None)
        col = getattr(exc, "colno", None)
        msg = getattr(exc, "msg", str(exc))
        findings = [Finding("json-invalid", f"{msg} at line {line}, column {col}", line, col,
                            detail=msg)]
        res = scan(code, JSON)
        if res.open_string is not None:
            findings.append(Finding("truncated", "ends inside a string", res.open_string[1],
                                    detail="ends inside a string"))
        elif res.open_brackets and not res.mismatched:
            findings.append(Finding("truncated", "ends with brackets still open",
                                    res.open_brackets[-1][1],
                                    detail="ends with brackets still open"))
        return findings
    return []


@dataclass(frozen=True)
class Options:
    external: bool = True  # run bash -n and node --check


DEFAULT_OPTIONS = Options()


def check_block(block: Block, record_id: str = "", turn: int = 0, index: int = 0,
                options: Options = DEFAULT_OPTIONS) -> BlockResult:
    result = BlockResult(record_id, turn, index, block, None)
    if block.kind == "fenced" and not block.terminated:
        result.findings.append(Finding("unterminated-fence", "fence opened and never closed",
                                       detail=block.info or "no info string"))
    lang = block.lang
    if lang == "python":
        py = check_python(block.code)
        result.notes.extend(py.notes)
        if py.skip:
            result.notes.append(f"skipped: {py.skip}")
        else:
            result.checker = "python"
            result.findings.extend(py.findings)
    elif lang == "json":
        result.checker = "json"
        result.findings.extend(check_json(block.code))
    elif lang in ("shell", "javascript"):
        if not options.external:
            result.notes.append("skipped: external checks off")
            return result
        found, note = (check_shell if lang == "shell" else check_javascript)(block.code)
        if found is None:
            result.notes.append(note)
        else:
            result.checker = lang
            result.findings.extend(found)
    else:
        balance = check_balance(block.code, lang)
        if balance is not None:
            result.checker = "balance"
            result.findings.extend(balance)
    return result


def check_record(record: Record, options: Options = DEFAULT_OPTIONS) -> RecordResult:
    blocks: list[BlockResult] = []
    checks: list[TurnCheck] = []
    for t, turn in enumerate(record.turns):
        found = extract_blocks(turn.answer)
        for i, block in enumerate(found):
            blocks.append(check_block(block, record.id, t, i, options))
        mismatch = language_mismatch(turn.prompt, found)
        if mismatch is not None:
            bad, message, asked = mismatch
            finding = Finding("lang-mismatch", message, detail=f"asked {asked}") if bad else None
            checks.append(TurnCheck(t, "asks-language", finding))
        if asks_for_code(turn.prompt):
            finding = None if found else Finding("no-code",
                                                 "prompt asks for code, answer has none")
            checks.append(TurnCheck(t, "asks-code", finding))
    return RecordResult(record, blocks, checks)


class DuplicateTracker:
    """Mark every code block identical to one seen in an earlier record."""

    def __init__(self, min_lines: int = 3) -> None:
        self.min_lines = min_lines
        self.first: dict[str, str] = {}

    def mark(self, result: RecordResult) -> None:
        seen_here: set[str] = set()
        for block in result.blocks:
            key = block_key(block.block.code, self.min_lines)
            if key is None:
                continue
            first = self.first.get(key)
            if first is None:
                self.first[key] = block.record_id
                seen_here.add(key)
            elif key not in seen_here:
                block.findings.append(Finding("duplicate-block",
                                              f"same code as a block of record {first}",
                                              detail=first))


def check_records(items: Iterable[Record | BadLine], options: Options = DEFAULT_OPTIONS,
                  jobs: int = 1, dedupe: bool = True,
                  chunk: int = 500) -> Iterator[RecordResult | BadLine]:
    """Check records in input order; ``jobs`` > 1 overlaps the external tool calls."""
    tracker = DuplicateTracker() if dedupe else None

    def one(item: Record | BadLine) -> RecordResult | BadLine:
        return item if isinstance(item, BadLine) else check_record(item, options)

    iterator = iter(items)
    pool = ThreadPoolExecutor(max_workers=jobs) if jobs > 1 else None
    try:
        while True:
            batch = list(islice(iterator, chunk))
            if not batch:
                return
            results = pool.map(one, batch) if pool else map(one, batch)
            for result in results:
                if tracker is not None and isinstance(result, RecordResult):
                    tracker.mark(result)
                yield result
    finally:
        if pool:
            pool.shutdown()
