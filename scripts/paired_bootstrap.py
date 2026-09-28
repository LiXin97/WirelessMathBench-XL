#!/usr/bin/env python3
"""
paired_bootstrap.py: paired-bootstrap analysis for contamination-aware
evaluation.

Protocol:
  - B = 10,000 paired bootstrap resamples, cluster on problem_id, seed=0.
  - Configured WML-7B comparison pairs for appendix reporting.
  - Full C(k,2) matrix for the locked model set; final paper prose uses
    this matrix to check full-vs-S0 point-estimate sign changes, not for
    appropriate-budget pairwise rank claims.
  - Per-bucket accuracy on B0..B4 with boundaries: 0; 1-2; 3-5; 6-10; >=11.
  - Spearman rho(bucket_index, accuracy) per model, with bootstrap CI.

INPUT SCHEMA
  --cleaned-jsonl: output of scripts/cleaned_subset_eval.py
      records: {model, problem_id, candidate, is_correct, rationale,
                in_S0, in_S1, hits_total}
      MISSING rows: is_correct is null  -> DROPPED, never zero-filled.
  --full-csv: per-model per-problem verdicts on the FULL 800-item test split.
      Required columns: model, problem_id, is_correct (0/1).
      If absent or unreadable, the script degrades gracefully to
      "S0-only paired" mode (Delta_full columns left blank, headline
      shows only Delta_S0); a note is emitted into bootstrap-runtime.md
      describing what needs to be wired.
  --out-dir: directory for the three output files.

OUTPUT
  paired-bootstrap-headline.csv  (9 rows, frontier vs WML-7B)
  paired-bootstrap-matrix.csv    (C(k,2) rows; 153 rows for the final 18-model roster)
  bootstrap-runtime.md           (assumptions, n_pairs, n_dropped, table)

CAUTION
  This script does NOT produce paper prose. It surfaces bootstrap numbers;
  interpretation and manuscript wording are downstream.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
try:
    from scipy.stats import rankdata  # type: ignore
except ImportError:
    def rankdata(a):  # average-rank fallback
        a = np.asarray(a, dtype=float)
        order = np.argsort(a, kind="mergesort")
        ranks = np.empty_like(order, dtype=float)
        ranks[order] = np.arange(1, len(a) + 1)
        # average ranks for ties
        sa = a[order]
        i = 0
        while i < len(sa):
            j = i
            while j + 1 < len(sa) and sa[j + 1] == sa[i]:
                j += 1
            if j > i:
                avg = (i + j) / 2.0 + 1.0
                ranks[order[i:j + 1]] = avg
            i = j + 1
        return ranks

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

B_DEFAULT = 10_000
SEED_DEFAULT = 0
CI_ALPHA = 0.05  # 95% CI

# WML-7B comparison set. Names must match the `model` field in
# cleaned-jsonl exactly; some rows are retained for continuity with the locked
# model set and are not used as appropriate-budget rank claims.
HEADLINE_FRONTIER = [
    "openai/gpt-5",
    "deepseek/deepseek-r1",
    "deepseek/deepseek-chat-v3.1",
    "x-ai/grok-4-fast",
    "google/gemini-2.5-flash",
    "anthropic/claude-sonnet-4",
    "openai/gpt-5-mini",
    "openai/o4-mini",
    "google/gemini-2.5-pro",
]
WML_7B = "WirelessMathLM-7B"

# Per §5.X bucket spec.
BUCKET_BOUNDARIES = [(0, 0), (1, 2), (3, 5), (6, 10), (11, 10**9)]
BUCKET_LABELS = ["B0", "B1", "B2", "B3", "B4"]


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_cleaned_jsonl(path: Path) -> pd.DataFrame:
    """Load JSONL, drop MISSING rows (is_correct is None), coerce types."""
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("is_correct") is None:
                continue
            rows.append({
                "model": str(r["model"]),
                "problem_id": str(r["problem_id"]),
                "is_correct": int(bool(r["is_correct"])),
                "in_S0": bool(r.get("in_S0", False)),
                "in_S1": bool(r.get("in_S1", False)),
                "hits_total": int(r.get("hits_total", 0)),
            })
    return pd.DataFrame(rows)


def load_full_csv(path: Path | None) -> pd.DataFrame | None:
    """Load per-model per-problem full-eval verdicts. Returns None if
    missing or schema-incompatible (caller degrades to S0-only mode)."""
    if path is None or not path.exists():
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    needed = {"model", "problem_id", "is_correct"}
    if not needed.issubset(df.columns):
        return None
    df = df.dropna(subset=["is_correct"]).copy()
    df["model"] = df["model"].astype(str)
    df["problem_id"] = df["problem_id"].astype(str)
    df["is_correct"] = df["is_correct"].astype(int)
    return df[["model", "problem_id", "is_correct"]]


# ---------------------------------------------------------------------------
# Bucket assignment
# ---------------------------------------------------------------------------

def assign_bucket(hits: int) -> str:
    for label, (lo, hi) in zip(BUCKET_LABELS, BUCKET_BOUNDARIES):
        if lo <= hits <= hi:
            return label
    return BUCKET_LABELS[-1]


# ---------------------------------------------------------------------------
# Cluster bootstrap on problem_id
# ---------------------------------------------------------------------------

def build_pivot(df: pd.DataFrame) -> tuple[np.ndarray, list[str], list[str]]:
    """Pivot to a (n_problems, n_models) int8 matrix of is_correct.
    Drops any (model, problem) pair that lacks a verdict by intersecting
    only over problem_ids present for ALL models."""
    pv = df.pivot_table(index="problem_id", columns="model",
                        values="is_correct", aggfunc="first")
    pv = pv.dropna(axis=0, how="any")
    pids = pv.index.astype(str).tolist()
    models = pv.columns.astype(str).tolist()
    M = pv.to_numpy(dtype=np.int8)
    return M, pids, models


def paired_bootstrap_deltas(M: np.ndarray, B: int, seed: int) -> np.ndarray:
    """Cluster bootstrap. M shape: (n_problems, n_models).
    Returns boot_acc shape: (B, n_models) of per-model accuracies."""
    n = M.shape[0]
    rng = np.random.default_rng(seed)
    out = np.empty((B, M.shape[1]), dtype=np.float64)
    for b in range(B):
        idx = rng.integers(0, n, size=n)
        out[b] = M[idx].mean(axis=0)
    return out


def ci(x: np.ndarray, alpha: float = CI_ALPHA) -> tuple[float, float]:
    lo = float(np.quantile(x, alpha / 2))
    hi = float(np.quantile(x, 1 - alpha / 2))
    return lo, hi


def two_sided_p_from_boot(deltas_boot: np.ndarray) -> float:
    """Two-sided bootstrap p-value: 2 * min(P(d<=0), P(d>=0)), clipped to (0,1]."""
    n = len(deltas_boot)
    p_le = (deltas_boot <= 0).mean()
    p_ge = (deltas_boot >= 0).mean()
    p = 2 * min(p_le, p_ge)
    return float(min(max(p, 1.0 / (n + 1)), 1.0))


# ---------------------------------------------------------------------------
# Multiple-testing corrections
# ---------------------------------------------------------------------------

def bonferroni(pvals: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    return pvals * len(pvals) <= alpha


def bh_fdr(pvals: np.ndarray, q: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg. Returns boolean mask of rejections."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    ranked = p[order]
    thresh = q * (np.arange(1, m + 1) / m)
    passed = ranked <= thresh
    if not passed.any():
        return np.zeros(m, dtype=bool)
    k = np.max(np.where(passed)[0])
    rej = np.zeros(m, dtype=bool)
    rej[order[: k + 1]] = True
    return rej


def holm_bonferroni(pvals: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Holm-Bonferroni family-wise correction."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    rejected = np.zeros(m, dtype=bool)
    for rank, idx in enumerate(order):
        if p[idx] <= alpha / (m - rank):
            rejected[idx] = True
        else:
            break
    return rejected


# ---------------------------------------------------------------------------
# Spearman rho with bootstrap CI (per-model bucket-vs-accuracy)
# ---------------------------------------------------------------------------

def spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    rx = rankdata(x)
    ry = rankdata(y)
    return float(np.corrcoef(rx, ry)[0, 1])


def per_bucket_accuracy(df: pd.DataFrame) -> pd.DataFrame:
    """Per (model, bucket) accuracy from a long DF with hits_total."""
    df = df.copy()
    df["bucket"] = df["hits_total"].apply(assign_bucket)
    g = df.groupby(["model", "bucket"])["is_correct"].agg(["mean", "size"]).reset_index()
    g.columns = ["model", "bucket", "accuracy", "n"]
    return g


def spearman_with_ci(df: pd.DataFrame, B: int, seed: int) -> pd.DataFrame:
    """Per-model Spearman(bucket_index, per-problem is_correct) with paired
    bootstrap CI on problem-level resamples. Bucket index is 0..4."""
    out = []
    rng = np.random.default_rng(seed)
    for model, sub in df.groupby("model"):
        sub = sub.copy()
        sub["bidx"] = sub["hits_total"].apply(
            lambda h: BUCKET_LABELS.index(assign_bucket(h)))
        x = sub["bidx"].to_numpy()
        y = sub["is_correct"].to_numpy()
        rho = spearman(x, y)
        n = len(x)
        if n < 2:
            out.append({"model": model, "rho": rho, "ci_low": float("nan"),
                        "ci_high": float("nan"), "n": n})
            continue
        boots = np.empty(B, dtype=np.float64)
        for b in range(B):
            idx = rng.integers(0, n, size=n)
            boots[b] = spearman(x[idx], y[idx])
        valid = boots[~np.isnan(boots)]
        lo, hi = ci(valid)
        p = two_sided_p_from_boot(valid)
        out.append({"model": model, "rho": rho, "ci_low": lo,
                    "ci_high": hi, "p_boot": p, "n": n})
    result = pd.DataFrame(out).sort_values("model").reset_index(drop=True)
    if len(result):
        result["holm_significant"] = holm_bonferroni(result["p_boot"].to_numpy(), alpha=0.05)
    return result


# ---------------------------------------------------------------------------
# Headline + matrix bootstrap
# ---------------------------------------------------------------------------

def run_pair_bootstrap(M: np.ndarray, models: list[str],
                       B: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Returns:
       boot_acc:  (B, n_models)
       point_acc: (n_models,)   (un-resampled point estimate)
    """
    boot_acc = paired_bootstrap_deltas(M, B=B, seed=seed)
    point_acc = M.mean(axis=0)
    return boot_acc, point_acc


