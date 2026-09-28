#!/usr/bin/env python
"""Paired-bootstrap CI on the per-model accuracy delta between
S_paper-disjoint and the rest of S0_test.

Per team-lead 2026-04-25 SGT: B=10000, percentile 95% CI, paired on
problem_id within each model, then pooled across models.

Inputs:
  --combined  saved model-response JSONL with one row per model/problem verdict
  --disjoint  data/paper_disjoint_test.csv
  --B         bootstrap reps (default 10000)
  --seed      RNG seed (default 0)

Output (stdout + --out csv):
  pooled_acc_pd, pooled_acc_rest, delta_pp, ci_lo_pp, ci_hi_pp, half_width_pp,
  per-model rows: model, n_pd, n_rest, acc_pd, acc_rest, delta_pp, ci_lo_pp, ci_hi_pp
"""
import argparse, csv, json
import numpy as np

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--combined", required=True)
    ap.add_argument("--disjoint", required=True)
    ap.add_argument("--B", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pd_ids = set()
    with open(args.disjoint) as f:
        for r in csv.DictReader(f):
            pd_ids.add(str(r["problem_id"]))

    by_model_pd, by_model_rest = {}, {}
    for line in open(args.combined):
        r = json.loads(line)
        if r.get("is_correct") is None:
            continue
        m, pid = r["model"], str(r["problem_id"])
        ic = 1 if r["is_correct"] else 0
        (by_model_pd if pid in pd_ids else by_model_rest).setdefault(m, []).append(ic)

    rng = np.random.default_rng(args.seed)
    rows = []
    pooled_pd, pooled_rest = [], []
    pooled_deltas = []
    for m in sorted(set(by_model_pd) | set(by_model_rest)):
        pd_v = np.array(by_model_pd.get(m, []), dtype=np.int8)
        rt_v = np.array(by_model_rest.get(m, []), dtype=np.int8)
        if len(pd_v) == 0 or len(rt_v) == 0:
            continue
        a_pd, a_rt = pd_v.mean(), rt_v.mean()
        delta = a_pd - a_rt
        # paired-on-item bootstrap: resample item indices independently in each
        # slice (no shared problem_id between slices, so paired w/in slice only).
        boot = np.empty(args.B, dtype=np.float32)
        for b in range(args.B):
            idx_pd = rng.integers(0, len(pd_v), len(pd_v))
            idx_rt = rng.integers(0, len(rt_v), len(rt_v))
            boot[b] = pd_v[idx_pd].mean() - rt_v[idx_rt].mean()
        lo, hi = np.percentile(boot, [2.5, 97.5])
        rows.append({
            "model": m, "n_pd": len(pd_v), "n_rest": len(rt_v),
            "acc_pd": f"{a_pd:.4f}", "acc_rest": f"{a_rt:.4f}",
            "delta_pp": f"{100*delta:+.2f}",
            "ci_lo_pp": f"{100*lo:+.2f}", "ci_hi_pp": f"{100*hi:+.2f}",
        })
        pooled_pd.extend(pd_v.tolist()); pooled_rest.extend(rt_v.tolist())

    pp = np.array(pooled_pd, dtype=np.int8)
    pr = np.array(pooled_rest, dtype=np.int8)
    pooled_delta = pp.mean() - pr.mean()
    boot_pool = np.empty(args.B, dtype=np.float32)
    for b in range(args.B):
        ip = rng.integers(0, len(pp), len(pp))
        ir = rng.integers(0, len(pr), len(pr))
        boot_pool[b] = pp[ip].mean() - pr[ir].mean()
    lo_p, hi_p = np.percentile(boot_pool, [2.5, 97.5])
    half = 0.5 * (hi_p - lo_p)
    print(f"POOLED  n_pd={len(pp)}  n_rest={len(pr)}")
    print(f"   acc_pd={pp.mean():.4f}  acc_rest={pr.mean():.4f}")
    print(f"   delta = {100*pooled_delta:+.2f}pp  95% CI [{100*lo_p:+.2f}, {100*hi_p:+.2f}]  hw={100*half:.2f}pp")
    print(f"   B={args.B}, seed={args.seed}")

    with open(args.out, "w") as f:
        w = csv.DictWriter(f, fieldnames=["model","n_pd","n_rest","acc_pd","acc_rest",
                                          "delta_pp","ci_lo_pp","ci_hi_pp"])
        w.writeheader(); w.writerows(rows)
    print(f"Wrote {len(rows)} per-model rows to {args.out}")

if __name__ == "__main__":
    main()
