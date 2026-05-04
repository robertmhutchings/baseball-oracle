#!/usr/bin/env python3
"""
Phase 2 decimal-fraction scan — surfaces decimal-fraction values in any
int_col across all 5 spec functions in ingest_full.py:
  spec_games, spec_batting, spec_pitching, spec_fielding, spec_teamstats.

Companion to phase2_sentinel_scan.py and phase2_boolean_audit.py. Read-only
against data/<year>/<year>*.csv. Saved as a durable artifact (per CLAUDE.md
working convention) so the same audit can be re-run after fixes.

Background
----------
The 2026-04-29 dry-run halted at 1943gameinfo line 918 (KCM194307182) on
timeofgame='0.0590277777777778'. That value × 1440 = 85.0 exactly, suggesting
the source duration (85 minutes / 1h 25m) was exported as a fraction-of-day
decimal instead of an integer-minutes count.

The first version of this scan (gameinfo-only) found exactly 1 hit. This
version extends to all int_cols across all 5 specs, to test the broader
hypothesis: "Excel-fraction encoding leakage is one underlying Retrosheet
data-prep issue affecting multiple tables."

Detection
---------
A value is "decimal-fraction-shaped" if (after .strip()) it contains '.',
'e', or 'E'. Intentionally over-catches.

Plausibility check (×1440 → minutes)
-------------------------------------
Applied ONLY to known time fields. The only int_col that is genuinely a
time field is games.timeofgame. (p_ipouts is outs-recorded per
schema.sql:309, not innings; verified against 1998 distribution which
peaks at 3/6/27 — clean integer outs, no fractions.)

For non-time int_cols: report the value verbatim with no ×1440 test.
This deliberately distinguishes:
  - Excel-fraction-time-leakage  (recoverable as round(v*1440) minutes)
  - Batting-average-style leakage (e.g. '0.286' misaligned into a count
    column from a rate column elsewhere) — NOT a time recovery candidate

Row clustering
--------------
For each row with ANY decimal-fraction hit, capture every int_col on that
row that is decimal-fraction-shaped. A row with hits in multiple columns
is a row-misalignment suspect (the entire row may be shifted by columns,
not a single-column encoding error).

Reporting
---------
Per (table) section:
  1. Per-column hit count
  2. Per-year hit count
  3. Multi-column row clustering (rows with >=2 column hits)
  4. Full enumeration of hits, with ×1440 interpretation for time fields
"""

import csv
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path('C:/BaseballOracle/data')

# Mirror ingest_full.py's int_cols across all 5 spec functions.
GAMES_INT_COLS = (
    'number', 'innings', 'timeofgame',
    'temp', 'windspeed', 'vruns', 'hruns', 'season',
    'tiebreaker',
)
BATTING_INT_COLS = (
    'b_lp', 'b_seq', 'number',
    'b_pa', 'b_ab', 'b_r', 'b_h', 'b_d', 'b_t', 'b_hr', 'b_rbi',
    'b_sh', 'b_sf', 'b_hbp', 'b_w', 'b_iw', 'b_k',
    'b_sb', 'b_cs', 'b_gdp', 'b_xi', 'b_roe',
)
PITCHING_INT_COLS = (
    'p_seq', 'number',
    'p_ipouts', 'p_noout', 'p_bfp',
    'p_h', 'p_d', 'p_t', 'p_hr', 'p_r', 'p_er',
    'p_w', 'p_iw', 'p_k', 'p_hbp', 'p_wp', 'p_bk',
    'p_sh', 'p_sf', 'p_sb', 'p_cs', 'p_pb',
)
FIELDING_INT_COLS = (
    'd_seq', 'd_pos', 'number',
    'd_ifouts', 'd_po', 'd_a', 'd_e', 'd_dp', 'd_tp',
    'd_pb', 'd_wp', 'd_sb', 'd_cs',
)
TEAMSTATS_INT_COLS = (
    *(f'inn{i}' for i in range(1, 29)),
    'lob', 'number',
    'b_pa', 'b_ab', 'b_r', 'b_h', 'b_d', 'b_t', 'b_hr', 'b_rbi',
    'b_sh', 'b_sf', 'b_hbp', 'b_w', 'b_iw', 'b_k',
    'b_sb', 'b_cs', 'b_gdp', 'b_xi', 'b_roe',
    'p_ipouts', 'p_noout', 'p_bfp',
    'p_h', 'p_d', 'p_t', 'p_hr', 'p_r', 'p_er',
    'p_w', 'p_iw', 'p_k', 'p_hbp', 'p_wp', 'p_bk',
    'p_sh', 'p_sf', 'p_sb', 'p_cs', 'p_pb',
    'd_po', 'd_a', 'd_e', 'd_dp', 'd_tp',
    'd_pb', 'd_wp', 'd_sb', 'd_cs',
)

