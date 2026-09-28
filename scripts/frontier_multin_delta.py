#!/usr/bin/env python3
"""Compute frontier full-vs-cleaned deltas under multiple n-gram thresholds.

The script reuses saved 800-item verdicts and swaps only the S0 membership
label from RedPajama-ArXiv audits run on the same 800 test items. It does not
rerun models.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERDICTS: list[Path] = []
DEFAULT_OUT_DIR = ROOT / "derived/frontier-multin-delta"
FRONTIER_MODELS = [
    "openai/gpt-5-mini",
    "openai/gpt-5.2-chat",
    "openai/gpt-4.1-mini",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
]
MODEL_LABELS = {
    "openai/gpt-5-mini": "GPT-$5$-mini",
    "openai/gpt-5.2-chat": "GPT-$5.2$-chat",
    "openai/gpt-4.1-mini": "GPT-$4.1$-mini",
    "google/gemini-2.5-pro": "Gemini-$2.5$-Pro",
    "google/gemini-2.5-flash": "Gemini-$2.5$-Flash",
}


def load_verdicts(paths: list[Path]) -> dict[str, dict[str, int]]:
    by_model: dict[str, dict[str, int]] = defaultdict(dict)
    for path in paths:
        with path.open() as fh:
            for line in fh:
                r = json.loads(line)
                model = str(r["model"])
                if model not in FRONTIER_MODELS:
                    continue
                if r.get("is_correct") is None:
                    continue
                by_model[model][str(r["problem_id"])] = int(bool(r["is_correct"]))
    missing = [m for m in FRONTIER_MODELS if len(by_model.get(m, {})) != 800]
    if missing:
        detail = {m: len(by_model.get(m, {})) for m in FRONTIER_MODELS}
        raise SystemExit(f"expected 800 verdicts per frontier model; got {detail}")
    return by_model


def load_s0(n: int, audit_dir: Path) -> dict[str, int]:
    path = audit_dir / f"audit-n{n}" / "contamination-audit.jsonl"
    if not path.exists():
        raise SystemExit(f"missing audit labels for n={n}: {path}")
    flags: dict[str, int] = {}
    with path.open() as fh:
        for line in fh:
            r = json.loads(line)
            flags[str(r["problem_id"])] = int(bool(r.get("in_S0")))
    if len(flags) != 800:
        raise SystemExit(f"expected 800 audit rows for n={n}; got {len(flags)}")
    return flags


def bootstrap_delta(ic: np.ndarray, in_s0: np.ndarray, B: int, seed: int) -> tuple[float, float, float]:
    n = len(ic)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(B, n))
    ic_b = ic[idx]
    s0_b = in_s0[idx]
    cf = ic_b.sum(axis=1)
    cs = (ic_b & s0_b).sum(axis=1)
    ns = s0_b.sum(axis=1)
    keep = ns > 0
    deltas = (cf[keep] / n) - (cs[keep] / ns[keep])
    return (float(np.quantile(deltas, 0.025)) * 100,
            float(np.quantile(deltas, 0.975)) * 100,
            float(np.max(np.abs(deltas))) * 100)


def fmt_delta(x: float) -> str:
    return f"{x:+.2f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", nargs="+", type=int, default=[8, 10, 12, 13, 15])
    ap.add_argument("--verdict-jsonl", action="append", type=Path, default=[],
                    help="saved model-response JSONL file; repeat for multiple files")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--audit-dir", type=Path, default=DEFAULT_OUT_DIR,
                    help="directory containing audit-n*/contamination-audit.jsonl files for the test split")
    ap.add_argument("--B", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    verdict_paths = args.verdict_jsonl or DEFAULT_VERDICTS
    if not verdict_paths:
        raise SystemExit("provide at least one --verdict-jsonl file with saved 800-item verdicts")
    verdicts = load_verdicts(verdict_paths)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    for n in args.n:
        flags = load_s0(n, args.audit_dir)
        pids = sorted(flags)
        in_s0 = np.array([flags[p] for p in pids], dtype=np.int8)
        n_s0 = int(in_s0.sum())
        for model in FRONTIER_MODELS:
            d = verdicts[model]
            if set(d) != set(flags):
                raise SystemExit(f"problem-id mismatch for {model} at n={n}")
            ic = np.array([d[p] for p in pids], dtype=np.int8)
            acc_full = float(ic.mean()) * 100
            acc_s0 = float((ic & in_s0).sum() / n_s0) * 100
            delta = acc_full - acc_s0
            lo, hi, boot_max_abs = bootstrap_delta(ic, in_s0, args.B, args.seed + n)
            rows.append({
                "n": n,
                "model": model,
                "model_label": MODEL_LABELS[model],
                "n_full": len(pids),
                "acc_full": acc_full,
                "n_S0": n_s0,
                "s0_pct": n_s0 / len(pids) * 100,
                "acc_S0": acc_s0,
                "delta_pp": delta,
                "ci_low_pp": lo,
                "ci_high_pp": hi,
                "bootstrap_max_abs_pp": boot_max_abs,
            })

    csv_path = args.out_dir / "frontier-multin-delta.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Compact TeX table for the main text: point deltas only; CIs remain in CSV.
    by_n: dict[int, dict[str, dict[str, object]]] = defaultdict(dict)
    for r in rows:
        by_n[int(r["n"])][str(r["model"])] = r
    tex_path = args.out_dir / "frontier-multin-delta-table.tex"
    with tex_path.open("w") as fh:
        fh.write("% Auto-generated by scripts/frontier_multin_delta.py\n")
        fh.write("\\begin{table}[t]\n\\centering\n")
        fh.write("\\caption{Threshold sensitivity of the frontier full-vs-cleaned comparison. Each cell is $\\Delta=\\mathrm{Full}-\\mathcal{S}_0^{(n)}$ in percentage points using saved $16$k frontier verdicts; paired-bootstrap intervals are released in the accompanying CSV.}\n")
        fh.write("\\label{tab:frontier_ngram_delta}\n")
        fh.write("\\scriptsize\n\\setlength{\\tabcolsep}{3pt}\n")
        fh.write("\\begin{tabular}{rccrrrrr}\n\\toprule\n")
        fh.write("$n$ & $|\\mathcal{S}_0^{(n)}|$ & $\\mathcal{S}_0^{(n)}$ \\% & GPT-$5$-mini & GPT-$5.2$-chat & GPT-$4.1$-mini & Gemini-Pro & Gemini-Flash \\\\\n")
        fh.write("\\midrule\n")
        for n in args.n:
            first = by_n[n][FRONTIER_MODELS[0]]
            cells = [
                str(n),
                f"{int(first['n_S0'])}/800",
                f"{float(first['s0_pct']):.1f}",
            ]
            cells.extend(fmt_delta(float(by_n[n][m]["delta_pp"])) for m in FRONTIER_MODELS)
            fh.write(" & ".join(cells) + " \\\\\n")
        fh.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")

    md_path = args.out_dir / "frontier-multin-delta.md"
    with md_path.open("w") as fh:
        fh.write("# Frontier multi-n full-vs-S0 sensitivity\n\n")
        fh.write("Generated from saved verdicts; no model reruns. Delta is Full - S0 in pp.\n\n")
        fh.write("| n | S0 test | S0 % | " + " | ".join(MODEL_LABELS[m].replace('$','') for m in FRONTIER_MODELS) + " |\n")
        fh.write("|---:|---:|---:|" + "---:|" * len(FRONTIER_MODELS) + "\n")
        for n in args.n:
            first = by_n[n][FRONTIER_MODELS[0]]
            cells = [str(n), f"{int(first['n_S0'])}/800", f"{float(first['s0_pct']):.1f}"]
            cells.extend(fmt_delta(float(by_n[n][m]["delta_pp"])) for m in FRONTIER_MODELS)
            fh.write("| " + " | ".join(cells) + " |\n")

    print(f"wrote {csv_path}")
    print(f"wrote {tex_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
