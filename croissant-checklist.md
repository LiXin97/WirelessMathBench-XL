# Croissant / RAI Release Checklist

**File:** `croissant.json`  
**Spec target:** Croissant 1.0 with RAI metadata  
**Release state:** public camera-ready release (v1.1)

## Dataset-Level Metadata

| Field | Status |
|---|---|
| name / description / keywords | Complete and aligned with the paper: 4,027 problems from 836 retained papers selected from a 970-paper source pool, with a problem-level release split and explicit `paper_id` clusters. |
| license | Per-file data licenses matching source-paper licenses: CC BY 4.0 (`problems_cc_by.jsonl`), CC BY-SA 4.0 (`problems_cc_by_sa.jsonl`), CC BY-NC-SA 4.0 (`problems_cc_by_nc_sa.jsonl`); 2,485 records from arXiv-default / CC BY-NC-ND / unlabeled sources withheld; identifier-level metadata CC BY 4.0; code MIT. |
| url / sameAs | https://lixin.ai/WirelessMathBench-XL; Hugging Face `XINLI1997/WirelessMATHBench-XL`; GitHub `LiXin97/WirelessMathBench-XL`. |
| version / datePublished | `1.1.0` (license remediation over the `1.0.0` corpus dated `2026-05-06`). |
| creator / publisher / citeAs | Seven authors, Nanyang Technological University; NeurIPS 2026 E&D citation. |
| conformsTo / isLiveDataset / language | Present. |

## Distribution Files

| File | Lines | sha256 / size |
|---|---|---|
| `data/problems_cc_by.jsonl` | 1334 | `3fcbd5dea8b697371e7ff77dc5fcb127bb2783797eb71b52c4df03d23e851460`, 4,899,816 bytes |
| `data/problems_cc_by_sa.jsonl` | 43 | `10086b6ee60f2f5015798a657dd8022af99e7ce0fce2e4b907d56943c47f03cf`, 186,894 bytes |
| `data/problems_cc_by_nc_sa.jsonl` | 165 | `a83629ec873d1410d135c76f5192b5a91840bcdb37863ed9813b9525f944509f`, 600,651 bytes |
| `data/S0_test_public.jsonl` | 295 | `6a3cbb904ad782f6f874b64ce86f2f0e7e3b8e1da81d7ddd4f0efb76b8643efa`, 1,031,771 bytes |
| `data/S1_test_public.jsonl` | 306 | `e8da317c70e97969c4feacda1396ea6bec1de9bba172c3e525afcd19058bde18`, 1,082,722 bytes |
| `data/paper_disjoint_test_public.jsonl` | 13 | `9e968f42535bcf1a0852838cbc6e1fde629daf42ee86d0ee14a004f89406be7a`, 48,039 bytes |
| `data/excluded_records_manifest.csv` | 2486 | `6220af13c6487da2d1894c30791e403696102c1cc636ac2cfb323dab4822913d`, 294,256 bytes |
| `data/contamination_metadata.jsonl` | 4027 | `eb2744e79ffeba163e2fc059e08c9aadfe824fe06c89b69ceedd85f8cffd429e`, 482,330 bytes |
| `data/s0_membership_by_n.csv` | 801 | `eb147d6bc1a4ad0a35520e1b0fcad045f946cb16b9164ee7ff63d097a096009c`, 25,976 bytes |
| `data/public_subset_results.csv` | 20 | `83083c8e0a036c6b4de40a9321899c96924c15829f64b395bc9ded217334e4f8`, 989 bytes |
| `data/frontier_multin_delta.csv` | 26 | `0f70d295498d75fd9ff4fbae13cc78b62fb75588b5685f0feda2b5ff5ad6c6d9`, 3,925 bytes |
| `data/answer_surface_n13_delta.csv` | 6 | `22d8f2c7ed4b2e0d4730e0ad265d896a2a74a1a56c40ea0398f2810f84e74fdf`, 815 bytes |
| `data/paper_disjoint_test.csv` | 35 | `b7b650c975af259c6b6a35cf35522bc497c82e352ef52854b61392240a1aa72e`, 1,028 bytes |
| `data/paper_disjoint_split_seed0.csv` | 4028 | `7b88f702a79d3511a5ec6f11400dd1d44c92ae06ef82b2cc44ea22886b3ad05a`, 175,157 bytes |
| `data/exact_format_lower_bound.csv` | 9 | `c136a0bc463a36a7756d9696680c0c0a4ec673859ffe44b905c2215d2c0c13c9`, 694 bytes |
| `data/external-audits/wmb_v1_587_redpajama_arxiv.jsonl` | 587 | `c6bee931b7e2ec978e049580740b6d27b82e95ddd59f70b64f6262c61b3cce5e`, 220,972 bytes |
| `data/external-audits/math500_redpajama_arxiv.jsonl` | 500 | `b4ce80de6aff3d4f60726964518265c3aaf3efea46cb8f49bf5cb2c001be7d35`, 192,212 bytes |
| `LICENSE` | n/a | `f9361c054851fba2e70bdf59c69cf07bd22e5a0e7468644e6319f26b22894dab`, 3,214 bytes |

## Record Sets

`problems` documents the distributed record schema (plus `source_license`,
`source_license_class`, `record_license`):
`problem_id`, `paper_id`, `paper_title`, `type`, `split`, `background`,
`question_text`, `equation`, `options`, `correct_answer`, `prompt`, and
`text`.

MCQ `options` are stored as a JSON object keyed by option letter, and MCQ
`correct_answer` values are option letters rather than boxed expressions.

Source metadata is intentionally minimal: `paper_id` is the
join key to the arXiv source paper, while real paper titles, per-instance
subfield labels, and extraction-record family ids are not release fields in
v1.0. `README.md` states this explicitly because `paper_title` is a placeholder
string.

`contamination_metadata` documents the joinable audit schema:
`problem_id`, `hits_total`, `docs_total`, `matched_ngrams_capped`, `in_S0`,
and `in_S1`.

The v1.0 `split` field is a problem-level release split, not a
source-paper-disjoint partition. The materialized `paper_disjoint_test` files
contain the 34-item diagnostic slice whose source papers are absent from the
training partition. Users needing paper-disjoint training generalisation should
group by `paper_id` and rebuild train/test splits; the seed-0 clustered
assignment in `paper_disjoint_split_seed0.csv` is provided as a reproducible
starting point.

## RAI Metadata

The Croissant file includes RAI fields for data collection, annotation,
LLM/synthetic-data involvement, preprocessing, release maintenance, personal
or sensitive information, recommended use cases, limitations, biases, risk
types, and social impact, plus provenance summaries for source papers and
generation/audit procedures.

## Local Validation

`python -m json.tool croissant.json` succeeds, and the file
contains no author-identifying hub URL or unresolved review marker. Run the
official Croissant validator on the packaged supplemental archive before final
submission.
