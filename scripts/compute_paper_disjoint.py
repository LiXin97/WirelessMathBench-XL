#!/usr/bin/env python
"""Compute verifier accuracy on the n=34 paper-disjoint surrogate.

Inputs:
  --combined  saved model-response JSONL with one row per model/problem verdict
  --disjoint  data/paper_disjoint_test.csv
Output:
  derived/verifier_paper_disjoint.csv
    columns: model, n_pd, n_correct_pd, acc_pd, n_rest, acc_rest, delta_pp

Note: n=34 is severely underpowered (95% CI half-width ~8.7pp at p~0.93);
this number rules out catastrophic verifier-overfitting only. See §5.X #9.
"""
import argparse, csv, json, pathlib, statistics

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--combined", required=True)
    ap.add_argument("--disjoint", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pd_ids = set()
    with open(args.disjoint) as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            pd_ids.add(str(r["problem_id"]))
    print(f"|S_paper-disjoint| = {len(pd_ids)}")

    by_model_pd = {}    # model -> [is_correct,...]
    by_model_rest = {}  # model -> [is_correct,...]
    for line in open(args.combined):
        r = json.loads(line)
        model = r["model"]
        pid = str(r["problem_id"])
        if "is_correct" not in r:
            continue
        ic = 1 if r["is_correct"] else 0
        if pid in pd_ids:
            by_model_pd.setdefault(model, []).append(ic)
        else:
            by_model_rest.setdefault(model, []).append(ic)

    rows = []
    for model in sorted(set(by_model_pd) | set(by_model_rest)):
        pd_v = by_model_pd.get(model, [])
        rest_v = by_model_rest.get(model, [])
        acc_pd = (sum(pd_v) / len(pd_v)) if pd_v else None
        acc_rest = (sum(rest_v) / len(rest_v)) if rest_v else None
        delta = (acc_pd - acc_rest) if (acc_pd is not None and acc_rest is not None) else None
        rows.append({"model": model,
                     "n_pd": len(pd_v),
                     "n_correct_pd": sum(pd_v),
                     "acc_pd": f"{acc_pd:.4f}" if acc_pd is not None else "",
                     "n_rest": len(rest_v),
                     "acc_rest": f"{acc_rest:.4f}" if acc_rest is not None else "",
                     "delta_pp": f"{100*delta:+.2f}" if delta is not None else ""})

    with open(args.out, "w") as f:
        w = csv.DictWriter(f, fieldnames=["model","n_pd","n_correct_pd","acc_pd",
                                          "n_rest","acc_rest","delta_pp"])
        w.writeheader(); w.writerows(rows)

    # Aggregate verifier-overfitting headline number: pooled accuracy across
    # all rows where the eval verifier issued a verdict on a paper-disjoint
    # item. This is the single number that lands in §5.X paragraph #9 [d].
    all_pd = [v for vs in by_model_pd.values() for v in vs]
    if all_pd:
        acc_pooled = sum(all_pd) / len(all_pd)
        print(f"POOLED verifier accuracy on S_paper-disjoint: {acc_pooled:.4f} "
              f"(n={len(all_pd)} model-item pairs across {len(by_model_pd)} models)")
    print(f"Wrote {len(rows)} rows to {args.out}")

if __name__ == "__main__":
    main()
