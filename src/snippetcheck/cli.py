"""Command-line interface: ``snippetcheck check | extract | explain``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TextIO

from . import __version__
from .check import check_records
from .extract import extract_blocks
from .records import BadLine, read_jsonl
from .report import summarise, to_json, to_markdown
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


def cmd_check(args: argparse.Namespace) -> int:
    with _open_input(args.path) as handle:
        records = _limited(read_jsonl(handle, args.field, args.prompt_field), args.limit)
        summary = summarise(check_records(records), max_examples=args.examples)
    if args.format == "json":
        print(json.dumps(to_json(summary), indent=2))
    else:
        print(to_markdown(summary), end="")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    with _open_input(args.path) as handle:
        for item in _limited(read_jsonl(handle, args.field, args.prompt_field), args.limit):
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
    )
    parser.add_argument("--version", action="version", version=f"snippetcheck {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="check every code block and report shares per rule")
    _add_input_args(check)
    check.add_argument("--format", choices=["markdown", "json"], default="markdown")
    check.add_argument("--examples", type=int, default=5,
                       help="example ids to list per rule (default 5)")
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
