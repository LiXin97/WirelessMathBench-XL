#!/usr/bin/env python3
"""Re-score every evaluated row on the 310-item public test subset.

Inputs are the released per-item verdicts and public test ids. Accuracy is
reported on the full 800-item split and on the public subset, with a 95%
percentile bootstrap interval over public-subset items (B=10,000, seed 0 per row).
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ROWS = [
    ("F", "GPT-5-mini", "frontier_16k", "openai/gpt-5-mini"),
    ("F", "GPT-5.2-chat", "frontier_16k", "openai/gpt-5.2-chat"),
    ("F", "GPT-4.1-mini", "frontier_16k", "openai/gpt-4.1-mini"),
    ("F", "Gemini-2.5-Pro", "frontier_16k", "google/gemini-2.5-pro"),
    ("F", "Gemini-2.5-Flash", "frontier_16k", "google/gemini-2.5-flash"),
    ("D1", "Grok-4-Fast", "locked_2k", "x-ai/grok-4-fast"),
    ("D2", "DeepSeek-V3.1", "locked_2k", "deepseek/deepseek-chat-v3.1"),
    ("D3", "Claude-4.0-Sonnet", "locked_2k", "anthropic/claude-sonnet-4"),
    ("D4", "o4-mini", "locked_2k", "openai/o4-mini"),
    ("D5", "DeepSeek-R1†", "locked_2k", "deepseek/deepseek-r1"),
    ("D6", "GPT-4o†", "locked_2k", "openai/gpt-4o"),
    ("D7", "Qwen2.5-72B-Instruct", "locked_2k", "qwen/qwen-2.5-72b-instruct"),
    ("D8", "Llama-3.3-70B-Instruct", "locked_2k", "meta-llama/llama-3.3-70b-instruct"),
    ("D9", "GPT-5-nano", "locked_2k", "openai/gpt-5-nano"),
    ("D10", "WirelessMathLM-7B", "locked_2k", "WirelessMathLM-7B"),
    ("D11", "DeepSeekMath-7B-RL", "locked_2k", "deepseek-math-7b-rl"),
    ("D12", "Qwen2.5-Math-7B-Instruct", "locked_2k", "Qwen2.5-Math-7B-Instruct"),
    ("D13", "WirelessMathLM-3B", "locked_2k", "WirelessMathLM-3B"),
    ("D14", "WirelessMathLM-0.5B", "locked_2k", "WirelessMathLM-0.5B"),
]


def load(path: Path) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    with path.open() as fh:
        for line in fh:
            r = json.loads(line)
            out.setdefault(r["model"], {})[str(r["problem_id"])] = int(r["is_correct"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdict-dir", type=Path, default=ROOT / "data/verdicts")
    ap.add_argument("--public-ids", type=Path, default=ROOT / "data/public_test_ids.json")
    ap.add_argument("--out", type=Path, default=ROOT / "data/public_subset_results.csv")
    ap.add_argument("--B", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    ids = sorted((str(x) for x in json.load(args.public_ids.open())), key=int)
    verdicts = {name: load(args.verdict_dir / f"{name}.jsonl") for name in ("frontier_16k", "locked_2k")}
    with args.out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["group", "model", "acc_full800", "acc_public310", "ci_low", "ci_high", "delta_pp"])
        for group, label, view, model in ROWS:
            v = verdicts[view][model]
            full = 100 * sum(v.values()) / len(v)
            arr = np.array([v[p] for p in ids], dtype=np.int8)
            rng = np.random.default_rng(args.seed)
            boot = 100 * arr[rng.integers(0, len(arr), size=(args.B, len(arr)))].mean(axis=1)
            pub = 100 * arr.mean()
            w.writerow([group, label, round(full, 2), round(pub, 2),
                        round(float(np.quantile(boot, 0.025)), 2),
                        round(float(np.quantile(boot, 0.975)), 2), round(pub - full, 2)])
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