def headline_table(boot_S0: np.ndarray, pt_S0: np.ndarray, models_S0: list[str],
                   boot_full: np.ndarray | None, pt_full: np.ndarray | None,
                   models_full: list[str] | None) -> pd.DataFrame:
    """Build the 9-pair headline table."""
    rows = []
    if WML_7B not in models_S0:
        # Cannot pair against WML-7B; emit empty headline with note.
        return pd.DataFrame(columns=[
            "model_i", "model_j", "delta_full", "ci_low_full", "ci_high_full",
            "delta_S0", "ci_low_S0", "ci_high_S0", "p_S0", "p_full",
            "sign_change", "bonferroni_significant"])
    j = models_S0.index(WML_7B)
    pvals_S0 = []
    for mi in HEADLINE_FRONTIER:
        if mi not in models_S0:
            continue
        i = models_S0.index(mi)
        d_S0_boot = boot_S0[:, i] - boot_S0[:, j]
        d_S0 = pt_S0[i] - pt_S0[j]
        lo_S0, hi_S0 = ci(d_S0_boot)
        p_S0 = two_sided_p_from_boot(d_S0_boot)
        pvals_S0.append(p_S0)

        if (boot_full is not None and pt_full is not None and models_full is not None
                and mi in models_full and WML_7B in models_full):
            i2 = models_full.index(mi)
            j2 = models_full.index(WML_7B)
            d_full_boot = boot_full[:, i2] - boot_full[:, j2]
            d_full = pt_full[i2] - pt_full[j2]
            lo_full, hi_full = ci(d_full_boot)
            p_full = two_sided_p_from_boot(d_full_boot)
            sign_change = (np.sign(d_full) != np.sign(d_S0)) and (d_full != 0) and (d_S0 != 0)
        else:
            d_full, lo_full, hi_full, p_full, sign_change = (
                float("nan"), float("nan"), float("nan"), float("nan"), False)

        rows.append({
            "model_i": mi, "model_j": WML_7B,
            "delta_full": d_full, "ci_low_full": lo_full, "ci_high_full": hi_full,
            "delta_S0": d_S0, "ci_low_S0": lo_S0, "ci_high_S0": hi_S0,
            "p_S0": p_S0, "p_full": p_full,
            "sign_change": bool(sign_change),
        })
    df = pd.DataFrame(rows)
    if len(df):
        df["bonferroni_significant"] = bonferroni(df["p_S0"].to_numpy(), alpha=0.05)
    return df


