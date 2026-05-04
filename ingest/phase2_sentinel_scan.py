"""Phase 2 sentinel scan — read-only.

Scans every per-year CSV in DATA_ROOT (1901–2023) plus the four
cross-year reference CSVs for cell values that would halt the
int/float/bool/date transforms used by ingest_full.py. Categorizes
hits by sentinel kind ('?', '??', '-', '--', 'unk', 'unknown',
'other') and prints one summary table per kind.

Read-only:
  - Never connects to a database.
  - Never modifies any file.
  - Imports ingest_full only for spec functions and transform helpers
    (no main() execution; ingest_full guards with __name__ == "__main__").

Usage:
    python phase2_sentinel_scan.py
    python phase2_sentinel_scan.py > scan_report.txt    # capture report

Background: dry-run halt at year=1937 1937fielding.csv on '?' in d_pos
column. Before changing any transform, this scan answers: which sentinel
kinds appear in halt-prone columns, where, and how often.
"""

import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

INGEST_DIR = Path(__file__).parent
sys.path.insert(0, str(INGEST_DIR))

from ingest_full import (  # noqa: E402
    REFERENCE_SPEC_FNS, YEAR_SPEC_FNS,
    to_int, to_float, to_bool, to_date_yyyymmdd, to_date_mdy,
    DATA_ROOT,
)

YEARS = list(range(1901, 2024))
HALT_PRONE_XFORMS = {to_int, to_float, to_bool, to_date_yyyymmdd, to_date_mdy}
ENUMERATED_SENTINELS = {"?", "??", "-", "--"}
ENUMERATED_LOWER = {"unk", "unknown"}


_classify_cache: dict = {}


def classify(s: str, xform) -> str | None:
    """Bucket a value by what its transform does to it.

    Returns:
        None      — xform(s) succeeds (not halt-prone).
        "?"/"??"/... — halt-prone and matches an enumerated sentinel.
        "other"   — halt-prone and does not match an enumerated sentinel.
    """
    key = (s, id(xform))
    cached = _classify_cache.get(key, "__miss__")
    if cached != "__miss__":
        return cached
    try:
        xform(s)
        result = None
    except Exception:
        if s in ENUMERATED_SENTINELS:
            result = s
        elif s.lower() in ENUMERATED_LOWER:
            result = s.lower()
        else:
            result = "other"
    _classify_cache[key] = result
    return result


def scan_csv(spec, year_label):
    """Yield (kind, table, csv_header, db_col, value, row_sample)
    tuples for each halt-prone value in the CSV described by `spec`.
    """
    csv_path = spec["csv"]
    if not csv_path.exists():
        return
    table = spec["table"]
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            return
        headers_lower = [h.strip().lower() for h in headers]
        halt_prone_cols = []
        for csv_header, db_col, xform in spec["fields"]:
            if xform in HALT_PRONE_XFORMS and csv_header in headers_lower:
                idx = headers_lower.index(csv_header)
                halt_prone_cols.append((idx, csv_header, db_col, xform))
        if not halt_prone_cols:
            return
        for row in reader:
            for idx, csv_header, db_col, xform in halt_prone_cols:
                if idx >= len(row):
                    continue
                v = row[idx].strip()
                if v == "":
                    continue
                kind = classify(v, xform)
                if kind is None:
                    continue
                yield kind, table, csv_header, db_col, v, row[:8]


def fmt_year_list(years_set):
    """Format a sorted set of years as 'min-max (N years)' if >4 entries."""
    ys = sorted(y for y in years_set if isinstance(y, int))
    refs = sorted(y for y in years_set if not isinstance(y, int))
    parts = []
    if ys:
        parts.append(
            f"{ys[0]}-{ys[-1]} ({len(ys)} years)" if len(ys) > 4
            else ", ".join(str(y) for y in ys)
        )
    if refs:
        parts.extend(refs)
    return "; ".join(parts)


