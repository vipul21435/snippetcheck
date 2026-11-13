"""Run snippetcheck from Python on the sample dataset and print a few findings.

    python examples/check_sample.py
"""

from pathlib import Path

from snippetcheck.check import check_records
from snippetcheck.records import iter_lines, read_jsonl
from snippetcheck.report import summarise

path = Path(__file__).with_name("sample.jsonl")
with path.open(encoding="utf-8") as handle:
    results = list(check_records(read_jsonl(iter_lines(handle))))

for result in results:
    for block in result.blocks:
        for finding in block.findings:
            print(f"record {block.record_id}, {block.block.lang} block {block.index}: "
                  f"{finding.rule}: {finding.message}")

summary = summarise(results)
stat = summary.rules["py-syntax"]
low, high = stat.interval
print(f"\nPython blocks that do not parse: {stat.count}/{stat.units} "
      f"({100 * stat.share:.1f} %, 95 % CI {100 * low:.1f} to {100 * high:.1f} %)")
