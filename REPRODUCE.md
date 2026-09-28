# Reproducing the Release Checks

This file gives integrity and reproduction checks for the WirelessMathBench-XL
v1.1 release.

## Environment

Python 3.10+ is sufficient for metadata checks. The contamination-audit scripts
also require:

```bash
pip install xxhash zstandard datasets
```

## Data Integrity Checks

Run from the repository root:

```bash
wc -l data/problems_cc_by.jsonl \
      data/problems_cc_by_sa.jsonl \
      data/problems_cc_by_nc_sa.jsonl \
      data/S0_test_public.jsonl \
      data/S1_test_public.jsonl \
      data/paper_disjoint_test_public.jsonl \
      data/excluded_records_manifest.csv \
      data/contamination_metadata.jsonl \
      data/s0_membership_by_n.csv \
      data/public_subset_results.csv \
      data/frontier_multin_delta.csv \
      data/answer_surface_n13_delta.csv \
      data/paper_disjoint_test.csv \
      data/paper_disjoint_split_seed0.csv \
      data/exact_format_lower_bound.csv \
      data/external-audits/wmb_v1_587_redpajama_arxiv.jsonl \
      data/external-audits/math500_redpajama_arxiv.jsonl
python -m json.tool croissant.json >/dev/null
```

Expected line counts:

```text
 1334 data/problems_cc_by.jsonl
   43 data/problems_cc_by_sa.jsonl
  165 data/problems_cc_by_nc_sa.jsonl
  295 data/S0_test_public.jsonl
  306 data/S1_test_public.jsonl
   13 data/paper_disjoint_test_public.jsonl
 2486 data/excluded_records_manifest.csv
 4027 data/contamination_metadata.jsonl
  801 data/s0_membership_by_n.csv
   20 data/public_subset_results.csv
   26 data/frontier_multin_delta.csv
    6 data/answer_surface_n13_delta.csv
   35 data/paper_disjoint_test.csv
 4028 data/paper_disjoint_split_seed0.csv
    9 data/exact_format_lower_bound.csv
  587 data/external-audits/wmb_v1_587_redpajama_arxiv.jsonl
  500 data/external-audits/math500_redpajama_arxiv.jsonl
```

The Croissant file should parse as JSON. Before final submission, validate it
with the official NeurIPS/Croissant validator used by the submission system.

## Audit Dry Run

The release-defining RedPajama-arXiv audit requires a local or hosted mirror of
the RedPajama arXiv slice. To verify the pipeline shape without downloading the
full corpus, run the script help and a small local-slice smoke test if a local
slice is available:

```bash
python scripts/contamination_audit.py --help
python scripts/contamination_audit.py \
  --problems data/problems_cc_by.jsonl \
  --slice redpajama-arxiv:/path/to/redpajama-arxiv-sample/ \
  --out-dir /tmp/wmbxl-audit-smoke \
  --workers 4
```

The release-defining full run reported in the paper scanned RedPajama-arXiv and
materialized per-problem metadata in
`data/contamination_metadata.jsonl`.
The threshold-sensitivity CSVs can be regenerated from archived verdicts and
test-split audit labels with `scripts/frontier_multin_delta.py`.
The source-paper-disjoint diagnostic view can be regenerated with
`scripts/materialize_paper_disjoint_view.py`. The full seed-0 clustered split
assignment can be regenerated with `scripts/build_paper_disjoint_split.py`; the
no-LLM exact-format
lower-bound smoke check can be regenerated with
`scripts/exact_format_lower_bound.py` from archived model responses.

## Public Test Subset and the Full Test Split

The 800-item test split used in the paper includes 490 withheld records (see
`LICENSE`). External users can evaluate on the 310-item public test subset
(`data/public_test_ids.json`; the `test` records of the three `problems_*.jsonl`
files). `data/public_subset_results.csv` gives every evaluated row's accuracy on
both the full split (authors' copy) and the public subset, recomputed from the
archived per-item verdicts. `S0_test_public` / `S1_test_public` are the public
records of the strict and lenient filtered views; they label one fixed 13-gram
prompt-surface lexical-overlap channel against RedPajama-ArXiv and are not a
general cleanliness label. Use `paper_id` for source-paper-clustered analyses;
the train/test split is problem-level, not source-paper-disjoint.

## External Portability Profiles

The two files under `data/external-audits/` are archived per-item outputs from
running the same audit implementation on the 587-item WirelessMathBench
predecessor and MATH-500. They show that the implementation produces
inspectable matches on external prompt sets. They do not validate the fixed
threshold for every domain or test paraphrase, target-answer,
proprietary-corpus, or post-training exposure.

## v1.1 Source-License-Aware Distribution

`data/source_paper_licenses.csv` records the arXiv OAI-PMH license of each of
the 836 source papers. Records are distributed only when that license clearly
permits redistribution of derived text: `problems_cc_by.jsonl` (1,334; CC BY /
CC0 sources), `problems_cc_by_sa.jsonl` (43), and `problems_cc_by_nc_sa.jsonl`
(165), each under the matching license. The 2,485 records from arXiv-default
(2,160), CC BY-NC-ND (323), or unlabeled (2) sources are withheld and listed in
`data/excluded_records_manifest.csv` without problem text.

```bash
python scripts/fetch_excluded_sources.py    # summary of withheld records
python scripts/fetch_excluded_sources.py --fetch sources/   # arXiv sources
```

Withheld records cannot be regenerated: construction used stochastic LLM
extraction and synthesis, so re-running the pipeline yields different problems.

Discussion-period E2, cloze, paraphrase, Min-K, and context-ablation scripts
that may remain in the development repository are exploratory provenance only.
They are not used to support the revised paper or rebuttal conclusions and
must not be interpreted as validation of the fixed lexical-overlap audit.
