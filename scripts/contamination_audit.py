"""
Contamination audit: reverse-probe n-gram overlap of WirelessMathBench-XL
problems against auditable pretraining-corpus slices. The v1.0 release-defining
run is RedPajama-ArXiv; Dolma-ArXiv and ProofPile-2-ArXiv were not used as
independent release-defining slices after being checked as RedPajama
repackagings.

Output schema (see decisions entry):
    contamination-audit.csv:    problem_id, n_grams_total, hits_total,
                                docs_total, in_S0, in_S1
    contamination-audit.jsonl:  one row per problem, matched 13-gram strings
                                per slice (capped at 20 per slice for spot-check)
    contamination-audit.md:     aggregate summary, |S0|, |S1|, histograms

Strict subset S0:   docs_total == 0 for RedPajama-ArXiv
Lenient subset S1:  docs_total <= 2 for RedPajama-ArXiv

Hard-abort gate (D5):  if |S1| < 150, ABORT cleaned-subset re-eval; pivot
paper to "corpus too contaminated to evaluate" framing.

Usage:
    python contamination_audit.py \\
        --problems   data/problems_cc_by.jsonl \\
        --slice      redpajama-arxiv:/data/redpajama-arxiv/ \\
        --out-dir    derived/redpajama-audit/

The --slice flag accepts one of:
    name:hf-dataset-id           e.g. redpajama-arxiv:togethercomputer/RedPajama-Data-1T@arxiv
    name:/local/path/            jsonl.zst or jsonl.gz files in dir
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import logging
import math
import multiprocessing as mp
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# --- third-party (lazy-import where possible to keep top-level light) ---
# pip install xxhash bitarray zstandard datasets

try:
    import xxhash
except ImportError:
    sys.exit("missing dep: pip install xxhash")

try:
    from bitarray import bitarray
except ImportError:
    sys.exit("missing dep: pip install bitarray")

# zstandard / datasets imported inside slice loaders so the script can run
# without them when only local jsonl.gz slices are provided.

# --------------------------------------------------------------------- config
N_GRAM = 13
BLOOM_FP_RATE = 1e-4
S0_MAX_HITS = 0
S1_MAX_HITS = 2
HARD_ABORT_S1_FLOOR = 150
SPOTCHECK_CAP_PER_SLICE = 20  # how many matched 13-grams to record in jsonl

LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+|[\{\}\$]")
WHITESPACE_RE = re.compile(r"\s+")

# Set by main(); read by normalize_text(). Module-level so workers inherit
# via fork on Linux without needing to thread the flag through every call.
NORMALIZE_ENABLED = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("contam-audit")


# --------------------------------------------------------------- normalization
def normalize_text(s: str) -> str:
    """
    Audit summary fields:
      lowercase + collapse whitespace + strip LaTeX command tokens.
    Apply identically to problem text and slice text — any asymmetry
    invalidates the overlap measurement.
    """
    if not NORMALIZE_ENABLED:
        # Raw mode: only collapse whitespace so .split() still tokenises sanely.
        # Preserve case, LaTeX command tokens, braces, dollars.
        return WHITESPACE_RE.sub(" ", s).strip()
    s = s.lower()
    s = LATEX_CMD_RE.sub(" ", s)
    s = WHITESPACE_RE.sub(" ", s).strip()
    return s


def ngrams(tokens: list[str], n: int | None = None) -> Iterator[tuple[str, ...]]:
    if n is None:
        n = N_GRAM
    if len(tokens) < n:
        return
    for i in range(len(tokens) - n + 1):
        yield tuple(tokens[i : i + n])


def hash_ngram(ng: tuple[str, ...]) -> int:
    return xxhash.xxh64(" ".join(ng).encode("utf-8")).intdigest()


# ===========================================================================
# REVERSE-PROBE algorithm (default since 2026-04-22 23:30 SGT)
# ---------------------------------------------------------------------------
# The original "build a set of all corpus n-grams, then probe each problem
# n-gram against it" approach is wrong-way-around: corpus has ~10B unique
# 13-grams, problems have ~500K. Storing the larger side blows memory.
#
# Reverse: precompute the SMALL set (problem n-grams → which problem(s) each
# came from), then stream-scan corpus files; on every n-gram hit increment
# that problem's hit count. Memory is fixed at ~50 MB regardless of corpus
# size. Wall-clock = pure ingest IO + hash time, ~10-20 min total at 16
# workers on this box.
# ===========================================================================

def build_problem_probe(problems: list[dict]) -> tuple[dict[int, list[str]], dict[str, int]]:
    """
    Returns:
      probe_index: hash → list of problem_ids whose normalized text contains
                   this 13-gram (handles collisions where multiple problems
                   share an n-gram).
      ngram_count_per_problem: problem_id → total number of 13-grams in that
                               problem's normalized text (denominator for
                               %-overlap stats; unique not raw, to match the
                               way slice n-grams are de-duped per-doc).
    """
    probe: dict[int, list[str]] = defaultdict(list)
    ngram_count_per_problem: dict[str, int] = {}
    for p in problems:
        norm = normalize_text(p["text"])
        toks = norm.split()
        all_ngrams = list(ngrams(toks))
        ngram_count_per_problem[p["problem_id"]] = len(all_ngrams)
        # de-dup per-problem so a problem can score at most once per unique ngram per slice
        seen_in_problem: set = set()
        for ng in all_ngrams:
            h = hash_ngram(ng)
            if h in seen_in_problem:
                continue
            seen_in_problem.add(h)
            probe[h].append(p["problem_id"])
    log.info(
        "probe built: %d unique problem-ngrams across %d problems (mean %.1f/problem)",
        len(probe), len(problems),
        sum(len(v) for v in probe.values()) / max(1, len(problems)),
    )
    return dict(probe), ngram_count_per_problem


def _worker_probe_slice_file(args: tuple) -> tuple[str, int, int, dict[str, int], dict[str, list[str]], dict[str, int], dict[str, set]]:
    """
    Per-file worker: stream a slice file. For each doc, build a per-doc map
    pid -> set of probe-ngram-hashes that hit in this doc. After the doc:
      - hits[pid] += <occurrence count of probe ngrams in this doc> (legacy)
      - docs_hit[pid] += 1 if pid had >=1 hit in this doc (carlini headline)
      - unique_ngrams[pid] |= set of probe-ngram-hashes hit by this pid (across all docs in this file)
    Returns (filename, n_docs, n_ngrams_seen, hits_by_problem, examples_by_problem,
             docs_hit_by_problem, unique_ngrams_by_problem).
    """
    file_path, slice_name, probe_index = args
    hits: dict[str, int] = defaultdict(int)              # occurrences (legacy)
    docs_hit: dict[str, int] = defaultdict(int)          # distinct source-docs containing >=1 hit
    unique_ngrams: dict[str, set] = defaultdict(set)     # distinct probe-ngram-hashes hit
    examples: dict[str, list[str]] = defaultdict(list)
    n_docs = 0
    n_ngrams = 0
    f = Path(file_path)
    for txt in _iter_one_slice_file(f):
        per_doc_pids: dict[str, set] = defaultdict(set)  # pid -> set[h] hit in THIS doc
        for ng in ngrams(normalize_text(txt).split()):
            h = hash_ngram(ng)
            if h in probe_index:
                for pid in probe_index[h]:
                    hits[pid] += 1
                    per_doc_pids[pid].add(h)
                    if len(examples[pid]) < SPOTCHECK_CAP_PER_SLICE:
                        examples[pid].append(" ".join(ng))
            n_ngrams += 1
        for pid, hset in per_doc_pids.items():
            docs_hit[pid] += 1
            unique_ngrams[pid] |= hset
        n_docs += 1
    return (f.name, n_docs, n_ngrams, dict(hits), {k: v for k, v in examples.items()},
            dict(docs_hit), {k: v for k, v in unique_ngrams.items()})


def run_reverse_probe_audit(
    slice_specs: list[str],
    probe_index: dict[int, list[str]],
    ngram_count_per_problem: dict[str, int],
    n_workers: int,
) -> tuple[list[dict], list[str]]:
    """
    Stream every slice file in parallel; reduce per-file hit dicts into final
    per-problem-per-slice hit counts. Returns (audit_rows, slice_names).
    """
    slice_names: list[str] = []
    per_slice_hits: dict[str, dict[str, int]] = {}
    per_slice_docs: dict[str, dict[str, int]] = {}          # pid -> distinct source-docs with >=1 hit
    per_slice_unique_ngrams: dict[str, dict[str, set]] = {}  # pid -> set[hash] of distinct probe-ngrams hit
    per_slice_examples: dict[str, dict[str, list[str]]] = {}

    for spec in slice_specs:
        name, source = spec.split(":", 1)
        slice_names.append(name)
        per_slice_hits[name] = defaultdict(int)
        per_slice_docs[name] = defaultdict(int)
        per_slice_unique_ngrams[name] = defaultdict(set)
        per_slice_examples[name] = defaultdict(list)
        if not (source.startswith("/") or source.startswith("./")):
            log.warning("[%s] HF streaming not supported in reverse-probe; skip", name)
            continue
        files = _list_slice_files(Path(source))
        log.info("[%s] reverse-probe over %d files, %d workers", name, len(files), n_workers)
        if not files:
            continue
        args_list = [(str(f), name, probe_index) for f in files]
        t0 = time.time()
        n_done = 0
        n_docs_total = 0
        n_ngrams_total = 0
        with mp.Pool(n_workers) as pool:
            for fname, n_docs, n_ng, hits_dict, ex_dict, docs_dict, uniq_dict in pool.imap_unordered(_worker_probe_slice_file, args_list):
                for pid, h in hits_dict.items():
                    per_slice_hits[name][pid] += h
                for pid, d in docs_dict.items():
                    per_slice_docs[name][pid] += d
                for pid, hset in uniq_dict.items():
                    per_slice_unique_ngrams[name][pid] |= hset
                for pid, exs in ex_dict.items():
                    if len(per_slice_examples[name][pid]) < SPOTCHECK_CAP_PER_SLICE:
                        room = SPOTCHECK_CAP_PER_SLICE - len(per_slice_examples[name][pid])
                        per_slice_examples[name][pid].extend(exs[:room])
                n_done += 1
                n_docs_total += n_docs
                n_ngrams_total += n_ng
                elapsed = time.time() - t0
                if n_done % 10 == 0 or n_done == len(files):
                    log.info(
                        "  [%s] %d/%d files, %d docs, %d ngrams scanned — elapsed %.1fs, %.1fs/file avg",
                        name, n_done, len(files), n_docs_total, n_ngrams_total,
                        elapsed, elapsed / n_done,
                    )
        log.info(
            "[%s] DONE — %d docs, %d ngrams, %.1fs total, %d problems with ≥1 occurrence-hit, %d problems with ≥1 doc-hit",
            name, n_docs_total, n_ngrams_total, time.time() - t0,
            sum(1 for v in per_slice_hits[name].values() if v > 0),
            sum(1 for v in per_slice_docs[name].values() if v > 0),
        )

    rows: list[dict] = []
    for pid, n_grams_total in ngram_count_per_problem.items():
        ps_hits = {n_: per_slice_hits[n_].get(pid, 0) for n_ in slice_names}
        ps_docs = {n_: per_slice_docs[n_].get(pid, 0) for n_ in slice_names}
        ps_uniq = {n_: len(per_slice_unique_ngrams[n_].get(pid, set())) for n_ in slice_names}
        ps_ex = {n_: per_slice_examples[n_].get(pid, []) for n_ in slice_names}
        hits_total = sum(ps_hits.values())
        docs_total = sum(ps_docs.values())
        unique_ngrams_total = sum(ps_uniq.values())
        rows.append({
            "problem_id": pid,
            "n_grams_total": n_grams_total,
            "per_slice_hits": ps_hits,                 # legacy: occurrence count
            "per_slice_docs": ps_docs,                 # NEW: distinct source-docs containing >=1 hit
            "per_slice_unique_ngrams": ps_uniq,        # NEW: distinct probe-ngrams hit
            "per_slice_examples": ps_ex,
            "hits_total": hits_total,                  # legacy
            "docs_total": docs_total,                  # NEW carlini-headline
            "unique_ngrams_total": unique_ngrams_total,  # NEW
            "in_S0": docs_total == S0_MAX_HITS,
            "in_S1": docs_total <= S1_MAX_HITS,
            "in_S0_docs": docs_total == S0_MAX_HITS,
            "in_S1_docs": docs_total <= S1_MAX_HITS,
        })
    return rows, slice_names


# ----------------------------------------------------------------- bloom filter
@dataclass
class BloomFilter:
    n_items: int
    fp_rate: float = BLOOM_FP_RATE
    bits: bitarray = field(init=False)
    n_hashes: int = field(init=False)
    size: int = field(init=False)

    def __post_init__(self):
        self.size = max(1, int(-self.n_items * math.log(self.fp_rate) / (math.log(2) ** 2)))
        self.n_hashes = max(1, int((self.size / self.n_items) * math.log(2)))
        self.bits = bitarray(self.size)
        self.bits.setall(False)
        log.info(
            "bloom: n=%d, fp=%g → bits=%.2e, k=%d, mem=%.2f GB",
            self.n_items, self.fp_rate, self.size, self.n_hashes, self.size / 8 / 1e9,
        )

    def _positions(self, h: int) -> Iterator[int]:
        # double-hashing: two 32-bit halves of xxh64 → k positions
        h1 = h & 0xFFFFFFFF
        h2 = (h >> 32) & 0xFFFFFFFF
        for i in range(self.n_hashes):
            yield (h1 + i * h2) % self.size

    def add(self, h: int) -> None:
        for p in self._positions(h):
            self.bits[p] = True

    def __contains__(self, h: int) -> bool:
        return all(self.bits[p] for p in self._positions(h))


# ----------------------------------------------------------------- exact set
@dataclass
class ExactHashSet:
    """
    Exact set of 64-bit n-gram hashes, frozen into a sorted numpy uint64 array
    after ingest for compact storage + binary-search lookup.

    Memory progression:
      - During ingest: Python set (~150 B/entry CPython overhead)
      - After freeze(): np.uint64 array (8 B/entry) + sorted for searchsorted

    For the WirelessMathBench-XL corpus (RP-arXiv ~5B unique + PP2-arXiv ~5B
    unique = ~10B unique 64-bit hashes total) the frozen arrays sum to ~80 GB,
    well within the 755 GB box. Selected over BloomFilter because the
    2026-04-22 00:22 SGT bloom run saturated at 13.7B raw ngrams against a
    1B-capacity bloom → ~100% FP rate → S₁=0 result was an artifact.

    The {add, __contains__} API mirrors BloomFilter so audit_problem doesn't
    need to branch.
    """
    n_items: int = 0  # ignored; kept for constructor parity
    fp_rate: float = 0.0
    hashes: set = field(default_factory=set)
    sorted_arr: object = None  # np.ndarray[uint64] after freeze()

    def __post_init__(self):
        log.info("exact-set: starting empty")

    @property
    def size(self) -> int:
        if self.sorted_arr is not None:
            return int(self.sorted_arr.size)
        return len(self.hashes)

    def add(self, h: int) -> None:
        self.hashes.add(h)

    def freeze(self) -> None:
        """Convert the Python set to a sorted np.uint64 array; release the set."""
        import numpy as np
        if not self.hashes:
            self.sorted_arr = np.empty(0, dtype=np.uint64)
            return
        log.info("freezing exact-set: %d hashes → np.uint64 array", len(self.hashes))
        self.sorted_arr = np.fromiter(self.hashes, dtype=np.uint64, count=len(self.hashes))
        self.sorted_arr.sort()
        self.hashes = set()  # release Python-set memory
        log.info("frozen: %.2f GB", self.sorted_arr.nbytes / 1e9)

    def __contains__(self, h: int) -> bool:
        if self.sorted_arr is not None:
            import numpy as np
            i = np.searchsorted(self.sorted_arr, np.uint64(h))
            return i < self.sorted_arr.size and self.sorted_arr[i] == np.uint64(h)
        return h in self.hashes


# ---------------------------------------------------------------- slice loaders
def iter_slice_local(path: Path) -> Iterator[str]:
    """Yield documents as raw strings from a directory of jsonl(.gz/.zst) files."""
    files = sorted(_list_slice_files(path))
    log.info("slice local: %d files under %s", len(files), path)
    for f in files:
        yield from _iter_one_slice_file(f)


def _list_slice_files(path: Path) -> list[Path]:
    """Find all jsonl(.gz|.zst) files under path (recursive)."""
    out: list[Path] = []
    for ext in ("*.jsonl", "*.jsonl.gz", "*.jsonl.zst"):
        out.extend(path.rglob(ext))
    return sorted(out)


def _iter_one_slice_file(f: Path) -> Iterator[str]:
    """Yield text strings from a single jsonl(.gz|.zst) file."""
    log.info("  reading %s (%.1f MB)", f.name, f.stat().st_size / 1e6)
    if f.suffix == ".gz":
        stream = io.TextIOWrapper(gzip.open(f, "rb"), encoding="utf-8")
    elif f.suffix == ".zst":
        import zstandard as zstd  # lazy
        stream = io.TextIOWrapper(zstd.ZstdDecompressor().stream_reader(open(f, "rb")), encoding="utf-8")
    else:
        stream = open(f, "r", encoding="utf-8")
    with stream as s:
        for line in s:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            txt = obj.get("text") or obj.get("content") or obj.get("raw_content") or ""
            if txt:
                yield txt


def iter_slice_hf(spec: str) -> Iterator[str]:
    """Yield documents from a HuggingFace dataset id (streaming)."""
    from datasets import load_dataset  # lazy
    if "@" in spec:
        repo, config = spec.split("@", 1)
    else:
        repo, config = spec, None
    log.info("slice hf: streaming %s (config=%s)", repo, config)
    ds = load_dataset(repo, config, split="train", streaming=True)
    for ex in ds:
        txt = ex.get("text") or ex.get("content") or ex.get("raw_content") or ""
        if txt:
            yield txt


def load_slice_into_bloom(slice_spec: str, bf: BloomFilter, est_ngrams: int) -> int:
    """
    slice_spec is "name:source" where source is either a local dir or a HF id.
    Returns total n-grams ingested (for log).
    """
    name, source = slice_spec.split(":", 1)
    if source.startswith("/") or source.startswith("./"):
        doc_iter = iter_slice_local(Path(source))
    else:
        doc_iter = iter_slice_hf(source)

    n_ngrams_added = 0
    n_docs = 0
    for txt in doc_iter:
        norm = normalize_text(txt)
        toks = norm.split()
        for ng in ngrams(toks):
            bf.add(hash_ngram(ng))
            n_ngrams_added += 1
        n_docs += 1
        if n_docs % 10_000 == 0:
            log.info("  [%s] %d docs, %d n-grams ingested", name, n_docs, n_ngrams_added)
    log.info("[%s] DONE — %d docs, %d n-grams", name, n_docs, n_ngrams_added)
    return n_ngrams_added


# --------------------------------------------- parallel worker (per-file shard)
def _worker_build_subset(args: tuple):
    """
    Per-file worker: build a sorted np.uint64 array of unique 64-bit n-gram
    hashes for one slice file.

    Returns (filename, n_docs, n_ngrams_seen, np.ndarray[uint64]).
    Pickling 8 B/hash via numpy is far cheaper than pickling a Python set
    (~150 B/entry); for a 250 MB compressed file with ~125 M unique hashes
    that's ~1 GB pickled vs ~19 GB.
    """
    import numpy as np
    file_path, slice_name = args
    s: set = set()
    n_docs = 0
    n_ngrams = 0
    f = Path(file_path)
    for txt in _iter_one_slice_file(f):
        norm = normalize_text(txt)
        toks = norm.split()
        for ng in ngrams(toks):
            s.add(hash_ngram(ng))
            n_ngrams += 1
        n_docs += 1
    arr = np.fromiter(s, dtype=np.uint64, count=len(s))
    arr.sort()
    return (f.name, n_docs, n_ngrams, arr)


def load_slice_into_set_parallel(
    slice_spec: str, master: ExactHashSet, n_workers: int
) -> int:
    """
    Parallel build: shard slice files across workers, each builds a sorted
    np.uint64 array of unique hashes; merge into the master ExactHashSet
    via union of arrays (np.union1d, accumulator pattern).

    HF (streaming) sources fall back to single-threaded.
    """
    import numpy as np
    name, source = slice_spec.split(":", 1)
    if not (source.startswith("/") or source.startswith("./")):
        log.info("[%s] HF source — falling back to single-threaded ingest", name)
        return load_slice_into_set_single(slice_spec, master)

    files = _list_slice_files(Path(source))
    log.info("[%s] %d files, %d workers (exact-set, np.uint64)", name, len(files), n_workers)
    if not files:
        return 0

    args_list = [(str(f), name) for f in files]

    t0 = time.time()
    n_ngrams_total = 0
    n_docs_total = 0
    n_done = 0
    master_arr = np.empty(0, dtype=np.uint64)
    pending: list = []  # buffer of incoming arrays; flush by union when large

    def flush_pending():
        """Merge pending sub-arrays into master_arr by union (sorted output)."""
        nonlocal master_arr, pending
        if not pending:
            return
        # concatenate then unique-sort: O(n log n) once is cheaper than n union1d calls
        combined = np.concatenate([master_arr] + pending)
        master_arr = np.unique(combined)
        pending = []

    with mp.Pool(n_workers) as pool:
        for fname, n_docs, n_ng, sub_arr in pool.imap_unordered(_worker_build_subset, args_list):
            pending.append(sub_arr)
            n_ngrams_total += n_ng
            n_docs_total += n_docs
            n_done += 1
            # flush every 8 files to bound peak memory
            if len(pending) >= 8:
                flush_pending()
            elapsed = time.time() - t0
            log.info(
                "  [%s] received %s (%d/%d files, %d docs, %d raw, %d sub-uniq, |master|=%d, |pending|=%d) — elapsed %.1fs, %.1fs/file avg",
                name, fname, n_done, len(files), n_docs, n_ng, sub_arr.size,
                master_arr.size, len(pending), elapsed, elapsed / n_done,
            )
    flush_pending()
    # commit master_arr to ExactHashSet's frozen slot
    master.sorted_arr = master_arr
    master.hashes = set()
    log.info(
        "[%s] DONE — %d docs, %d raw n-grams, %d unique (%.2f GB), %.1fs total",
        name, n_docs_total, n_ngrams_total, master_arr.size,
        master_arr.nbytes / 1e9, time.time() - t0,
    )
    return n_ngrams_total


def load_slice_into_set_single(slice_spec: str, master: ExactHashSet) -> int:
    """Single-threaded fallback (e.g. for HF streaming)."""
    name, source = slice_spec.split(":", 1)
    if source.startswith("/") or source.startswith("./"):
        doc_iter = iter_slice_local(Path(source))
    else:
        doc_iter = iter_slice_hf(source)
    n_ngrams = 0
    n_docs = 0
    for txt in doc_iter:
        norm = normalize_text(txt)
        toks = norm.split()
        for ng in ngrams(toks):
            master.add(hash_ngram(ng))
            n_ngrams += 1
        n_docs += 1
        if n_docs % 10_000 == 0:
            log.info("  [%s] %d docs, %d ngrams, |master|=%d", name, n_docs, n_ngrams, len(master.hashes))
    log.info("[%s] DONE — %d docs, %d n-grams, %d unique", name, n_docs, n_ngrams, len(master.hashes))
    return n_ngrams


# ----------------------------------------- legacy bloom helpers (kept for reference)
def _worker_build_subbloom(args: tuple) -> tuple[str, int, int, bytes]:
    """
    Per-file worker: build a sub-bloom of given size/n_hashes from one slice file.
    Returns (filename, n_docs, n_ngrams, bloom_bytes_for_OR_merge).

    Pickling a 240MB bytes blob between worker and parent is OK once per file;
    the alternative (shared-memory mmap of one giant bloom under a lock) would
    serialize all writes and kill parallelism.
    """
    file_path, bloom_size, n_hashes, slice_name = args
    bf = BloomFilter.__new__(BloomFilter)
    bf.size = bloom_size
    bf.n_hashes = n_hashes
    bf.n_items = 1  # unused after construction
    bf.fp_rate = BLOOM_FP_RATE
    bf.bits = bitarray(bloom_size)
    bf.bits.setall(False)

    n_docs = 0
    n_ngrams = 0
    f = Path(file_path)
    for txt in _iter_one_slice_file(f):
        norm = normalize_text(txt)
        toks = norm.split()
        for ng in ngrams(toks):
            bf.add(hash_ngram(ng))
            n_ngrams += 1
        n_docs += 1
    return (f.name, n_docs, n_ngrams, bf.bits.tobytes())


def load_slice_into_bloom_parallel(
    slice_spec: str, bf: BloomFilter, n_workers: int
) -> int:
    """
    Parallel build: shard slice files across workers, each builds a sub-bloom of
    identical geometry, merge by bitwise OR into the master bloom `bf`.

    HF (streaming) sources are not supported here — they fall back to single-threaded.
    """
    name, source = slice_spec.split(":", 1)
    if not (source.startswith("/") or source.startswith("./")):
        log.info("[%s] HF source — falling back to single-threaded ingest", name)
        return load_slice_into_bloom(slice_spec, bf, bf.n_items)

    files = _list_slice_files(Path(source))
    log.info("[%s] %d files, %d workers", name, len(files), n_workers)
    if not files:
        return 0

    args_list = [(str(f), bf.size, bf.n_hashes, name) for f in files]

    t0 = time.time()
    n_ngrams_total = 0
    n_docs_total = 0
    n_done = 0
    # imap_unordered so we OR-merge as workers finish (overlap merge with worker compute)
    with mp.Pool(n_workers) as pool:
        for fname, n_docs, n_ng, sub_bytes in pool.imap_unordered(_worker_build_subbloom, args_list):
            sub_bits = bitarray()
            sub_bits.frombytes(sub_bytes)
            # frombytes() rounds up to byte boundary; trim back to master length
            if len(sub_bits) > bf.size:
                sub_bits = sub_bits[: bf.size]
            bf.bits |= sub_bits
            n_ngrams_total += n_ng
            n_docs_total += n_docs
            n_done += 1
            elapsed = time.time() - t0
            log.info(
                "  [%s] merged %s (%d/%d files, %d docs, %d ngrams) — elapsed %.1fs, %.1fs/file avg",
                name, fname, n_done, len(files), n_docs, n_ng, elapsed, elapsed / n_done,
            )
    log.info("[%s] DONE — %d docs, %d n-grams, %.1fs total", name, n_docs_total, n_ngrams_total, time.time() - t0)
    return n_ngrams_total


# ----------------------------------------------------------------- problem load
def load_problems(path: Path) -> list[dict]:
    """
    Expected jsonl: {"problem_id": str, "text": str, ...}.
    `text` should be the normalized problem statement (the surface that would
    appear in arXiv source if the problem were in the pretraining slice).
    """
    out = []
    with open(path) as f:
        for line in f:
            obj = json.loads(line)
            if "problem_id" not in obj or "text" not in obj:
                raise ValueError(f"bad row: keys={list(obj.keys())[:5]}")
            out.append(obj)
    log.info("problems loaded: %d", len(out))
    return out


# ----------------------------------------------------------------------- audit
def audit_problem(problem: dict, blooms: dict[str, BloomFilter]) -> dict:
    norm = normalize_text(problem["text"])
    toks = norm.split()
    all_ngrams = list(ngrams(toks))
    per_slice_hits: dict[str, int] = {}
    per_slice_examples: dict[str, list[str]] = {}
    for slice_name, bf in blooms.items():
        hits = []
        for ng in all_ngrams:
            if hash_ngram(ng) in bf:
                hits.append(" ".join(ng))
        per_slice_hits[slice_name] = len(hits)
        per_slice_examples[slice_name] = hits[:SPOTCHECK_CAP_PER_SLICE]
    hits_total = sum(per_slice_hits.values())
    return {
        "problem_id": problem["problem_id"],
        "n_grams_total": len(all_ngrams),
        "per_slice_hits": per_slice_hits,
        "per_slice_examples": per_slice_examples,
        "hits_total": hits_total,
        "in_S0": hits_total == S0_MAX_HITS,
        "in_S1": hits_total <= S1_MAX_HITS,
    }


# ---------------------------------------------------------------------- output
def write_csv(rows: list[dict], slice_names: list[str], out: Path) -> None:
    import csv
    cols = (
        ["problem_id", "n_grams_total"]
        + [f"hits_{n}" for n in slice_names]
        + [f"docs_{n}" for n in slice_names]
        + [f"unique_ngrams_{n}" for n in slice_names]
        + ["hits_total", "docs_total", "unique_ngrams_total",
           "in_S0", "in_S1", "in_S0_docs", "in_S1_docs"]
    )
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(
                [r["problem_id"], r["n_grams_total"]]
                + [r["per_slice_hits"][n] for n in slice_names]
                + [r.get("per_slice_docs", {}).get(n, 0) for n in slice_names]
                + [r.get("per_slice_unique_ngrams", {}).get(n, 0) for n in slice_names]
                + [r["hits_total"], r.get("docs_total", 0), r.get("unique_ngrams_total", 0),
                   int(r["in_S0"]), int(r["in_S1"]),
                   int(r.get("in_S0_docs", r["in_S0"])), int(r.get("in_S1_docs", r["in_S1"]))]
            )


def write_jsonl(rows: list[dict], out: Path) -> None:
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_md_summary(rows: list[dict], slice_names: list[str], out: Path) -> None:
    n = len(rows)
    s0 = sum(r["in_S0"] for r in rows)
    s1 = sum(r["in_S1"] for r in rows)
    s0_docs = sum(r.get("in_S0_docs", r["in_S0"]) for r in rows)
    s1_docs = sum(r.get("in_S1_docs", r["in_S1"]) for r in rows)
    hits_dist = Counter(r["hits_total"] for r in rows)
    docs_dist = Counter(r.get("docs_total", 0) for r in rows)
    per_slice_hits_dist = {
        n_: Counter(r["per_slice_hits"][n_] for r in rows) for n_ in slice_names
    }
    abort = s1_docs < HARD_ABORT_S1_FLOOR
    lines = [
        "# Contamination audit — summary",
        "",
        f"Total problems: **{n}**",
        "",
        "## Headline (doc-unique counting; carlini 2026-04-23 fix)",
        "",
        f"Strict cleaned subset S₀ (docs_total == 0): **{s0_docs}** ({100*s0_docs/n:.1f}%)",
        f"Lenient cleaned subset S₁ (docs_total ≤ 2): **{s1_docs}** ({100*s1_docs/n:.1f}%)",
        "",
        f"**Hard-abort floor (|S₁_docs| < 150):** {'TRIGGERED — abort cleaned-subset re-eval' if abort else 'not triggered — proceed'}",
        "",
        "## Legacy (occurrence counting; pre-2026-04-23)",
        "",
        f"S₀ (hits_total == 0): {s0} ({100*s0/n:.1f}%)",
        f"S₁ (hits_total ≤ 2): {s1} ({100*s1/n:.1f}%)",
        "",
        "## docs_total distribution (distinct source-docs containing ≥1 hit, summed across slices)",
        "",
        "| docs_total | count |",
        "|---|---|",
    ]
    for k in sorted(docs_dist):
        lines.append(f"| {k} | {docs_dist[k]} |")
    lines += ["", "## hits_total distribution (occurrence-count, legacy)", "", "| hits_total | count |", "|---|---|"]
    for k in sorted(hits_dist):
        lines.append(f"| {k} | {hits_dist[k]} |")
    lines += ["", "## Per-slice hit distribution (occurrences)"]
    for n_ in slice_names:
        lines += ["", f"### {n_}", "", "| hits | count |", "|---|---|"]
        for k in sorted(per_slice_hits_dist[n_]):
            lines.append(f"| {k} | {per_slice_hits_dist[n_][k]} |")
    out.write_text("\n".join(lines))


# ------------------------------------------------------------------------- main
def main() -> None:
    global N_GRAM
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--problems", type=Path, required=True)
    p.add_argument("--slice", action="append", required=True, help="name:source (HF id or local dir)")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--bloom-est-ngrams", type=int, default=10_000_000_000,
                   help="estimate of unique n-grams across all slices (for bloom sizing; only used with --use-bloom)")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 4),
                   help="parallel workers for slice ingest (default: nproc-4)")
    p.add_argument("--use-bloom", action="store_true",
                   help="use bloom filter (legacy; large public-corpus slices can saturate this path). "
                        "Default = reverse-probe (memory-fixed, FP-free).")
    p.add_argument("--use-exact-set", action="store_true",
                   help="use exact-set forward (build all-corpus hash set then probe per problem). "
                        "This path is memory-intensive and is kept for reproducibility.")
    p.add_argument("--no-normalize", action="store_true",
                   help="disable lowercase + LaTeX-cmd-strip; keep only whitespace collapse.")
    p.add_argument("--n-gram", type=int, default=N_GRAM,
                   help="n-gram length for the overlap probe (default: 13, the v1.0 release-defining threshold).")
    args = p.parse_args()

    N_GRAM = args.n_gram
    log.info("n-gram length: %d", N_GRAM)

    global NORMALIZE_ENABLED
    NORMALIZE_ENABLED = not args.no_normalize
    log.info("normalization: %s", "ENABLED (lowercase + strip-LaTeX)" if NORMALIZE_ENABLED else "DISABLED (whitespace-only)")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    problems = load_problems(args.problems)

    # ------- algorithm selector -------
    if args.use_bloom:
        algo = "bloom"
    elif args.use_exact_set:
        algo = "exact-forward"
    else:
        algo = "reverse-probe"
    log.info("algorithm: %s", algo)

    if algo == "reverse-probe":
        probe, ngram_count = build_problem_probe(problems)
        rows, slice_names = run_reverse_probe_audit(args.slice, probe, ngram_count, args.workers)
        suffix = "" if NORMALIZE_ENABLED else "-nonorm"
        write_csv(rows, slice_names, args.out_dir / f"contamination-audit{suffix}.csv")
        write_jsonl(rows, args.out_dir / f"contamination-audit{suffix}.jsonl")
        write_md_summary(rows, slice_names, args.out_dir / f"contamination-audit{suffix}.md")
        s1_docs = sum(r.get("in_S1_docs", r["in_S1"]) for r in rows)
        if s1_docs < HARD_ABORT_S1_FLOOR:
            log.warning(
                "ABORT GATE: |S1_docs|=%d < %d. Cleaned-subset re-evaluation is underpowered.",
                s1_docs, HARD_ABORT_S1_FLOOR,
            )
        log.info("done — wrote %s/", args.out_dir)
        return

    # ------- legacy paths -------
    slice_names: list[str] = []
    blooms: dict[str, "BloomFilter | ExactHashSet"] = {}
    for spec in args.slice:
        name = spec.split(":", 1)[0]
        slice_names.append(name)
        if algo == "bloom":
            bf = BloomFilter(n_items=args.bloom_est_ngrams)
            if args.workers > 1:
                load_slice_into_bloom_parallel(spec, bf, args.workers)
            else:
                load_slice_into_bloom(spec, bf, args.bloom_est_ngrams)
            blooms[name] = bf
        else:  # exact-forward
            es = ExactHashSet()
            if args.workers > 1:
                load_slice_into_set_parallel(spec, es, args.workers)
            else:
                load_slice_into_set_single(spec, es)
            blooms[name] = es

    log.info("auditing %d problems against %d slices", len(problems), len(blooms))
    rows = [audit_problem(prob, blooms) for prob in problems]

    suffix = "" if NORMALIZE_ENABLED else "-nonorm"
    write_csv(rows, slice_names, args.out_dir / f"contamination-audit{suffix}.csv")
    write_jsonl(rows, args.out_dir / f"contamination-audit{suffix}.jsonl")
    write_md_summary(rows, slice_names, args.out_dir / f"contamination-audit{suffix}.md")

    s1 = sum(r["in_S1"] for r in rows)
    if s1 < HARD_ABORT_S1_FLOOR:
        log.warning(
            "ABORT GATE: |S1|=%d < %d. Cleaned-subset re-evaluation is underpowered.",
            s1, HARD_ABORT_S1_FLOOR,
        )

    log.info("done — wrote %s/", args.out_dir)


if __name__ == "__main__":
    main()
