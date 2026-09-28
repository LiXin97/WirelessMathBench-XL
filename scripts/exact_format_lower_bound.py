#!/usr/bin/env python
"""Compute a no-LLM exact-format lower-bound check from saved verdicts.

This script does not reproduce the production verifier. It scores existing
model responses using only deterministic rules: MCQ letter extraction and exact
comparison of extracted ``\boxed{...}`` answers after lightweight LaTeX
normalisation. The resulting accuracies are lower-bound checks for the
full-vs-S0 contamination comparison, not replacement leaderboard numbers.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import re
from pathlib import Path


DEFAULT_VERDICT_GLOBS: list[str] = []


def extract_boxed(text: str) -> list[str]:
    out: list[str] = []
    i = 0
    token = "\\boxed"
    while True:
        j = text.find(token, i)
        if j < 0:
            break
        k = text.find("{", j + len(token))
        if k < 0:
            i = j + len(token)
            continue
        depth = 0
        start = k + 1
        for t in range(k, len(text)):
            if text[t] == "{":
                depth += 1
            elif text[t] == "}":
                depth -= 1
                if depth == 0:
                    out.append(text[start:t])
                    i = t + 1
                    break
        else:
            i = k + 1
    return out


def normalise_math(text: str) -> str:
    text = text.lower().replace("−", "-")
    for cmd in [
        r"\mathbf",
        r"\boldsymbol",
        r"\mathrm",
        r"\mathsf",
        r"\mathcal",
        r"\operatorname",
        r"\text",
    ]:
        text = text.replace(cmd, "")
    for tok in [
        r"\left",
        r"\right",
        r"\,",
        r"\!",
        r"\;",
        r"\:",
        r"\quad",
        r"\qquad",
        r"\boxed",
    ]:
        text = text.replace(tok, "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^a-z0-9\\{}_^+\-*/=<>.,()\[\]]", "", text)
    return text.replace("{", "").replace("}", "")


def reference_parts(answer: str) -> list[str]:
    boxed = extract_boxed(answer)
    if boxed:
        return [normalise_math(x) for x in boxed]
    return [normalise_math(answer)]


def extract_mcq_letter(candidate: str) -> str:
    patterns = [
        r"(?i)final answer is\s*[:\-]?\s*\**\(?([ABCD])\)?",
        r"(?i)answer is\s*[:\-]?\s*\**\(?([ABCD])\)?",
        r"(?i)option\s+([ABCD])",
        r"(?i)\b([ABCD])\s*(?:is correct|\(correct\))",
    ]
    for pattern in patterns:
        matches = list(re.finditer(pattern, candidate))
        if matches:
            return matches[-1].group(1).upper()
    for boxed in reversed(extract_boxed(candidate)):
        match = re.search(r"\b([ABCD])\b", boxed.strip(), re.I)
        if match:
            return match.group(1).upper()
    tail = candidate[-400:]
    matches = list(re.finditer(r"\b([ABCD])\b", tail))
    return matches[-1].group(1).upper() if matches else ""


def exact_format_correct(candidate: str | None, answer: str, problem_type: str) -> bool:
    if not candidate:
        return False
    if problem_type == "MCQ":
        return extract_mcq_letter(candidate) == answer.strip().upper()

    refs = reference_parts(answer)
    boxes = [normalise_math(x) for x in extract_boxed(candidate)]
    if boxes:
        if len(boxes) >= len(refs) and boxes[-len(refs) :] == refs:
            return True
        pos = 0
        for ref in refs:
            found = False
            while pos < len(boxes):
                if boxes[pos] == ref:
                    found = True
                    pos += 1
                    break
                pos += 1
            if not found:
                return False
        return True

    normalised_candidate = normalise_math(candidate)
    return all(ref and ref in normalised_candidate for ref in refs)


def load_test_problems(path: Path) -> dict[str, dict]:
    problems = {}
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("split") == "test":
                problems[str(row["problem_id"])] = row
    return problems


def view_label(path: Path, model: str) -> tuple[str, str]:
    text = str(path)
    if "d6-fulltest-approp/full-mini-16k" in text and "gpt-5-mini" in model:
        return "frontier-16k", "GPT-5-mini"
    if "d6-fulltest-approp/full/" in text:
        if "gpt-5.2-chat" in model:
            return "frontier-16k", "GPT-5.2-chat"
        if "gpt-4.1-mini" in model:
            return "frontier-16k", "GPT-4.1-mini"
        if "gemini-2.5-pro" in model:
            return "frontier-16k", "Gemini-2.5-Pro"
        if "gemini-2.5-flash" in model:
            return "frontier-16k", "Gemini-2.5-Flash"
    if "d6-fulltest" in text and model == "WirelessMathLM-7B":
        return "locked-2k", "WirelessMathLM-7B"
    if "d6-fulltest" in text and model == "deepseek-math-7b-rl":
        return "locked-2k", "DeepSeekMath-7B-RL"
    if "d6-fulltest" in text and model == "Qwen2.5-Math-7B-Instruct":
        return "locked-2k", "Qwen2.5-Math-7B-Instruct"
    return "", ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problems", default="data/problems_cc_by.jsonl")
    parser.add_argument("--out", required=True)
    parser.add_argument("--verdict-glob", action="append", default=[])
    args = parser.parse_args()

    problems = load_test_problems(Path(args.problems))
    globs = args.verdict_glob or DEFAULT_VERDICT_GLOBS
    paths = []
    for pattern in globs:
        paths.extend(Path(p) for p in glob.glob(pattern))
    if not paths:
        raise SystemExit("provide at least one --verdict-glob matching saved model-response JSONL files")

    accum: dict[tuple[str, str], dict[str, int]] = {}
    for path in sorted(paths):
        with path.open() as handle:
            for line in handle:
                row = json.loads(line)
                view, label = view_label(path, row["model"])
                if not view:
                    continue
                pid = str(row["problem_id"])
                problem = problems.get(pid)
                if not problem:
                    continue
                key = (view, label)
                bucket = accum.setdefault(
                    key,
                    {
                        "n_full": 0,
                        "judge_full": 0,
                        "exact_full": 0,
                        "n_s0": 0,
                        "judge_s0": 0,
                        "exact_s0": 0,
                    },
                )
                exact = exact_format_correct(
                    row.get("candidate"), problem["correct_answer"], problem["type"]
                )
                judge = bool(row.get("is_correct"))
                bucket["n_full"] += 1
                bucket["judge_full"] += int(judge)
                bucket["exact_full"] += int(exact)
                if problem.get("contamination", {}).get("in_S0"):
                    bucket["n_s0"] += 1
                    bucket["judge_s0"] += int(judge)
                    bucket["exact_s0"] += int(exact)

    rows = []
    for (view, label), b in sorted(accum.items()):
        if b["n_full"] == 0 or b["n_s0"] == 0:
            continue
        exact_full = 100 * b["exact_full"] / b["n_full"]
        exact_s0 = 100 * b["exact_s0"] / b["n_s0"]
        judge_full = 100 * b["judge_full"] / b["n_full"]
        judge_s0 = 100 * b["judge_s0"] / b["n_s0"]
        rows.append(
            {
                "view": view,
                "model": label,
                "n_full": b["n_full"],
                "n_s0": b["n_s0"],
                "judge_full_pct": f"{judge_full:.2f}",
                "judge_s0_pct": f"{judge_s0:.2f}",
                "judge_delta_pp": f"{judge_full - judge_s0:+.2f}",
                "exact_full_pct": f"{exact_full:.2f}",
                "exact_s0_pct": f"{exact_s0:.2f}",
                "exact_delta_pp": f"{exact_full - exact_s0:+.2f}",
            }
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "view",
                "model",
                "n_full",
                "n_s0",
                "judge_full_pct",
                "judge_s0_pct",
                "judge_delta_pp",
                "exact_full_pct",
                "exact_s0_pct",
                "exact_delta_pp",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
