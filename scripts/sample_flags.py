"""Print a seeded random sample of the blocks one rule flags, for reading by hand.

    python scripts/sample_flags.py DATA.json RULE [--n 50] [--seed 0]

Prints, for each sampled finding: record id, the finding, which block it is in, the
prompt (lines starting "> ") and the full answer with line numbers, so that lines the
extractor left out of the block can be seen.
Nothing from the dataset is executed.
"""

from __future__ import annotations

import argparse
import random

from snippetcheck.check import Options, check_records
from snippetcheck.records import Record, iter_lines, read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("rule")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-external", action="store_true")
    args = parser.parse_args()
    flagged = []
    with open(args.path, encoding="utf-8") as handle:
        items = read_jsonl(iter_lines(handle))
        options = Options(external=not args.no_external)
        for result in check_records(items, options, jobs=8):
            if not hasattr(result, "blocks"):
                continue
            record: Record = result.record
            for block in result.blocks:
                for finding in block.findings:
                    if finding.rule == args.rule:
                        flagged.append((record, block, finding))
    rng = random.Random(args.seed)
    sample = rng.sample(flagged, min(args.n, len(flagged)))
    print(f"# {len(flagged)} findings of {args.rule}; sample of {len(sample)}, seed {args.seed}")
    for k, (record, block, finding) in enumerate(sample, 1):
        turn = record.turns[block.turn]
        print(f"\n## {k}. record {record.id}: {finding.message} "
              f"({block.block.kind} {block.block.lang or 'unknown'} block "
              f"{block.index}, from answer line {block.block.start_line})")
        for line in turn.prompt.split("\n"):
            print(f"> {line}")
        print("--- full answer")
        for n, line in enumerate(turn.answer.split("\n"), 1):
            print(f"{n:3} | {line}")


if __name__ == "__main__":
    main()
