#!/usr/bin/env python3
"""
Phase 2 boolean audit — surfaces both halt-prone AND silently-miscoerced
values across every bool_col in ingest_full.py's spec functions.

Companion to phase2_sentinel_scan.py. Read-only against data/<year>/*.csv.
Saved as a durable artifact (per CLAUDE.md working convention) so the same
audit can be re-run after future ingest changes.

Background
----------
The 2026-04-28 dry-run halted at forfeit='H' (HOM193806191, 1938). Investigation
revealed forfeit also has 6 'Y' rows that had been silently mapped to True
because 'y' is in to_bool's accept set — even though Retrosheet's spec defines
forfeit as a coded column ('V'/'H'/'T'), not a boolean. The 'Y' rows were
quietly losing their semantic distinction from H/V/T.

This script generalizes that finding: for every column declared as a bool
in any spec_*() function, it surfaces the full distinct-value picture so we
can identify other columns at risk of the same silent corruption.

Reporting
---------
For each (table, column) pair:
  1. Distinct values + counts (full picture)
  2. Halt-prone values  — anything to_bool would raise ValueError on
  3. Suspect values     — anything outside CANONICAL even if to_bool accepts
                          (catches the 'Y'-as-Retrosheet-code class of bug)
  4. Year distribution for halt-prone OR suspect values

CANONICAL set
-------------
Defined by PM 2026-04-28 (intent reconciled with the explicit 'Y is suspect'
example): the unambiguous explicit-spelling boolean forms plus 0/1. Single-
letter codes ('t'/'f'/'y'/'n'/'Y'/'N') are deliberately EXCLUDED so they
surface as suspect — they are exactly the shapes Retrosheet might overload
with code semantics.
"""

import csv
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path('C:/BaseballOracle/data')

# Mirror to_bool's accept logic (both halves lowercased).
TO_BOOL_TRUE = {'1', 'true', 't', 'y', 'yes'}
TO_BOOL_FALSE = {'0', 'false', 'f', 'n', 'no'}

# Per CLAUDE.md §4 items 19-20 — these never raise; map to NULL.
NULL_SENTINELS_LOWER = {'?', 'x', 'unknown'}

CANONICAL = {
    'true', 'false', 'TRUE', 'FALSE', 'True', 'False',
    'yes', 'no', 'YES', 'NO',
    '0', '1',
}

# (table, csv-suffix, [bool_col db-names])
TARGETS = [
    ('retro.games',    'gameinfo.csv', ['usedh', 'htbf', 'forfeit']),
    ('retro.batting',  'batting.csv',  ['dh', 'ph', 'pr']),
    ('retro.pitching', 'pitching.csv', ['wp', 'lp', 'is_save',
                                        'p_gs', 'p_gf', 'p_cg']),
    ('retro.fielding', 'fielding.csv', ['d_gs']),
]

# CSV headers that differ from db column names (per CLAUDE.md §3).
CSV_HEADER_REMAP = {'is_save': 'save'}


def is_halt_prone(v: str) -> bool:
    """True iff to_bool would raise on this value."""
    s = v.strip().lower()
    if s in NULL_SENTINELS_LOWER:
        return False
    return s not in TO_BOOL_TRUE and s not in TO_BOOL_FALSE


def is_suspect(v: str) -> bool:
    """True iff outside CANONICAL (even if to_bool would accept)."""
    return v not in CANONICAL


def main() -> None:
    overall_halt = 0
    overall_suspect = 0

    for table, csv_suffix, columns in TARGETS:
        print(f'================ {table} ({csv_suffix}) ================')
        per_col_distinct = {c: Counter() for c in columns}
        per_col_year_hits = {c: defaultdict(Counter) for c in columns}

        for year in range(1901, 2024):
            f = DATA / str(year) / f'{year}{csv_suffix}'
            if not f.exists():
                continue
            with f.open(newline='', encoding='utf-8') as fp:
                r = csv.DictReader(fp)
                for row in r:
                    for col in columns:
                        csv_col = CSV_HEADER_REMAP.get(col, col)
                        v = (row.get(csv_col) or '').strip()
                        if v == '':
                            continue
                        per_col_distinct[col][v] += 1
                        if is_halt_prone(v) or is_suspect(v):
                            per_col_year_hits[col][year][v] += 1

        for col in columns:
            print(f'  --- {col} ---')
            distinct = per_col_distinct[col]
            if not distinct:
                print('    (all values empty)')
                continue
            print('    Distinct values + counts:')
            for v, c in sorted(distinct.items(), key=lambda x: (-x[1], x[0])):
                halt = is_halt_prone(v)
                suspect = (not halt) and is_suspect(v)
                tag = '  HALT' if halt else ('  SUSPECT' if suspect else '')
                print(f'      {c:>10}x  {v!r}{tag}')

            year_hits = per_col_year_hits[col]
            halt_total = sum(
                cnt for years in year_hits.values()
                for v, cnt in years.items() if is_halt_prone(v)
            )
            suspect_total = sum(
                cnt for years in year_hits.values()
                for v, cnt in years.items()
                if (not is_halt_prone(v)) and is_suspect(v)
            )
            overall_halt += halt_total
            overall_suspect += suspect_total

            print(f'    Halt-prone total: {halt_total}')
            print(f'    Suspect total:    {suspect_total}')
            if year_hits:
                print('    Year distribution (halt | suspect):')
                for y in sorted(year_hits):
                    print(f'      {y}: {dict(year_hits[y])}')
        print()

    print('============================================================')
    print(f'Corpus totals: halt-prone={overall_halt}, suspect={overall_suspect}')


if __name__ == '__main__':
    main()
