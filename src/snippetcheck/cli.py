"""Command-line interface: ``snippetcheck check | extract | explain``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TextIO

from . import __version__
from .check import Options, RecordResult, check_records
from .extract import extract_blocks
from .records import BadLine, iter_lines, read_jsonl
from .report import Summary, summarise, to_json, to_markdown
from .rules import RULES


@contextmanager
def _open_input(path: str) -> Iterator[TextIO]:
    if path == "-":
        yield sys.stdin
    else:
        with open(path, encoding="utf-8") as handle:
            yield handle


def _limited(items, limit: int | None):
    for n, item in enumerate(items):
        if limit is not None and n >= limit:
            return
        yield item


def _add_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", help="JSONL file, or - for standard input")
    parser.add_argument("--field", help="take the answer text from this key (dotted path)")
    parser.add_argument("--prompt-field", help="with --field, take the prompt from this key")
    parser.add_argument("--limit", type=int, help="read at most this many records")


def parse_threshold(text: str) -> tuple[str, float]:
    """Parse RULE=SHARE, where SHARE is a fraction (0.05) or a percentage (5%)."""
    rule, sep, value = text.partition("=")
    if not sep or rule not in RULES:
        raise argparse.ArgumentTypeError(f"expected RULE=SHARE with a known rule, got {text!r}")
    try:
        share = float(value[:-1]) / 100 if value.endswith("%") else float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"bad share in {text!r}") from None
    if not 0 <= share <= 1:
        raise argparse.ArgumentTypeError(f"share must be between 0 and 1 in {text!r}")
    return rule, share


def _rule_list(text: str) -> list[str]:
    rules = [r.strip() for r in text.split(",") if r.strip()]
    unknown = [r for r in rules if r not in RULES]
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown rule(s): {', '.join(unknown)}")
    return rules


def failed_thresholds(summary: Summary, limits: list[tuple[str, float]]) -> list[str]:
    failed = []
    for rule, limit in limits:
        stat = summary.rules[rule]
        if stat.units and stat.share > limit:
            failed.append(f"{rule}: {100 * stat.share:.2f} % > {100 * limit:.2f} %")
    return failed


def cmd_check(args: argparse.Namespace) -> int:
    drop = {rule for group in args.drop for rule in group}
    if drop and not args.fix:
        print("snippetcheck: --drop needs --fix OUT", file=sys.stderr)
        return 2
    if args.fix and not drop:
        print("snippetcheck: --fix needs at least one --drop RULE", file=sys.stderr)
        return 2
    if args.fix and args.path != "-" and os.path.exists(args.fix) \
            and os.path.samefile(args.fix, args.path):
        print("snippetcheck: --fix OUT must not be the input file", file=sys.stderr)
        return 2
    options = Options(external=not args.no_external)
    kept = dropped = passed = 0
    out = open(args.fix, "w", encoding="utf-8", errors="backslashreplace") if args.fix else None
    try:
        with _open_input(args.path) as handle:
            records = _limited(read_jsonl(iter_lines(handle), args.field, args.prompt_field),
                               args.limit)
            results = check_records(records, options, jobs=args.jobs,
                                    dedupe=not args.no_dedupe)

            def tee():
                nonlocal kept, dropped, passed
                for result in results:
                    if out is not None and isinstance(result, RecordResult):
                        if result.rules() & drop:
                            dropped += 1
                        else:
                            out.write(result.record.raw + "\n")
                            kept += 1
                    elif out is not None and result.raw:
                        out.write(result.raw + "\n")  # unreadable lines are passed through
                        passed += 1
                    yield result

            summary = summarise(tee(), max_examples=args.examples)
    finally:
        if out is not None:
            out.close()
    if args.format == "json":
        print(json.dumps(to_json(summary), indent=2))
    else:
        print(to_markdown(summary), end="")
    if out is not None:
        print(f"--fix: kept {kept} records and {passed} unreadable lines, dropped {dropped} "
              f"({', '.join(sorted(drop))})", file=sys.stderr)
    failed = failed_thresholds(summary, args.max)
    for line in failed:
        print(f"threshold exceeded: {line}", file=sys.stderr)
    return 1 if failed else 0


def cmd_extract(args: argparse.Namespace) -> int:
    with _open_input(args.path) as handle:
        items = read_jsonl(iter_lines(handle), args.field, args.prompt_field)
        for item in _limited(items, args.limit):
            if isinstance(item, BadLine):
                print(f"line {item.line}: {item.reason}", file=sys.stderr)
                continue
            for t, turn in enumerate(item.turns):
                for i, block in enumerate(extract_blocks(turn.answer)):
                    if args.lang and block.lang != args.lang:
                        continue
                    print(json.dumps({
                        "record": item.id, "turn": t, "block": i, "kind": block.kind,
                        "info": block.info, "lang": block.lang,
                        "lang_source": block.lang_source, "start_line": block.start_line,
                        "terminated": block.terminated, "code": block.code,
                    }))
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    if args.rule is None:
        for rule in RULES.values():
            print(f"{rule.id:20} {rule.summary}")
        return 0
    rule = RULES.get(args.rule)
    if rule is None:
        print(f"unknown rule: {args.rule}; known: {', '.join(RULES)}", file=sys.stderr)
        return 2
    print(f"{rule.id}: {rule.summary}\n\nCounted over: {rule.unit} blocks.\n\n{rule.detail}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="snippetcheck",
        description="Static checks for the code inside instruction and chat datasets. "
                    "Nothing from the dataset is executed or imported.",
        epilog="Exit codes: 0 ok, 1 a --max threshold exceeded, 2 bad usage or input.",
    )
    parser.add_argument("--version", action="version", version=f"snippetcheck {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="check every code block and report shares per rule")
    _add_input_args(check)
    check.add_argument("--format", choices=["markdown", "json"], default="markdown")
    check.add_argument("--examples", type=int, default=5,
                       help="example ids to list per rule (default 5)")
    check.add_argument("--max", type=parse_threshold, action="append", default=[],
                       metavar="RULE=SHARE",
                       help="exit 1 when RULE's share exceeds SHARE (0.05 or 5%%); repeatable")
    check.add_argument("--fix", metavar="OUT",
                       help="write the records that no --drop rule rejects to OUT, as JSONL "
                            "(also for JSON array input); unreadable lines are copied as they "
                            "are; OUT must differ from the input")
    check.add_argument("--drop", type=_rule_list, action="append", default=[],
                       metavar="RULE[,RULE]", help="with --fix, drop records with these rules")
    check.add_argument("--jobs", type=int, default=4,
                       help="threads, to overlap bash/node calls (default 4)")
    check.add_argument("--no-external", action="store_true",
                       help="do not run bash -n or node --check")
    check.add_argument("--no-dedupe", action="store_true",
                       help="do not look for duplicate blocks across records")
    check.set_defaults(func=cmd_check)

    extract = sub.add_parser("extract", help="print every code block as one JSON line")
    _add_input_args(extract)
    extract.add_argument("--lang", help="only blocks in this language")
    extract.set_defaults(func=cmd_extract)

    explain = sub.add_parser("explain", help="describe a rule, or list them all")
    explain.add_argument("rule", nargs="?")
    explain.set_defaults(func=cmd_explain)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except OSError as exc:
        print(f"snippetcheck: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
