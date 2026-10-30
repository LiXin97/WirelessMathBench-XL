<div align="center">

# WirelessMathBench-XL

### An Auditable Benchmark for Wireless Mathematical Reasoning

*[NeurIPS 2026, Evaluations and Datasets Track](https://openreview.net/forum?id=KbbNUVldqT)* (OpenReview)

Xin Li, Mengbing Liu, Yiyang Zhu, Wenhe Zhang, Li Wei, Jiancheng An, Chau Yuen<br>
Nanyang Technological University

[![arXiv](https://img.shields.io/badge/arXiv-2509.23219-b31b1b?logo=arxiv)](https://arxiv.org/abs/2509.23219)
[![Project page](https://img.shields.io/badge/Project-page-059669)](https://lixin.ai/WirelessMathBench-XL/)
[![Models](https://img.shields.io/badge/%F0%9F%A4%97%20Models-5%20checkpoints-ffcc4d)](https://huggingface.co/collections/XINLI1997/wirelessmathbench-xl-6aba22d1122ef418c33dd34c)
[![Data](https://img.shields.io/badge/%F0%9F%A4%97%20Data-WirelessMATHBench--XL-ffcc4d)](https://huggingface.co/datasets/XINLI1997/WirelessMATHBench-XL)
[![Code license](https://img.shields.io/badge/code-MIT-blue)](LICENSE)
[![Data license](https://img.shields.io/badge/data-per%20file-lightgrey)](#license)

**WirelessMathBench-XL contains 4,027 wireless-math problems in three formats (multiple choice, progressive fill-in at 25/50/75% masking, and full equation completion) built from 836 arXiv papers (July 2005 to August 2025).**

</div>

## News

- **2026-09-28** Data release v1.1, code and the reference checkpoints are public, and arXiv
  [2509.23219](https://arxiv.org/abs/2509.23219) is updated to this paper (v2).

## The idea in 30 seconds

- **Auditable.** Each problem keeps its source-paper identifier, a verifier-facing answer, and per-problem metadata
  from a reverse-probe 13-gram audit of prompt-surface lexical overlap against RedPajama-arXiv. The audit covers one
  fixed channel; it is not a cleanliness certificate (see the paper's Scope and limitations).
- **Released only where licenses allow.** Records are distributed only when the source paper's license clearly permits
  redistribution of derived text. 1,542 records are distributed; 2,485 are withheld and listed by identifier only. See
  `LICENSE`.
- **A public test subset for comparable results.** The union of the three test splits is the **310-item public test
  subset** (`data/public_test_ids.json`). Use the 310-item public subset for externally comparable results.

## Quick start

Check the distributed records and the 310-item public test subset (CPU, seconds):

```bash
git clone https://github.com/LiXin97/WirelessMathBench-XL && cd WirelessMathBench-XL
wc -l data/problems_cc_by.jsonl data/problems_cc_by_sa.jsonl data/problems_cc_by_nc_sa.jsonl
python -c "import json; print(len(json.load(open('data/public_test_ids.json'))))"
```

Expected:

```text
   1334 data/problems_cc_by.jsonl
     43 data/problems_cc_by_sa.jsonl
    165 data/problems_cc_by_nc_sa.jsonl
   1542 total
310
```

[REPRODUCE.md](REPRODUCE.md) has the full integrity checks and the audit commands.

## Models and data

**Data:** [🤗 XINLI1997/WirelessMATHBench-XL](https://huggingface.co/datasets/XINLI1997/WirelessMATHBench-XL). The data
files, evaluation cuts, withheld-record metadata, reproducibility boundary, split and contamination notes, task formats
and provenance are described in [docs/DATA.md](docs/DATA.md). The Datasheet for Datasets is Appendix G of the
paper ([arXiv:2509.23219](https://arxiv.org/abs/2509.23219)); `croissant.json` carries the Croissant metadata with
its Responsible-AI fields.

**Models**, all in the
[model collection](https://huggingface.co/collections/XINLI1997/wirelessmathbench-xl-6aba22d1122ef418c33dd34c).
GRPO-trained WirelessMathLM reference checkpoints (240 steps on the train split):

| Model | Base | Full-800 | Public-310 |
|---|---|---:|---:|
| [🤗 WirelessMathLM-7B](https://huggingface.co/XINLI1997/WirelessMathLM-7B) | Qwen2.5-7B | 47.88 | 46.45 |
| [🤗 WirelessMathLM-3B](https://huggingface.co/XINLI1997/WirelessMathLM-3B) | Qwen2.5-3B | 25.50 | 25.16 |
| [🤗 WirelessMathLM-0.5B](https://huggingface.co/XINLI1997/WirelessMathLM-0.5B) | Qwen2.5-0.5B | 2.12 | 2.26 |
| [🤗 WirelessMathLM-Qwen3-4B](https://huggingface.co/XINLI1997/WirelessMathLM-Qwen3-4B) | Qwen3-4B | – | – |
| [🤗 Math12k-GRPO-Control-7B](https://huggingface.co/XINLI1997/Math12k-GRPO-Control-7B) (general-math control) | Qwen2.5-7B | 22.75 | 20.00 |

Accuracy (%) under the paper's locked 2k-token protocol; the Qwen3-4B run is
reported only as a training-time check (paper Tab. 7). The Math12k control is
size- and step-matched GRPO on general math (paper §3.5). These are release-split
learnability checks, not evidence of general reasoning.

## Repository layout

| Script | Purpose |
|---|---|
| `scripts/contamination_audit.py` | Reverse-probe n-gram audit: index benchmark prompts, stream a corpus, record per-problem hits |
| `scripts/frontier_multin_delta.py` | Full-vs-S0 deltas across n-gram thresholds |
| `scripts/paired_bootstrap.py`, `scripts/per_model_delta_bootstrap.py`, `scripts/paper_disjoint_bootstrap.py` | Paired problem-level bootstrap intervals |
| `scripts/exact_format_lower_bound.py` | No-LLM exact-format lower-bound scorer |
| `scripts/build_paper_disjoint_split.py`, `scripts/materialize_paper_disjoint_view.py`, `scripts/compute_paper_disjoint.py` | Source-paper-disjoint split and views |
| `scripts/fetch_excluded_sources.py` | Summarize withheld records and fetch their arXiv sources for provenance |

See `REPRODUCE.md` for integrity checks and commands. Release history is in `CHANGELOG.md`, how to report
an error is in `CONTRIBUTING.md`, and models and papers that use the benchmark are listed in `PAPERS_USING.md`.

## Citation

```bibtex
@inproceedings{
li2026wirelessmathbenchxl,
title={WirelessMathBench-XL: An Auditable Benchmark for Wireless Mathematical Reasoning},
author={Xin Li and Mengbing Liu and Yiyang Zhu and Wenhe Zhang and Li Wei and Jiancheng An and Chau Yuen},
booktitle={The Fortieth Annual Conference on Neural Information Processing Systems Evaluations and Datasets Track},
year={2026}
}
```

## License

Data files are licensed per file following each record's source-paper license
(CC BY 4.0, CC BY-SA 4.0, or CC BY-NC-SA 4.0); identifier-level metadata is
CC BY 4.0; code is MIT. See `LICENSE`.
