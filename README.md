# WirelessMathBench-XL

**An Auditable Benchmark for Wireless Mathematical Reasoning** · NeurIPS 2026, Evaluations and Datasets Track

Xin Li, Mengbing Liu, Yiyang Zhu, Wenhe Zhang, Li Wei, Jiancheng An, Chau Yuen · Nanyang Technological University

[Project page](https://lixin.ai/WirelessMathBench-XL/) · [OpenReview](https://openreview.net/forum?id=KbbNUVldqT) · [Dataset (Hugging Face)](https://huggingface.co/datasets/XINLI1997/WirelessMATHBench-XL)

WirelessMathBench-XL contains 4,027 wireless-math problems in three formats
(multiple choice, progressive fill-in at 25/50/75% masking, and full equation
completion) built from 836 arXiv papers (July 2005 to August 2025). Each
problem keeps its source-paper identifier, a verifier-facing answer, and
per-problem metadata from a reverse-probe 13-gram audit of prompt-surface
lexical overlap against RedPajama-arXiv. The audit covers one fixed channel; it
is not a cleanliness certificate (see the paper's Scope and limitations).

## Data release (v1.1)

Records are distributed only when the source paper's license clearly permits
redistribution of derived text. 1,542 records are distributed; 2,485 are
withheld and listed by identifier only. See `LICENSE`.

### Files

Distributed records (one JSON object per line; `split` is `train` or `test`):

| File | Records (train / test) | Record license |
|---|---|---|
| `data/problems_cc_by.jsonl` | 1,334 (1,061 / 273) | CC BY 4.0 (sources: CC BY, CC0) |
| `data/problems_cc_by_sa.jsonl` | 43 (34 / 9) | CC BY-SA 4.0 |
| `data/problems_cc_by_nc_sa.jsonl` | 165 (137 / 28) | CC BY-NC-SA 4.0 |

Each record carries `source_license`, `source_license_class`, and
`record_license`. The union of the three test splits is the **310-item public
test subset** (`data/public_test_ids.json`).

Evaluation cuts of the public test subset:

- `data/S0_test_public.jsonl`: 295 public test records with zero
  RedPajama-arXiv 13-gram prompt-surface hits.
- `data/S1_test_public.jsonl`: 306 public test records with at most two
  distinct RedPajama-arXiv source documents hit.
- `data/paper_disjoint_test_public.jsonl`: 13 public test records whose source
  papers are absent from the training partition (diagnostic only).

Withheld records and identifier-level metadata (all 4,027 problems, no problem
text):

- `data/excluded_records_manifest.csv`: 2,485 withheld records
  (`problem_id`, `paper_id`, `arxiv_id`, `split`, `type`, `license_class`,
  `source_license`): arXiv default license 2,160, CC BY-NC-ND 323, unlabeled 2.
- `data/source_paper_licenses.csv`: license URI and class for all 836 source
  papers (harvested from arXiv OAI-PMH).
- `data/contamination_metadata.jsonl`, `data/contamination_flags_v11.csv`:
  per-problem audit metadata. Matched n-gram strings are omitted for withheld
  records.
- `data/s0_membership_by_n.csv`: S0 membership of the 800 test problems under
  n in {8, 10, 12, 13, 15}.
- `data/paper_disjoint_split_seed0.csv`, `data/paper_disjoint_test.csv`:
  source-paper-disjoint split assignments.

Results:

- `data/public_subset_results.csv`: accuracy of all 19 evaluated rows on the
  800-item test split and on the 310-item public subset (95% bootstrap CI).
  This is the externally reproducible view.
- `data/frontier_multin_delta.csv`, `data/answer_surface_n13_delta.csv`,
  `data/exact_format_lower_bound.csv`: audit sensitivity analyses reported in
  the paper (computed by the authors on the full test split). The bootstrap CIs in
  `frontier_multin_delta.csv` come from a separate resampling run from the
  paper's Table 2, so interval endpoints can differ in the last digit
  (about 0.01 pp); point estimates are identical.
- `data/external-audits/`: per-item outputs of the same 13-gram audit applied
  to the 587-item WirelessMathBench predecessor and MATH-500 (portability
  examples only).

Metadata: `croissant.json` (Croissant + RAI), `croissant-checklist.md`.

### Reproducibility boundary

Numbers on the full 800-item test split in the paper were computed by the
authors on their complete copy, which includes withheld records. Withheld
records cannot be regenerated: they were produced by stochastic LLM extraction
and synthesis followed by expert screening, so re-running the pipeline on the
same arXiv sources yields different problems.
`scripts/fetch_excluded_sources.py` lists withheld papers and can download
their arXiv sources for provenance inspection. Use the 310-item public subset
for externally comparable results.

### Split and contamination notes

The train/test split is problem-level, not source-paper-disjoint. Use
`paper_id` or `paper_disjoint_split_seed0.csv` (3,222 / 805, zero paper
overlap) for paper-disjoint protocols.

S0/S1 are defined against RedPajama-arXiv using normalized 13-gram overlap over
the released prompt surface. They label one fixed lexical-overlap channel; they
do not cover paraphrase, target-answer, alternate-version, post-training, or
closed-corpus exposure and are not a cleanliness certificate.

### Task format mapping

`type=MCQ` is multiple choice. `fill_blank_25`, `fill_blank_50`, and
`fill_blank_75` are progressive Fill-in tasks. `fill_blank_100` is full
equation completion (FEC).

### Provenance

`paper_id` is the arXiv identifier of the source paper and the provenance key.
`paper_title` is a placeholder string. Source-paper PDFs, LaTeX sources, and
derivation paragraphs are not redistributed.

## Code

| Script | Purpose |
|---|---|
| `scripts/contamination_audit.py` | Reverse-probe n-gram audit: index benchmark prompts, stream a corpus, record per-problem hits |
| `scripts/frontier_multin_delta.py` | Full-vs-S0 deltas across n-gram thresholds |
| `scripts/paired_bootstrap.py`, `scripts/per_model_delta_bootstrap.py`, `scripts/paper_disjoint_bootstrap.py` | Paired problem-level bootstrap intervals |
| `scripts/exact_format_lower_bound.py` | No-LLM exact-format lower-bound scorer |
| `scripts/build_paper_disjoint_split.py`, `scripts/materialize_paper_disjoint_view.py`, `scripts/compute_paper_disjoint.py` | Source-paper-disjoint split and views |
| `scripts/fetch_excluded_sources.py` | Summarize withheld records and fetch their arXiv sources for provenance |

See `REPRODUCE.md` for integrity checks and commands. Training recipes and
WirelessMathLM checkpoints will be linked here.

## Citation

```bibtex
@inproceedings{
li2026wirelessmathbenchxl,
title={WirelessMathBench-XL: An Auditable Benchmark for Wireless Mathematical Reasoning},
author={Xin Li and Mengbing Liu and Yiyang Zhu and Wenhe Zhang and Li Wei and Jiancheng An and Chau Yuen},
booktitle={The Fortieth Annual Conference on Neural Information Processing Systems Evaluations and Datasets Track},
year={2026},
url={https://openreview.net/forum?id=KbbNUVldqT}
}
```

## License

Data files are licensed per file following each record's source-paper license
(CC BY 4.0, CC BY-SA 4.0, or CC BY-NC-SA 4.0); identifier-level metadata is
CC BY 4.0; code is MIT. See `LICENSE`.
