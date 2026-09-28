#!/usr/bin/env python3
"""
fetch_excluded_sources.py — inspect and fetch the sources of withheld records.

The public release distributes only records whose source-paper license clearly
permits redistribution of derived text (CC BY / CC0 -> problems_cc_by.jsonl,
CC BY-SA -> problems_cc_by_sa.jsonl, CC BY-NC-SA -> problems_cc_by_nc_sa.jsonl;
1,542 of 4,027 records). The remaining 2,485 records derive from papers under
the arXiv default non-exclusive distribution license (2,160), CC BY-NC-ND (323),
or no recorded license (2). They are withheld and listed, without problem text,
in data/excluded_records_manifest.csv.

What this script does:
  * summarises the manifest by license class and split;
  * lists withheld papers with their problem counts;
  * optionally downloads the arXiv source archives of withheld papers
    (--fetch DIR), rate-limited, so that a user can inspect provenance or run
    their own extraction under their own legal determination.

What it does NOT do: it cannot reproduce the withheld records. The original
records were produced by stochastic LLM extraction and synthesis (DeepSeek-R1,
GPT-4o) followed by expert screening, so re-running the pipeline on the same
sources yields different problems. Results on the 800-item test split therefore
rely on the authors' full copy; the 310-item public test subset
(data/public_test_ids.json, results in data/public_subset_results.csv) is the
externally reproducible view.

Usage:
  python3 scripts/fetch_excluded_sources.py                  # summary
  python3 scripts/fetch_excluded_sources.py --list-papers
  python3 scripts/fetch_excluded_sources.py --fetch sources/ [--split test]
"""
from __future__ import annotations

import argparse
import collections
import csv
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "data" / "excluded_records_manifest.csv"


def load_manifest(split: str | None) -> list[dict[str, str]]:
    with MANIFEST.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if split is None or r["split"] == split]


def fetch(rows: list[dict[str, str]], out: Path, delay: float) -> None:
    """Download arXiv e-print archives, one per withheld paper, rate-limited."""
    out.mkdir(parents=True, exist_ok=True)
    papers = sorted({(r["paper_id"], r["arxiv_id"]) for r in rows})
    for i, (paper_id, arxiv_id) in enumerate(papers, 1):
        dest = out / f"{paper_id}.tar.gz"
        if dest.exists():
            continue
        url = f"https://arxiv.org/e-print/{paper_id}"
        print(f"[{i}/{len(papers)}] {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "wmb-xl-provenance/1.1"})
        with urllib.request.urlopen(req) as resp:
            dest.write_bytes(resp.read())
        time.sleep(delay)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["train", "test"],
                    help="restrict to one split of the withheld records")
    ap.add_argument("--list-papers", action="store_true",
                    help="print withheld papers with problem counts")
    ap.add_argument("--fetch", type=Path, metavar="DIR",
                    help="download arXiv source archives of withheld papers into DIR")
    ap.add_argument("--delay", type=float, default=3.0,
                    help="seconds between arXiv requests (default: 3)")
    args = ap.parse_args()

    rows = load_manifest(args.split)
    by_class = collections.Counter(r["license_class"] for r in rows)
    by_split = collections.Counter(r["split"] for r in rows)
    print(f"{len(rows)} withheld records from "
          f"{len({r['paper_id'] for r in rows})} papers")
    print("  by license: " + ", ".join(f"{k}={v}" for k, v in sorted(by_class.items())))
    print("  by split:   " + ", ".join(f"{k}={v}" for k, v in sorted(by_split.items())))

    if args.list_papers:
        per_paper = collections.Counter(r["paper_id"] for r in rows)
        for pid in sorted(per_paper):
            print(f"{pid}\t{per_paper[pid]} problems")

    if args.fetch:
        fetch(rows, args.fetch, args.delay)


if __name__ == "__main__":
    main()
