"""Run the checks over records and blocks."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

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
    checker: str | None  # "python", "json", or None when no checker applies
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class RecordResult:
    record: Record
    blocks: list[BlockResult]


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


def check_block(block: Block, record_id: str = "", turn: int = 0, index: int = 0) -> BlockResult:
    result = BlockResult(record_id, turn, index, block, None)
    if block.kind == "fenced" and not block.terminated:
        result.findings.append(Finding("unterminated-fence", "fence opened and never closed",
                                       detail=block.info or "no info string"))
    if block.lang == "python":
        py = check_python(block.code)
        result.notes.extend(py.notes)
        if py.skip:
            result.notes.append(f"skipped: {py.skip}")
        else:
            result.checker = "python"
            result.findings.extend(py.findings)
    elif block.lang == "json":
        result.checker = "json"
        result.findings.extend(check_json(block.code))
    return result


def check_record(record: Record) -> RecordResult:
    blocks: list[BlockResult] = []
    for t, turn in enumerate(record.turns):
        for i, block in enumerate(extract_blocks(turn.answer)):
            blocks.append(check_block(block, record.id, t, i))
    return RecordResult(record, blocks)


def check_records(items: Iterable[Record | BadLine]) -> Iterator[RecordResult | BadLine]:
    for item in items:
        yield item if isinstance(item, BadLine) else check_record(item)
