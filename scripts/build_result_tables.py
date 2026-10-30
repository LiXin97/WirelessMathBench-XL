#!/usr/bin/env python3
"""Rebuild the per-model and pairwise result tables from released verdicts.

Writes data/per_model_results.csv and data/paired_bootstrap_matrix.csv, and
prints the summary statistics quoted in the paper. It reuses
per_model_delta_bootstrap.py and paired_bootstrap.py and makes no model calls.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FORMATS = {"MCQ": "acc_mcq", "fill_blank_100": "acc_fec"}


def load(path: Path) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    with path.open() as fh:
        for line in fh:
            r = json.loads(line)
            out.setdefault(r["model"], {})[str(r["problem_id"])] = r
    return out


def acc(v: dict[str, dict], ids=None) -> float:
    keys = list(v) if ids is None else [i for i in ids if i in v]
    return 100 * sum(v[i]["is_correct"] for i in keys) / len(keys)


def bootstrap(script: Path, jsonl: Path, subset: str, seed: int, B: int) -> dict[str, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "pm.csv"
        subprocess.run([sys.executable, str(script), "--jsonl", str(jsonl), "--out", str(out),
                        "--subset", subset, "--seed", str(seed), "--B", str(B)],
                       check=True, stdout=subprocess.DEVNULL)
        return {r["model"]: r for r in csv.DictReader(out.open())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdict-dir", type=Path, default=ROOT / "data/verdicts")
    ap.add_argument("--split-csv", type=Path, default=ROOT / "data/paper_disjoint_split_seed0.csv")
    ap.add_argument("--public-ids", type=Path, default=ROOT / "data/public_test_ids.json")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--B", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    types = {r["problem_id"]: r["type"] for r in csv.DictReader(args.split_csv.open())
             if r["original_split"] == "test"}
    fmt_ids: dict[str, list[str]] = {"acc_mcq": [], "acc_fill": [], "acc_fec": []}
    for pid, t in types.items():
        fmt_ids[FORMATS.get(t, "acc_fill")].append(pid)
    public = [str(x) for x in json.load(args.public_ids.open())]

    views = {"16k": args.verdict_dir / "frontier_16k.jsonl", "2k": args.verdict_dir / "locked_2k.jsonl"}
    data = {k: load(p) for k, p in views.items()}
    script = ROOT / "scripts/per_model_delta_bootstrap.py"
    rows = []
    for view, path in views.items():
        s0 = bootstrap(script, path, "S0", args.seed, args.B)
        s1 = bootstrap(script, path, "S1", args.seed, args.B)
        for model, v in sorted(data[view].items()):
            a, b = s0[model], s1[model]
            row = {"budget": view, "model": model, "n_full": a["n_full"], "acc_full": round(acc(v), 4),
                   "n_S0": a["n_S0"], "acc_S0": round(100 * float(a["acc_S0"]), 4),
                   "delta_S0_pp": a["delta_pp"], "ci_low_S0_pp": a["ci_low_pp"], "ci_high_S0_pp": a["ci_high_pp"],
                   "n_S1": b["n_S1"], "acc_S1": round(100 * float(b["acc_S1"]), 4),
                   "delta_S1_pp": b["delta_pp"], "ci_low_S1_pp": b["ci_low_pp"], "ci_high_S1_pp": b["ci_high_pp"]}
            for name, ids in fmt_ids.items():
                row[name] = round(acc(v, ids), 4)
            row["acc_public310"] = round(acc(v, public), 4)
            other = data["2k"].get(model) if view == "16k" else None
            row["gain_2k_to_16k_pp"] = round(acc(v) - acc(other), 2) if other else ""
            rows.append(row)
    out = args.out_dir / "per_model_results.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} rows)")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        full = tmp / "full.csv"
        with full.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["model", "problem_id", "is_correct"])
            for model, v in data["2k"].items():
                for pid, r in v.items():
                    w.writerow([model, pid, r["is_correct"]])
        subprocess.run([sys.executable, str(ROOT / "scripts/paired_bootstrap.py"), "--cleaned-jsonl", str(views["2k"]),
                        "--full-csv", str(full), "--out-dir", str(tmp), "--B", str(args.B), "--seed", str(args.seed)],
                       check=True, stdout=subprocess.DEVNULL)
        with (tmp / "paired-bootstrap-matrix.csv").open() as src, (args.out_dir / "paired_bootstrap_matrix.csv").open("w", newline="") as dst:
            reader = csv.DictReader(src)
            writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
            writer.writeheader()
            for r in reader:
                for k in ("delta_full", "ci_low_full", "ci_high_full", "delta_S0", "ci_low_S0", "ci_high_S0", "p_S0"):
                    r[k] = f"{float(r[k]):.6f}"
                writer.writerow(r)
        (args.out_dir.parent / "derived").mkdir(exist_ok=True)
        shutil.copy(tmp / "bootstrap-runtime.md", args.out_dir.parent / "derived/bootstrap-runtime.md")
    print(f"wrote {args.out_dir / 'paired_bootstrap_matrix.csv'}")

    # Statistics quoted in the paper.
    f = data["16k"]
    pids = sorted(types)
    x = np.array([f["openai/gpt-5.2-chat"][p]["is_correct"] for p in pids])
    y = np.array([f["openai/gpt-5-mini"][p]["is_correct"] for p in pids])
    idx = np.random.default_rng(args.seed).integers(0, len(pids), size=(args.B, len(pids)))
    d = 100 * (x[idx] - y[idx]).mean(axis=1)
    print(f"GPT-5.2-chat minus GPT-5-mini at 16k: {100 * (x - y).mean():+.3f} "
          f"[{np.quantile(d, 0.025):+.3f}, {np.quantile(d, 0.975):+.3f}]")
    s0 = [p for p in pids if next(iter(f.values()))[p]["in_S0"]]
    bound = {m: 30 * (100 - acc(v, s0)) / 800 for m, v in f.items()}
    print(f"all-flagged-correct bound, 16k rows: {min(bound.values()):.3f}-{max(bound.values()):.3f} pp")
    for view, rowsv in data.items():
        flips = [(a, b) for a, b in itertools.combinations(rowsv, 2)
                 if (acc(rowsv[a]) - acc(rowsv[b])) * (acc(rowsv[a], s0) - acc(rowsv[b], s0)) < 0]
        print(f"{view}: {len(rowsv)} rows, full-vs-S0 pairwise sign flips: {len(flips)}")


if __name__ == "__main__":
    main()
