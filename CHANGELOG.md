# Changelog

Versions follow MAJOR.MINOR.PATCH (see the Datasheet, Appendix G of the paper).

## v1.1 — 2026-09-28

- Source-license-aware release: 1,542 records whose source papers permit
  redistribution are published in three license configs (`cc_by`, `cc_by_sa`,
  `cc_by_nc_sa`); the 2,485 remaining records are listed by identifier only in
  `data/excluded_records_manifest.csv`.
- The 310-item public test subset (`data/public_test_ids.json`) and its
  re-scored results (`data/public_subset_results.csv`).
- Source-paper-disjoint views: the 34-item `paper_disjoint_test` view and a
  seed-0 grouped split with 3,222 / 805 records.
- Audit outputs: per-problem contamination metadata for all 4,027 problems,
  S0 membership by n-gram length for the 800-item test split, the answer-surface check at n = 13, the
  exact-format lower bound, and external reruns (WirelessMathBench, MATH-500).
- Croissant 1.0 metadata with Responsible-AI fields.

## v1.0 — 2025-10-09 (withdrawn)

- First release: 4,027 problems from 836 arXiv papers in three formats
  (MCQ, progressive fill-in at 25/50/75% masking, full equation completion),
  with a problem-level 3,227 / 800 train/test split.
- Withdrawn with v1.1: 2,485 of its records come from papers whose licenses do
  not permit redistribution of derived text, so v1.0 is no longer distributed.
