"""Aggregate results into shares with Wilson intervals, and render them."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from .check import BlockResult, RecordResult
from .records import BadLine
from .rules import RULES

Z95 = 1.959963984540054


def wilson_interval(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials (Wilson 1927).

    Returns (0.0, 1.0) when n is 0.
    """
    if n < 0 or k < 0 or k > n:
        raise ValueError("need 0 <= k <= n")
    if n == 0:
        return 0.0, 1.0
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass
class RuleStat:
    rule: str
    count: int
    units: int
    examples: list[str] = field(default_factory=list)

    @property
    def share(self) -> float:
        return self.count / self.units if self.units else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.count, self.units)


@dataclass
class Summary:
    records: int = 0
    bad_lines: int = 0
    turns: int = 0
    blocks: int = 0
    languages: Counter = field(default_factory=Counter)
    kinds: Counter = field(default_factory=Counter)
    units: Counter = field(default_factory=Counter)
    rules: dict[str, RuleStat] = field(default_factory=dict)
    details: dict[str, Counter] = field(default_factory=dict)


def _units_of(block: BlockResult) -> list[str]:
    units = []
    if block.checker is not None:
        units.append("checked")
        units.append(block.checker)
    if block.block.kind == "fenced":
        units.append("fenced")
    return units


def summarise(results: Iterable[RecordResult | BadLine], max_examples: int = 5) -> Summary:
    summary = Summary()
    for rule in RULES.values():
        summary.rules[rule.id] = RuleStat(rule.id, 0, 0)
        summary.details[rule.id] = Counter()
    for item in results:
        if isinstance(item, BadLine):
            summary.bad_lines += 1
            continue
        summary.records += 1
        summary.turns += len(item.record.turns)
        for block in item.blocks:
            summary.blocks += 1
            summary.languages[block.block.lang or "unknown"] += 1
            summary.kinds[block.block.kind] += 1
            for unit in _units_of(block):
                summary.units[unit] += 1
            for rule_id in {f.rule for f in block.findings}:
                stat = summary.rules[rule_id]
                stat.count += 1
                if len(stat.examples) < max_examples:
                    stat.examples.append(f"{block.record_id}#{block.turn}.{block.index}")
            for finding in block.findings:
                if finding.detail:
                    summary.details[finding.rule][finding.detail] += 1
    for stat in summary.rules.values():
        stat.units = summary.units[RULES[stat.rule].unit]
    return summary


def to_json(summary: Summary, top: int = 10) -> dict:
    return {
        "records": summary.records,
        "bad_lines": summary.bad_lines,
        "turns": summary.turns,
        "blocks": summary.blocks,
        "languages": dict(summary.languages.most_common()),
        "kinds": dict(summary.kinds.most_common()),
        "rules": {
            rule_id: {
                "count": stat.count,
                "unit": RULES[rule_id].unit,
                "units": stat.units,
                "share": stat.share,
                "ci95": list(stat.interval),
                "examples": stat.examples,
                "top_details": dict(summary.details[rule_id].most_common(top)),
            }
            for rule_id, stat in summary.rules.items()
        },
    }


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _pct(x: float) -> str:
    return f"{100 * x:.1f} %"


def to_markdown(summary: Summary, top: int = 5) -> str:
    out = [
        "# snippetcheck report",
        "",
        f"Records: {summary.records} ({summary.bad_lines} unreadable lines), "
        f"answers: {summary.turns}, code blocks: {summary.blocks}",
        "",
        "## Rules",
        "",
        "| rule | count | over | share | 95 % CI (Wilson) | examples |",
        "|---|---:|---|---:|---|---|",
    ]
    for rule_id, stat in summary.rules.items():
        lo, hi = stat.interval
        unit = RULES[rule_id].unit
        ci = f"{_pct(lo)} to {_pct(hi)}" if stat.units else "n/a"
        examples = ", ".join(stat.examples)
        out.append(f"| {rule_id} | {stat.count} | {stat.units} {unit} blocks | "
                   f"{_pct(stat.share)} | {ci} | {examples} |")
    out += ["", "## Languages", "", "| language | blocks |", "|---|---:|"]
    for lang, count in summary.languages.most_common():
        out.append(f"| {lang} | {count} |")
    syntax = summary.details.get("py-syntax", Counter())
    if syntax:
        out += ["", "## Most common Python syntax errors", "", "| error | blocks |", "|---|---:|"]
        for key, count in syntax.most_common(top):
            out.append(f"| {_cell(key)} | {count} |")
    out += ["", "Examples are record id#answer.block, all 0-based after the record id."]
    return "\n".join(out) + "\n"