# (table-display, csv-suffix, int_cols, row-key-cols-for-clustering)
TARGETS = [
    ('retro.games',     'gameinfo.csv',  GAMES_INT_COLS,
     ('gid',)),
    ('retro.batting',   'batting.csv',   BATTING_INT_COLS,
     ('gid', 'id', 'b_lp', 'b_seq', 'stattype')),
    ('retro.pitching',  'pitching.csv',  PITCHING_INT_COLS,
     ('gid', 'id', 'p_seq', 'stattype')),
    ('retro.fielding',  'fielding.csv',  FIELDING_INT_COLS,
     ('gid', 'id', 'd_seq', 'd_pos', 'stattype')),
    ('retro.teamstats', 'teamstats.csv', TEAMSTATS_INT_COLS,
     ('gid', 'team', 'stattype')),
]

# Time-field allowlist: columns where a decimal-fraction CAN be recovered
# as round(v * 1440) minutes. Keyed by (table, column).
TIME_FIELD_ALLOWLIST = {
    ('retro.games', 'timeofgame'),
}


def is_decimal_fraction_shaped(v: str) -> bool:
    if v == '':
        return False
    return any(ch in v for ch in '.eE')


def x1440_interp(v: str):
    try:
        f = float(v)
    except ValueError:
        return None, False
    scaled = f * 1440
    rounded = round(scaled)
    return rounded, abs(scaled - rounded) < 0.01


def scan_table(table, csv_suffix, int_cols, row_key_cols):
    print(f'================ {table} ({csv_suffix}) ================')
    per_col = Counter()
    per_year = Counter()
    # row_key -> list of (year, col, value) tuples for every flagged col
    row_hits = defaultdict(list)

    for year in range(1901, 2024):
        f = DATA / str(year) / f'{year}{csv_suffix}'
        if not f.exists():
            continue
        with f.open(newline='', encoding='utf-8') as fp:
            r = csv.DictReader(fp)
            for row in r:
                row_flags = []
                for col in int_cols:
                    v = (row.get(col) or '').strip()
                    if is_decimal_fraction_shaped(v):
                        row_flags.append((col, v))
                if not row_flags:
                    continue
                key = tuple((row.get(k) or '').strip() for k in row_key_cols)
                for col, v in row_flags:
                    per_col[col] += 1
                    per_year[year] += 1
                    row_hits[(year, key)].append((col, v))

    total_hits = sum(per_col.values())
    print(f'  Total hits: {total_hits} (across {len(row_hits)} distinct rows)')
    print()

    if total_hits == 0:
        print('  (no decimal-fraction values in any int_col for this table)')
        print()
        return

    print('  Per-column counts:')
    for col, c in per_col.most_common():
        print(f'    {col}: {c}')
    print()

    print('  Per-year counts:')
    for y in sorted(per_year):
        print(f'    {y}: {per_year[y]}')
    print()

    multi_col_rows = {k: hs for k, hs in row_hits.items() if len(hs) >= 2}
    print(f'  Multi-column rows (>=2 decimal-fraction hits in same row): '
          f'{len(multi_col_rows)}')
    if multi_col_rows:
        for (y, key), hs in sorted(multi_col_rows.items()):
            key_str = '/'.join(repr(k) for k in key)
            print(f'    {y} {key_str}: {hs}')
    print()

    print('  Full enumeration (year, row-key, column, value, x1440 if time field):')
    for (y, key), hs in sorted(row_hits.items()):
        key_str = '/'.join(repr(k) for k in key)
        for col, v in hs:
            extra = ''
            if (table, col) in TIME_FIELD_ALLOWLIST:
                xi, xc = x1440_interp(v)
                if xc:
                    extra = f'  [x1440={xi} min, recoverable]'
                else:
                    extra = '  [x1440=non-integer, NOT recoverable]'
            print(f'    {y} {key_str}  {col}={v!r}{extra}')
    print()


def main() -> None:
    for table, csv_suffix, int_cols, row_key_cols in TARGETS:
        scan_table(table, csv_suffix, int_cols, row_key_cols)

    print('============================================================')
    print('Scan complete. See per-table sections above for details.')


if __name__ == '__main__':
    main()
