#!/usr/bin/env python3
"""Per-model Δ(full − cleaned subset) paired bootstrap.

For each model, compute:
  acc_full = (# correct on all 800 test items) / 800
  acc_subset = (# correct on S0/S1∩test items) / (# S0/S1∩test items)
  Δ          = acc_full - acc_subset

Bootstrap CI: resample problem_ids with replacement (from the 800 full set);
recompute both acc_full and acc_S0 on the resample (S0 mask carried per-pid).
B=10,000 resamples; 95% CI from quantiles.

Inputs:
  saved model-response JSONL with one row per model/problem verdict

Output:
  derived/per-model-delta.csv
    cols: model, n_full, acc_full, n_S0, acc_S0, delta_pp, ci_low_pp, ci_high_pp
"""

from __future__ import annotations

import json
import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSONL = ROOT / "derived/fulltest-verdicts.jsonl"
DEFAULT_OUT = ROOT / "derived/per-model-delta.csv"

B = 10000
SEED = 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--subset", choices=["S0", "S1"], default="S0")
    parser.add_argument("--B", type=int, default=B)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    subset_field = f"in_{args.subset}"

    # model -> dict[pid] = (is_correct, in_S0)
    by_model: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    with args.jsonl.open() as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("is_correct") is None:
                continue
            by_model[r["model"]][r["problem_id"]] = (
                int(bool(r["is_correct"])),
                int(bool(r.get(subset_field))),
            )

    rng = np.random.default_rng(args.seed)
    rows: list[tuple] = []
    for model in sorted(by_model):
        d = by_model[model]
        pids = sorted(d.keys())
        n = len(pids)
        ic = np.array([d[p][0] for p in pids], dtype=np.int8)
        in_s0 = np.array([d[p][1] for p in pids], dtype=np.int8)

        n_full = n
        c_full = int(ic.sum())
        n_s0 = int(in_s0.sum())
        c_s0 = int((ic & in_s0).sum())
        if n_s0 == 0:
            print(f"  {model}: no {args.subset} rows, skip")
            continue
        acc_full = c_full / n_full
        acc_s0 = c_s0 / n_s0
        delta = acc_full - acc_s0

        # Bootstrap: resample idx into pids with replacement
        idx = rng.integers(0, n, size=(args.B, n))
        ic_b = ic[idx]
        s0_b = in_s0[idx]
        cf = ic_b.sum(axis=1)
        nf = n  # constant
        cs = (ic_b & s0_b).sum(axis=1)
        ns = s0_b.sum(axis=1)
        # Avoid div by zero — drop resamples with zero S0 count (extremely rare)
        keep = ns > 0
        deltas = (cf[keep] / nf) - (cs[keep] / ns[keep])
        lo = np.quantile(deltas, 0.025)
        hi = np.quantile(deltas, 0.975)

        rows.append((model, n_full, acc_full, n_s0, acc_s0, delta * 100, lo * 100, hi * 100))
        print(f"  {model:42s}  n_full={n_full:3d}  n_{args.subset}={n_s0:3d}  "
              f"Δ={delta*100:+.2f}pp  95% CI [{lo*100:+.2f}, {hi*100:+.2f}]")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fout:
        fout.write(f"model,n_full,acc_full,n_{args.subset},acc_{args.subset},delta_pp,ci_low_pp,ci_high_pp\n")
        for r in rows:
            fout.write(f"{r[0]},{r[1]},{r[2]:.6f},{r[3]},{r[4]:.6f},"
                       f"{r[5]:.4f},{r[6]:.4f},{r[7]:.4f}\n")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
