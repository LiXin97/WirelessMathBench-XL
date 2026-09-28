#!/usr/bin/env python
"""Materialize the v1.0 source-paper-disjoint sensitivity test view.

The released train/test split is problem-level. This script derives the small
sensitivity view of test records whose source paper does not appear in the train
partition. It is underpowered for a leaderboard, but it is the official v1.0
view for split-dependence analysis and a template for rebuilding future
paper-disjoint splits by grouping on ``paper_id``.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problems", default="data/problems_cc_by.jsonl")
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--out-csv", required=True)
    args = parser.parse_args()

    records = []
    train_papers = set()
    with open(args.problems) as handle:
        for line in handle:
            row = json.loads(line)
            records.append(row)
            if row.get("split") == "train":
                train_papers.add(row["paper_id"])

    paper_disjoint = [
        row
        for row in records
        if row.get("split") == "test" and row.get("paper_id") not in train_papers
    ]

    out_jsonl = Path(args.out_jsonl)
    out_csv = Path(args.out_csv)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with out_jsonl.open("w") as handle:
        for row in paper_disjoint:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    with out_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["problem_id", "paper_id", "type"])
        writer.writeheader()
        for row in paper_disjoint:
            writer.writerow(
                {
                    "problem_id": row["problem_id"],
                    "paper_id": row["paper_id"],
                    "type": row.get("type", ""),
                }
            )

    print(
        f"Wrote {len(paper_disjoint)} source-paper-disjoint test records "
        f"from {len(set(r['paper_id'] for r in paper_disjoint))} papers"
    )


if __name__ == "__main__":
    main()