def main():
    started = datetime.now()
    findings: dict = defaultdict(list)
    other_values: Counter = Counter()
    files_scanned = 0
    files_skipped = 0

    print("Phase 2 Sentinel Scan")
    print("=" * 60)
    print(f"Started:    {started.isoformat(timespec='seconds')}")
    print(f"DATA_ROOT:  {DATA_ROOT}")
    print(f"Years:      {YEARS[0]}-{YEARS[-1]}")
    print(f"Read-only:  no DB connection, no file mutations")
    print()

    # Reference tables (cross-year)
    for spec_fn in REFERENCE_SPEC_FNS:
        spec = spec_fn()
        if not spec["csv"].exists():
            files_skipped += 1
            continue
        files_scanned += 1
        for kind, table, ch, dc, val, sample in scan_csv(spec, "ref"):
            findings[kind].append({
                "year": "ref", "table": table, "csv_header": ch,
                "db_col": dc, "value": val, "row_sample": sample,
            })
            if kind == "other":
                other_values[val] += 1

    # Per-year tables
    for year in YEARS:
        for spec_fn in YEAR_SPEC_FNS:
            spec = spec_fn(year)
            if not spec["csv"].exists():
                files_skipped += 1
                continue
            files_scanned += 1
            for kind, table, ch, dc, val, sample in scan_csv(spec, year):
                findings[kind].append({
                    "year": year, "table": table, "csv_header": ch,
                    "db_col": dc, "value": val, "row_sample": sample,
                })
                if kind == "other":
                    other_values[val] += 1

    completed = datetime.now()
    duration_s = (completed - started).total_seconds()

    print(f"Files scanned: {files_scanned}")
    print(f"Files missing/skipped: {files_skipped}")
    print(f"Halt-prone values found: "
          f"{sum(len(v) for v in findings.values()):,}")
    print(f"Duration: {duration_s:.1f}s")
    print()

    if not findings:
        print("No halt-prone values found across the corpus.")
        return

    # Per-sentinel tables
    for kind in sorted(findings.keys()):
        entries = findings[kind]
        print("-" * 60)
        print(f"Sentinel: {kind!r}")
        print("-" * 60)
        print(f"Total occurrences: {len(entries):,}")

        years_set = {e["year"] for e in entries}
        print(f"Year coverage: {fmt_year_list(years_set)}")

        col_counts: Counter = Counter(
            (e["table"], e["csv_header"]) for e in entries
        )
        col_years: dict = defaultdict(set)
        for e in entries:
            col_years[(e["table"], e["csv_header"])].add(e["year"])

        print("(table, csv_column) occurrences:")
        for (table, ch), n in col_counts.most_common():
            print(f"  {table}.{ch}: {n:,}  "
                  f"[{fmt_year_list(col_years[(table, ch)])}]")

        print("First 5 row samples:")
        for e in entries[:5]:
            print(f"  year={e['year']} {e['table']}.{e['csv_header']}"
                  f"={e['value']!r}  row[:8]={e['row_sample']}")
        print()

    if "other" in findings and other_values:
        print("-" * 60)
        print("'other' bucket — top 25 distinct values")
        print("-" * 60)
        for val, n in other_values.most_common(25):
            print(f"  {val!r}: {n:,}")
        if len(other_values) > 25:
            print(f"  ...and {len(other_values) - 25:,} more distinct values")
        print()

    # Recommendation
    print("-" * 60)
    print("Recommendation")
    print("-" * 60)
    enumerated_found = [k for k in findings
                        if k in ENUMERATED_SENTINELS or k in ENUMERATED_LOWER]
    other_count = len(findings.get("other", []))
    if enumerated_found and other_count == 0:
        print(
            "Findings are limited to enumerated sentinels. A targeted fix\n"
            "(treat each found enumerated sentinel as None in the halt-prone\n"
            "transforms) should cover the corpus."
        )
    elif enumerated_found and other_count > 0:
        print(
            f"Enumerated sentinels found AND 'other' bucket has "
            f"{other_count:,} entries. Review the 'other' top-values list\n"
            "above. If those values are themselves a small set of recognizable\n"
            "sentinels, expand the enumerated list. If they are malformed\n"
            "numeric strings, deeper investigation is needed before fixing."
        )
    elif other_count > 0:
        print(
            f"Only the 'other' bucket has findings ({other_count:,} entries).\n"
            "Review the top-values list — these may be undiscovered sentinels\n"
            "or genuine data corruption."
        )
    else:
        print("No actionable findings.")


if __name__ == "__main__":
    main()
