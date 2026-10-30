# Contributing

## Reporting an error in a problem

Open an issue with:

- the `problem_id` (and `paper_id`);
- what is wrong (question, masked equation, options, or answer) and why, with
  a pointer to the source paper (section or equation number);
- the corrected answer, if you have one.

Corrections are released as PATCH versions and listed in `CHANGELOG.md`.

## Reporting an overlap or contamination finding

Include the corpus (name, version, snapshot date), the matched strings, and
the document identifiers, so the finding can be checked against the audit
metadata in `data/contamination_metadata.jsonl`.

## Pull requests

Code fixes are welcome. Do not submit problem text, answers, or source text for
records listed in `data/excluded_records_manifest.csv`: those records are
withheld because their source licenses do not permit redistribution.

## Listing your work

To add a model or paper that uses the benchmark, open a pull request against
`PAPERS_USING.md`.