def matrix_table(boot_S0: np.ndarray, pt_S0: np.ndarray, models_S0: list[str],
                 boot_full: np.ndarray | None, pt_full: np.ndarray | None,
                 models_full: list[str] | None) -> pd.DataFrame:
    """Full C(n,2) pair matrix on S0; full-eval columns where available;
    BH-FDR(q=0.05) is emitted as an exploratory column. The submitted paper
    uses the matrix only for full-vs-S0 point-estimate sign-change checks."""
    rows = []
    n = len(models_S0)
    for i in range(n):
        for jj in range(i + 1, n):
            mi, mj = models_S0[i], models_S0[jj]
            d_boot = boot_S0[:, i] - boot_S0[:, jj]
            d = pt_S0[i] - pt_S0[jj]
            lo, hi = ci(d_boot)
            p = two_sided_p_from_boot(d_boot)
            full_d = full_lo = full_hi = float("nan")
            sign_change = False
            if (boot_full is not None and pt_full is not None and models_full is not None
                    and mi in models_full and mj in models_full):
                i2 = models_full.index(mi)
                j2 = models_full.index(mj)
                fb = boot_full[:, i2] - boot_full[:, j2]
                full_d = pt_full[i2] - pt_full[j2]
                full_lo, full_hi = ci(fb)
                sign_change = (np.sign(full_d) != np.sign(d)) and (full_d != 0) and (d != 0)
            rows.append({
                "model_i": mi, "model_j": mj,
                "delta_full": full_d, "ci_low_full": full_lo, "ci_high_full": full_hi,
                "delta_S0": d, "ci_low_S0": lo, "ci_high_S0": hi,
                "p_S0": p, "sign_change": bool(sign_change),
            })
    df = pd.DataFrame(rows)
    if len(df):
        df["bh_fdr_significant"] = bh_fdr(df["p_S0"].to_numpy(), q=0.05)
    return df


