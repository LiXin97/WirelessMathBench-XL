#!/usr/bin/env python3
"""Recount the release statistics quoted in the paper from public files only.

Covers split and format counts, source-paper counts and eras, S0/S1 sizes, overlap
buckets, the n-gram sweep, license counts, and the external audit profiles.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows(name: str) -> list[dict]:
    with (ROOT / "data" / name).open() as fh:
        return list(csv.DictReader(fh))


def jsonl(name: str) -> list[dict]:
    with (ROOT / "data" / name).open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def year_month(paper_id: str) -> tuple[int, int]:
    m = re.match(r"(\d{2})(\d{2})", paper_id)
    yy, mm = int(m[1]), int(m[2])
    return (2000 + yy if yy < 90 else 1900 + yy, mm)


def pct(a: float, b: float) -> float:
    return round(100 * a / b, 3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "derived/release_stats.json")
    args = ap.parse_args()
    split = rows("paper_disjoint_split_seed0.csv")
    meta = {r["problem_id"]: r for r in jsonl("contamination_metadata.jsonl")}
    test = [r["problem_id"] for r in split if r["original_split"] == "test"]
    by_paper: dict[str, set] = {}
    for r in split:
        by_paper.setdefault(r["paper_id"], set()).add(r["original_split"])
    months = [year_month(p) for p in by_paper]
    era = Counter("3G/4G 2005-2018" if y <= 2018 else "5G 2019-2023" if y <= 2023 else "5G-Adv/6G 2024-2025"
                  for y, _ in months)
    out: dict = {
        "problems": len(split),
        "split": dict(Counter(r["original_split"] for r in split)),
        "split_by_type": {f"{a}/{b}": n for (a, b), n in
                          sorted(Counter((r["original_split"], r["type"]) for r in split).items())},
        "source_papers": len(by_paper),
        "papers_in_both_splits": sum(len(v) == 2 for v in by_paper.values()),
        "papers_train_only": sum(v == {"train"} for v in by_paper.values()),
        "papers_test_only": sum(v == {"test"} for v in by_paper.values()),
        "paper_month_range": [min(months), max(months)],
        "papers_by_era": dict(era),
        "papers_by_era_pct": {k: pct(v, len(months)) for k, v in era.items()},
        "S0": sum(m["in_S0"] for m in meta.values()),
        "S1": sum(m["in_S1"] for m in meta.values()),
        "S0_pct": pct(sum(m["in_S0"] for m in meta.values()), len(meta)),
        "S1_pct": pct(sum(m["in_S1"] for m in meta.values()), len(meta)),
        "S0_test": sum(meta[p]["in_S0"] for p in test),
        "S1_test": sum(meta[p]["in_S1"] for p in test),
        "flagged_all": sum(m["hits_total"] > 0 for m in meta.values()),
        "flagged_test": sum(meta[p]["hits_total"] > 0 for p in test),
        "max_hits_all": max(m["hits_total"] for m in meta.values()),
        "max_hits_test": max(meta[p]["hits_total"] for p in test),
        "median_hits_flagged": statistics.median(m["hits_total"] for m in meta.values() if m["hits_total"] > 0),
    }
    def bucket(x: int) -> str:
        return "0" if x == 0 else "1-2" if x <= 2 else "3-5" if x <= 5 else "6-10" if x <= 10 else ">=11"
    out["test_overlap_buckets"] = dict(Counter(bucket(meta[p]["hits_total"]) for p in test))

    member = {r["problem_id"]: r for r in rows("s0_membership_by_n.csv")}
    paper = {r["problem_id"]: r["paper_id"] for r in split}
    post = [p for p in member if year_month(paper[p]) >= (2023, 4)]
    pre = [p for p in member if year_month(paper[p]) < (2023, 4)]
    sweep = {}
    for n in (8, 10, 12, 13, 15):
        key = f"in_S0_n{n}"
        count = sum(member[p][key] == "True" for p in member)
        sweep[n] = {
            "S0_count": count, "S0_pct": pct(count, len(member)),
            "flip_vs_13_pct": pct(sum(member[p][key] != member[p]["in_S0_n13"] for p in member), len(member)),
            "post_snapshot_flag_pct": pct(sum(member[p][key] == "False" for p in post), len(post)),
            "pre_snapshot_flag_pct": pct(sum(member[p][key] == "False" for p in pre), len(pre)),
        }
    out["ngram_sweep_test"] = sweep

    for name in ("problems_cc_by", "problems_cc_by_sa", "problems_cc_by_nc_sa"):
        recs = jsonl(f"{name}.jsonl")
        out[name] = {"records": len(recs), "test": sum(r["split"] == "test" for r in recs)}
    out["public_test_ids"] = len(json.load((ROOT / "data/public_test_ids.json").open()))
    manifest = rows("excluded_records_manifest.csv")
    out["withheld"] = {"records": len(manifest), "test": sum(r["split"] == "test" for r in manifest),
                       "by_license": dict(Counter(r["license_class"] for r in manifest))}
    disjoint = rows("paper_disjoint_test.csv")
    out["paper_disjoint_test"] = {"items": len(disjoint), "papers": len({r["paper_id"] for r in disjoint}),
                                  "public_items": len(jsonl("paper_disjoint_test_public.jsonl"))}
    for label, name in (("wirelessmathbench_v1", "wmb_v1_587_redpajama_arxiv"), ("math500", "math500_redpajama_arxiv")):
        recs = jsonl(f"external-audits/{name}.jsonl")
        top = max(recs, key=lambda r: r["hits_total"])
        out[label] = {"items": len(recs), "flagged": sum(r["hits_total"] > 0 for r in recs),
                      "mean_probe_grams": round(statistics.mean(r["n_grams_total"] for r in recs), 2),
                      "top_flag_hits": top["hits_total"], "top_flag_docs": top["docs_total"]}
    args.out.parent.mkdir(exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, default=list) + "\n")
    print(json.dumps(out, indent=1, default=list))


if __name__ == "__main__":
    main()
