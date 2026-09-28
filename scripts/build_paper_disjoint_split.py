#!/usr/bin/env python
"""Build a paper-disjoint train/test split from released WMB-XL records.

The v1.0 release split is problem-level. This utility constructs a new split
by assigning every source paper, and therefore all problems from that paper, to
exactly one partition. The default target is an approximately 80/20 split with
rough task-format balance; users should retrain and reevaluate models on the
result before making paper-disjoint generalisation claims.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


Record = Dict[str, object]


def stable_key(text: str, seed: int) -> str:
    payload = f"{seed}:{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def type_counts(records: Iterable[Record]) -> Counter:
    return Counter(str(row.get("type", "")) for row in records)


def l1_distance(current: Counter, target: Counter) -> float:
    keys = set(current) | set(target)
    return sum(abs(current.get(key, 0) - target.get(key, 0)) for key in keys)


def choose_test_papers(
    paper_records: Dict[str, List[Record]], target_test_count: int, seed: int
) -> Tuple[set, Counter]:
    total_by_type = type_counts(row for rows in paper_records.values() for row in rows)
    total_count = sum(total_by_type.values())
    target_by_type = Counter(
        {key: target_test_count * value / total_count for key, value in total_by_type.items()}
    )

    remaining = sorted(paper_records, key=lambda pid: stable_key(pid, seed))
    test_papers = set()
    current_by_type: Counter = Counter()
    current_count = 0

    while remaining and current_count < target_test_count:
        best_index = 0
        best_score = None
        for index, paper_id in enumerate(remaining):
            rows = paper_records[paper_id]
            candidate_counts = current_by_type + type_counts(rows)
            candidate_count = current_count + len(rows)
            score = (
                l1_distance(candidate_counts, target_by_type),
                abs(candidate_count - target_test_count),
                stable_key(paper_id, seed),
            )
            if best_score is None or score < best_score:
                best_score = score
                best_index = index
        paper_id = remaining.pop(best_index)
        test_papers.add(paper_id)
        rows = paper_records[paper_id]
        current_by_type.update(type_counts(rows))
        current_count += len(rows)

    return test_papers, current_by_type


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problems", default="data/problems_cc_by.jsonl")
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--out-jsonl")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()

    records: List[Record] = []
    paper_records: Dict[str, List[Record]] = defaultdict(list)
    with open(args.problems) as handle:
        for line in handle:
            row = json.loads(line)
            records.append(row)
            paper_records[str(row["paper_id"])].append(row)

    target_test_count = round(len(records) * args.test_fraction)
    test_papers, test_by_type = choose_test_papers(
        paper_records, target_test_count=target_test_count, seed=args.seed
    )

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "problem_id",
                "paper_id",
                "type",
                "original_split",
                "paper_disjoint_split",
            ],
        )
        writer.writeheader()
        for row in records:
            split = "test" if str(row["paper_id"]) in test_papers else "train"
            writer.writerow(
                {
                    "problem_id": row["problem_id"],
                    "paper_id": row["paper_id"],
                    "type": row.get("type", ""),
                    "original_split": row.get("split", ""),
                    "paper_disjoint_split": split,
                }
            )

    if args.out_jsonl:
        out_jsonl = Path(args.out_jsonl)
        out_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with out_jsonl.open("w") as handle:
            for row in records:
                split = "test" if str(row["paper_id"]) in test_papers else "train"
                new_row = dict(row)
                new_row["original_split"] = row.get("split", "")
                new_row["split"] = split
                handle.write(json.dumps(new_row, ensure_ascii=False) + "\n")

    train_count = len(records) - sum(test_by_type.values())
    print(
        "Built paper-disjoint split: "
        f"train={train_count}, test={sum(test_by_type.values())}, "
        f"test_papers={len(test_papers)}, seed={args.seed}"
    )


if __name__ == "__main__":
    main()