# ---------------------------------------------------------------------------
# Runtime summary
# ---------------------------------------------------------------------------

def write_runtime_md(out_path: Path, B: int, n_pairs: int, n_dropped: int,
                     n_models: int, n_problems: int, mode: str,
                     headline: pd.DataFrame, bucket_acc: pd.DataFrame,
                     spearman_df: pd.DataFrame, full_join_note: str) -> None:
    lines = []
    lines.append("# paired_bootstrap.py runtime summary")
    lines.append("")
    lines.append(f"- B = {B}, seed = 0, cluster bootstrap on `problem_id`.")
    lines.append(f"- mode = **{mode}**.")
    lines.append(f"- n_models (cleaned subset, after MISSING drop) = {n_models}")
    lines.append(f"- n_problems (intersected across all models) = {n_problems}")
    lines.append(f"- n_pairs in matrix = {n_pairs}")
    lines.append(f"- n_dropped (MISSING rows in cleaned-jsonl) = {n_dropped}")
    lines.append(f"- full-eval join note: {full_join_note}")
    lines.append("")
    lines.append("## Configured WML-7B comparison pairs")
    lines.append("")
    if len(headline):
        lines.append("| model_i | Δ_full | 95% CI full | Δ_S0 | 95% CI S0 | sign_change | bonf_sig |")
        lines.append("|---|---|---|---|---|---|---|")
        for _, r in headline.iterrows():
            lines.append(
                f"| {r['model_i']} | {r['delta_full']:+.4f} | "
                f"[{r['ci_low_full']:+.4f}, {r['ci_high_full']:+.4f}] | "
                f"{r['delta_S0']:+.4f} | "
                f"[{r['ci_low_S0']:+.4f}, {r['ci_high_S0']:+.4f}] | "
                f"{r['sign_change']} | {r['bonferroni_significant']} |"
            )
    else:
        lines.append("(empty — WML-7B not present in cleaned-jsonl roster)")
    lines.append("")
    lines.append("## Per-bucket accuracy (B0=0, B1=1-2, B2=3-5, B3=6-10, B4>=11)")
    lines.append("")
    if len(bucket_acc):
        wide = bucket_acc.pivot(index="model", columns="bucket", values="accuracy")
        wide = wide.reindex(columns=BUCKET_LABELS)
        lines.append("| model | " + " | ".join(BUCKET_LABELS) + " |")
        lines.append("|" + "---|" * (len(BUCKET_LABELS) + 1))
        for model, row in wide.iterrows():
            cells = [f"{v:.3f}" if pd.notna(v) else "—" for v in row]
            lines.append(f"| {model} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Per-model Spearman ρ(bucket_index, accuracy)")
    lines.append("")
    if len(spearman_df):
        lines.append("| model | ρ | 95% CI | p_boot | Holm sig. | n |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for _, r in spearman_df.iterrows():
            lo = r["ci_low"]; hi = r["ci_high"]
            ci_str = f"[{lo:+.3f}, {hi:+.3f}]" if pd.notna(lo) else "—"
            rho_str = f"{r['rho']:+.3f}" if pd.notna(r['rho']) else "—"
            p_str = f"{r['p_boot']:.4g}" if pd.notna(r.get('p_boot')) else "—"
            sig = bool(r.get("holm_significant", False))
            lines.append(f"| {r['model']} | {rho_str} | {ci_str} | {p_str} | {sig} | {int(r['n'])} |")
    lines.append("")
    lines.append("## Notes for contamination-audit caption/prose")
    lines.append("- All numbers above are TERMINAL outputs of D13.")
    lines.append("- The paper prose is written separately; this script only emits numbers.")
    lines.append("- `sign_change=True` rows are candidates for the rank-flip column "
                 "of the audited leaderboard checks.")
    out_path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def make_synthetic_jsonl(path: Path, n_problems: int = 200, seed: int = 0) -> int:
    """Write a synthetic cleaned-jsonl. Returns count of MISSING rows written."""
    rng = np.random.default_rng(seed)
    models = HEADLINE_FRONTIER + [
        "openai/gpt-4o", WML_7B, "openai/gpt-5-nano",
        "meta-llama/llama-3.3-70b-instruct", "qwen/qwen-2.5-72b-instruct",
        "Qwen2.5-Math-7B-Instruct", "deepseek-math-7b-rl",
        "WirelessMathLM-3B", "WirelessMathLM-0.5B",
    ]
    # per-model true accuracy, vaguely calibrated to eval-results.md ranks
    true_acc = np.linspace(0.58, 0.18, num=len(models))
    n_missing = 0
    with open(path, "w") as f:
        for pid in range(n_problems):
            hits = int(rng.integers(0, 15))
            in_S0 = (hits == 0)
            in_S1 = (hits <= 2)  # synthetic self-test only
            for mi, model in enumerate(models):
                # 1% MISSING per (model, problem)
                if rng.random() < 0.01:
                    n_missing += 1
                    f.write(json.dumps({
                        "model": model, "problem_id": f"P{pid:04d}",
                        "candidate": None, "is_correct": None,
                        "rationale": "MISSING: synthetic",
                        "in_S0": in_S0, "in_S1": in_S1, "hits_total": hits,
                    }) + "\n")
                    continue
                # contamination boost: more hits -> easier
                p = true_acc[mi] + 0.02 * hits
                p = float(np.clip(p, 0.0, 0.99))
                ok = bool(rng.random() < p)
                f.write(json.dumps({
                    "model": model, "problem_id": f"P{pid:04d}",
                    "candidate": "x", "is_correct": ok, "rationale": "ok",
                    "in_S0": in_S0, "in_S1": in_S1, "hits_total": hits,
                }) + "\n")
    return n_missing


def make_synthetic_full_csv(path: Path, jsonl_path: Path) -> None:
    """Build a synthetic full-eval CSV from the same problem_ids."""
    df = load_cleaned_jsonl(jsonl_path)
    rng = np.random.default_rng(1)
    pids = sorted(df["problem_id"].unique())
    models = sorted(df["model"].unique())
    rows = []
    for m in models:
        base = df[df["model"] == m]["is_correct"].mean()
        for pid in pids:
            # "full" eval = same problems + 600 extra; here: same set, slight noise
            ok = int(rng.random() < base * 1.02)
            rows.append({"model": m, "problem_id": pid, "is_correct": ok})
    pd.DataFrame(rows).to_csv(path, index=False)


def self_test(out_dir: Path, B: int = 500) -> int:
    """End-to-end on synthetic input. Uses a smaller B for speed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "_synth_cleaned.jsonl"
    full = out_dir / "_synth_full.csv"
    n_missing = make_synthetic_jsonl(jsonl, n_problems=150, seed=0)
    make_synthetic_full_csv(full, jsonl)
    print(f"[self-test] synthetic written: {jsonl} ({n_missing} MISSING) + {full}")
    rc = run(jsonl, full, out_dir, B=B, seed=0)
    print(f"[self-test] run() returned {rc}")
    # Sanity checks
    head = pd.read_csv(out_dir / "paired-bootstrap-headline.csv")
    mat = pd.read_csv(out_dir / "paired-bootstrap-matrix.csv")
    assert len(head) == 9, f"headline rows = {len(head)} (expect 9)"
    n_models = len(pd.unique(pd.concat([mat["model_i"], mat["model_j"]])))
    expected_pairs = n_models * (n_models - 1) // 2
    assert len(mat) == expected_pairs, f"matrix rows = {len(mat)} (expect {expected_pairs})"
    for col in ("delta_S0", "ci_low_S0", "ci_high_S0", "p_S0",
                "bonferroni_significant"):
        assert col in head.columns, f"headline missing column {col}"
    for col in ("delta_S0", "p_S0", "bh_fdr_significant"):
        assert col in mat.columns, f"matrix missing column {col}"
    print(f"[self-test] OK: headline=9 rows, matrix={expected_pairs} rows, schema validated.")
    return 0


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(cleaned_jsonl: Path, full_csv: Path | None, out_dir: Path,
        B: int = B_DEFAULT, seed: int = SEED_DEFAULT) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    df_all = load_cleaned_jsonl(cleaned_jsonl)
    n_dropped_total = 0  # we already filtered on load; re-count from raw
    with open(cleaned_jsonl) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("is_correct") is None:
                n_dropped_total += 1

    # S0 subset only for headline + matrix.
    df_S0 = df_all[df_all["in_S0"]].copy()
    if df_S0.empty:
        print("[paired_bootstrap] ERROR: no in_S0=True rows in cleaned-jsonl",
              file=sys.stderr)
        return 2

    M_S0, pids_S0, models_S0 = build_pivot(df_S0)
    print(f"[paired_bootstrap] S0 pivot: {M_S0.shape[0]} problems x {M_S0.shape[1]} models")
    boot_S0, pt_S0 = run_pair_bootstrap(M_S0, models_S0, B=B, seed=seed)

    # Full-eval (optional). Keep the full 800-item domain separate from the
    # S0 pivot. Earlier drafts incorrectly restricted this to pids_S0, which
    # made delta_full identical to delta_S0 by construction.
    df_full = load_full_csv(full_csv) if full_csv is not None else None
    boot_full = pt_full = None
    models_full: list[str] | None = None
    full_join_note = ""
    if df_full is not None and not df_full.empty:
        if df_full.empty:
            full_join_note = ("full-csv loaded but contains no valid rows — "
                              "degraded to S0-only mode.")
            df_full = None
        else:
            M_full, _, models_full = build_pivot(df_full)
            boot_full, pt_full = run_pair_bootstrap(M_full, models_full, B=B, seed=seed)
            full_join_note = (f"full-csv loaded on full domain: {M_full.shape[0]} problems x "
                              f"{M_full.shape[1]} models. S0 columns use the "
                              f"separate {M_S0.shape[0]}-problem S0 pivot.")
    if df_full is None or boot_full is None:
        if not full_join_note:
            full_join_note = (
                "full-csv missing or unreadable — running in S0-only mode. "
                "Provide a CSV (model, problem_id, is_correct) for the full "
                "800-item test split to compute full-vs-cleaned deltas.")
        mode = "S0-only paired"
    else:
        mode = "S0 + full paired"

    headline = headline_table(boot_S0, pt_S0, models_S0,
                              boot_full, pt_full, models_full)
    matrix = matrix_table(boot_S0, pt_S0, models_S0,
                          boot_full, pt_full, models_full)

    headline.to_csv(out_dir / "paired-bootstrap-headline.csv", index=False)
    matrix.to_csv(out_dir / "paired-bootstrap-matrix.csv", index=False)

    # Per-bucket accuracy + Spearman (uses S0 superset = df_all so buckets B1..B4 exist).
    bucket_acc = per_bucket_accuracy(df_all)
    spearman_df = spearman_with_ci(df_all, B=B, seed=seed)

    write_runtime_md(out_dir / "bootstrap-runtime.md",
                     B=B, n_pairs=len(matrix), n_dropped=n_dropped_total,
                     n_models=len(models_S0), n_problems=len(pids_S0),
                     mode=mode, headline=headline, bucket_acc=bucket_acc,
                     spearman_df=spearman_df, full_join_note=full_join_note)
    print(f"[paired_bootstrap] wrote {out_dir}/paired-bootstrap-headline.csv "
          f"({len(headline)} rows)")
    print(f"[paired_bootstrap] wrote {out_dir}/paired-bootstrap-matrix.csv "
          f"({len(matrix)} rows)")
    print(f"[paired_bootstrap] wrote {out_dir}/bootstrap-runtime.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cleaned-jsonl", type=Path,
                   help="output of cleaned_subset_eval.py")
    p.add_argument("--full-csv", type=Path, default=None,
                   help="per-model per-problem full-eval verdicts "
                        "(model,problem_id,is_correct); optional.")
    p.add_argument("--out-dir", type=Path, required=False)
    p.add_argument("--B", type=int, default=B_DEFAULT)
    p.add_argument("--seed", type=int, default=SEED_DEFAULT)
    p.add_argument("--self-test", action="store_true",
                   help="run end-to-end on synthetic data (no real inputs needed)")
    args = p.parse_args(argv)

    if args.self_test:
        out = args.out_dir or Path("/tmp/paired_bootstrap_selftest")
        return self_test(out, B=min(args.B, 500))
    if not args.cleaned_jsonl or not args.out_dir:
        p.error("--cleaned-jsonl and --out-dir are required (unless --self-test)")
    return run(args.cleaned_jsonl, args.full_csv, args.out_dir,
               B=args.B, seed=args.seed)


if __name__ == "__main__":
    sys.exit(main())
