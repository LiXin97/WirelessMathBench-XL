# WirelessMathBench-XL data release (v1.1)

Records are distributed only when the source paper's license clearly permits
redistribution of derived text. 1,542 records are distributed; 2,485 are
withheld and listed by identifier only. See `LICENSE`.

## Files

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
  records. Besides `in_S0`, `contamination_flags_v11.csv` carries three
  exploratory flags from the review discussion; no result in the paper uses
  them. All three are set only on the 174 flagged (non-S0) problems:
  `pre_snapshot_flag` (58) marks a source paper dated before the
  RedPajama-arXiv snapshot (March 2023), the only flags that can reflect the
  problem's own source text; `cloze_reproducible` (33) marks a problem for
  which at least one of the five frontier models, asked at T=0 to continue
  the problem text from its midpoint, reproduced an exact 13-gram of the true
  continuation; `memorization_signature` (18) is the intersection of the two.
  The last flag names a post-hoc stratum; it is not evidence that a model
  memorised the problem.
- `data/s0_membership_by_n.csv`: S0 membership of the 800 test problems under
  n in {8, 10, 12, 13, 15}.
- `data/s0_membership_all_n.csv`: S0 membership of all 4,027 problems under
  each n in {8, 10, 12, 13, 15}, one row per (problem_id, n) with a true/false
  `in_S0` (20,135 rows). At n = 13 it matches `contamination_metadata.jsonl`;
  on the test split it matches `s0_membership_by_n.csv`.
- `data/paper_disjoint_split_seed0.csv`, `data/paper_disjoint_test.csv`:
  source-paper-disjoint split assignments.

Results:

- `data/public_subset_results.csv`: accuracy of all 19 evaluated rows on the
  800-item test split and on the 310-item public subset (95% bootstrap CI).
  This is the externally reproducible view.
- `data/verdicts/locked_2k.jsonl` (18 rows) and `data/verdicts/frontier_16k.jsonl`
  (5 rows): one line per model and problem with `is_correct` and the public audit
  flags, for all 800 test items. There is no problem or response text.
- `data/per_model_results.csv`: full, S0, and S1 accuracy with deltas and 95%
  bootstrap CIs, per-format accuracy, public-subset accuracy, and the 2k-to-16k
  gain for each row.
- `data/paired_bootstrap_matrix.csv`: all 153 pairs of the 18 locked-2k rows.
- `data/truncation_16k.csv`: truncation rates for the five 16k rows; the 2k runs
  did not record `finish_reason`.
- `data/frontier_multin_delta.csv`, `data/answer_surface_n13_delta.csv`,
  `data/exact_format_lower_bound.csv`: audit sensitivity analyses reported in
  the paper (computed by the authors on the full test split). The bootstrap CIs in
  `frontier_multin_delta.csv` come from a separate resampling run from the
  paper's main results table, so interval endpoints can differ in the last digit
  (about 0.01 pp); point estimates are identical.
- `data/external-audits/`: per-item outputs of the same 13-gram audit applied
  to the 587-item WirelessMathBench predecessor and MATH-500 (portability
  examples only).

Metadata: `croissant.json` (Croissant + RAI), `croissant-checklist.md`.

## Reproducibility boundary

Numbers on the full 800-item test split in the paper were computed by the
authors on their complete copy, which includes withheld records. Withheld
records cannot be regenerated: they were produced by stochastic LLM extraction
and synthesis followed by expert screening, so re-running the pipeline on the
same arXiv sources yields different problems.
`scripts/fetch_excluded_sources.py` lists withheld papers and can download
their arXiv sources for provenance inspection. Use the 310-item public subset
for externally comparable results.

## Split and contamination notes

The train/test split is problem-level, not source-paper-disjoint. Use
`paper_id` or `paper_disjoint_split_seed0.csv` (3,222 / 805, zero paper
overlap) for paper-disjoint protocols.

S0/S1 are defined against RedPajama-arXiv using normalized 13-gram overlap over
the released prompt surface. They label one fixed lexical-overlap channel; they
do not cover paraphrase, target-answer, alternate-version, post-training, or
closed-corpus exposure and are not a cleanliness certificate.

## Task format mapping

`type=MCQ` is multiple choice. `fill_blank_25`, `fill_blank_50`, and
`fill_blank_75` are progressive Fill-in tasks. `fill_blank_100` is full
equation completion (FEC).

## Provenance

`paper_id` is the arXiv identifier of the source paper and the provenance key.
`paper_title` is a placeholder string. Source-paper PDFs, LaTeX sources, and
derivation paragraphs are not redistributed.
