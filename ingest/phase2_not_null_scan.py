#!/usr/bin/env python3
"""
Phase 2 NOT NULL constraint scan — surfaces source-CSV rows with empty
values for columns the DB schema declares NOT NULL.

Companion to phase2_sentinel_scan.py, phase2_boolean_audit.py,
phase2_decimal_fraction_scan.py, and phase2_pk_uniqueness_scan.py.
Read-only. Saved as a durable artifact.

Background
----------
Real ingest halted 2026-04-29 at year 1937 with NotNullViolation on
retro.games.gid (1937gameinfo.csv: a row with all team/date/number
fields populated but empty gid). Dry-run did not catch this because
NOT NULL is a DB-only constraint enforced at COPY time. This scan
covers the gap.

Approach
--------
1. Parse schema/schema.sql for NOT NULL columns per retro.* table:
   - inline PRIMARY KEY (single-column PK)
   - inline NOT NULL
   - trailing PRIMARY KEY (col1, col2, ...) [composite PK; cols are NOT NULL]
2. Cross-check against NOT_NULL_COLS in ingest_full.py — flag drift.
3. For each (table, NOT NULL column), scan the corresponding source
   CSVs across all 1901-2023 year folders and identify rows with
   empty values. Reference tables (players, teams, ballparks,
   relatives) are loaded once in stage 1 of the halted run and
   already succeeded — not re-scanned here.
4. Report per-table violations + per-year/per-column distribution.
5. Dump the immediate halt's full row content (1937 NW2 vs NY5,
   1937-05-30, missing gid).

Special cases
-------------
- retro.players_team_year.year is NOT NULL but the value is supplied
  from the folder name (extras=[(year, year)] in spec_players_team_year),
  not from the CSV. So it is impossible for the CSV to have an empty
  value for this column. Skipped from the scan.
- DB-column-vs-CSV-header renames (retro.pitching.is_save <- 'save',
  retro.plays.pitch_count <- 'count') are handled via DB_TO_CSV map.
  Neither of those renamed columns is NOT NULL, so this is defensive.
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path('C:/BaseballOracle/data')
SCHEMA = Path('C:/BaseballOracle/schema/schema.sql')

INGEST_DIR = Path('C:/BaseballOracle/ingest')
sys.path.insert(0, str(INGEST_DIR))
from ingest_full import NOT_NULL_COLS as INGEST_NOT_NULL_COLS  # noqa: E402

# Year-scoped tables and their CSV-suffix + columns to skip from the
# CSV scan (because the value is supplied externally, not from CSV).
YEAR_TABLES = {
    'retro.games':              ('gameinfo.csv',  set()),
    'retro.players_team_year':  ('allplayers.csv', {'year'}),
    'retro.batting':            ('batting.csv',   set()),
    'retro.pitching':           ('pitching.csv',  set()),
    'retro.fielding':           ('fielding.csv',  set()),
    'retro.teamstats':          ('teamstats.csv', set()),
    'retro.plays':              ('plays.csv',     set()),
}

# DB column -> CSV header for renamed columns (defensive; neither is NOT NULL).
DB_TO_CSV = {
    ('retro.pitching', 'is_save'): 'save',
    ('retro.plays', 'pitch_count'): 'count',
}


def parse_not_null_from_schema(path: Path) -> dict:
    """Return dict: table_name -> set of NOT NULL column names.

    Handles three syntactic patterns:
      - inline single-column PRIMARY KEY: 'col TYPE PRIMARY KEY,'
      - inline NOT NULL:                  'col TYPE NOT NULL,'
      - trailing composite PRIMARY KEY:   'PRIMARY KEY (col1, col2)'
    """
    result: dict = defaultdict(set)
    current_table = None

    with path.open(encoding='utf-8') as f:
        for line in f:
            # Strip line comments
            if '--' in line:
                line = line[:line.index('--')]
            line = line.strip()
            if not line:
                continue

            # Detect CREATE TABLE retro.X (
            m = re.match(r'CREATE TABLE\s+retro\.(\w+)\s*\(', line, re.IGNORECASE)
            if m:
                current_table = f'retro.{m.group(1)}'
                continue

            if current_table is None:
                continue

            # End of CREATE TABLE block
            if line.startswith(')'):
                current_table = None
                continue

            # Trailing composite PRIMARY KEY (col1, col2, ...)
            m = re.match(r'PRIMARY KEY\s*\(([^)]+)\)', line, re.IGNORECASE)
            if m:
                cols = [c.strip() for c in m.group(1).split(',')]
                result[current_table].update(cols)
                continue

            # Inline column line: starts with bare identifier
            parts = line.split()
            if not parts:
                continue
            colname = parts[0]
            if not re.match(r'^\w+$', colname):
                continue
            line_upper = line.upper()
            if 'PRIMARY KEY' in line_upper or 'NOT NULL' in line_upper:
                result[current_table].add(colname)

    return dict(result)


def scan_table(table: str, not_null_cols: set, csv_skip_cols: set) -> list:
    """Scan all year CSVs for the given table; return list of violation dicts."""
    csv_suffix, _ = YEAR_TABLES[table]
    cols_to_check = sorted(not_null_cols - csv_skip_cols)
    if not cols_to_check:
        return []

    violations = []
    for year in range(1901, 2024):
        f = DATA / str(year) / f'{year}{csv_suffix}'
        if not f.exists():
            continue
        with f.open(newline='', encoding='utf-8') as fp:
            r = csv.DictReader(fp)
            for line_num, row in enumerate(r, start=2):
                for db_col in cols_to_check:
                    csv_col = DB_TO_CSV.get((table, db_col), db_col)
                    v = (row.get(csv_col) or '').strip()
                    if v == '':
                        violations.append({
                            'year': year,
                            'line': line_num,
                            'table': table,
                            'db_col': db_col,
                            'csv_col': csv_col,
                            'gid': (row.get('gid') or '').strip(),
                            'visteam': (row.get('visteam') or '').strip(),
                            'hometeam': (row.get('hometeam') or '').strip(),
                            'team': (row.get('team') or '').strip(),
                            'date': (row.get('date') or '').strip(),
                            'number': (row.get('number') or '').strip(),
                        })
    return violations


def dump_halt_row() -> None:
    """Dump the full row content for the immediate halt: 1937 NY5 @ NW2,
    1937-05-30, number=1, missing gid."""
    print('=' * 60)
    print('Immediate halt row dump (1937gameinfo.csv)')
    print('=' * 60)
    f = DATA / '1937' / '1937gameinfo.csv'
    if not f.exists():
        print(f'  ! file not found: {f}')
        return
    with f.open(newline='', encoding='utf-8') as fp:
        r = csv.DictReader(fp)
        for line_num, row in enumerate(r, start=2):
            gid = (row.get('gid') or '').strip()
            visteam = (row.get('visteam') or '').strip()
            hometeam = (row.get('hometeam') or '').strip()
            date = (row.get('date') or '').strip()
            number = (row.get('number') or '').strip()
            if (gid == '' and visteam == 'NY5' and hometeam == 'NW2'
                    and date == '19370530' and number == '1'):
                print(f'  -- line {line_num} --')
                for k, v in row.items():
                    vs = (v or '').strip()
                    marker = ('  <-- EMPTY (NOT NULL violation)'
                              if k == 'gid' else '')
                    print(f'    {k}: {vs!r}{marker}')
                return
    print('  ! row not found in 1937gameinfo.csv')


def main() -> None:
    print('Phase 2 NOT NULL constraint scan')
    print('=' * 60)
    print()

    # 1. Parse schema.sql
    schema_nn = parse_not_null_from_schema(SCHEMA)
    print('NOT NULL columns parsed from schema.sql:')
    for tbl in sorted(schema_nn):
        print(f'  {tbl}: {sorted(schema_nn[tbl])}')
    print()

    # 2. Cross-check vs ingest_full.py NOT_NULL_COLS
    print('Drift check vs ingest_full.py NOT_NULL_COLS:')
    drift = False
    all_tables = set(schema_nn) | set(INGEST_NOT_NULL_COLS)
    for tbl in sorted(all_tables):
        s = schema_nn.get(tbl, set())
        i = INGEST_NOT_NULL_COLS.get(tbl, set())
        if s != i:
            drift = True
            print(f'  {tbl}:')
            print(f'    schema only:      {sorted(s - i)}')
            print(f'    ingest_full only: {sorted(i - s)}')
    if not drift:
        print('  (no drift — schema and ingest_full agree)')
    print()

    # 3. Scan year CSVs (using schema as authoritative)
    print('=' * 60)
    print('Violation scan (schema.sql is authoritative)')
    print('=' * 60)
    print()

    grand_total = 0
    all_violations: list = []
    for tbl in YEAR_TABLES:
        nn_cols = schema_nn.get(tbl, set())
        skip = YEAR_TABLES[tbl][1]
        violations = scan_table(tbl, nn_cols, skip)
        all_violations.extend(violations)
        grand_total += len(violations)

        print(f'{tbl}: {len(violations)} violations '
              f'(NOT NULL cols scanned: '
              f'{sorted(nn_cols - skip)})')
        if not violations:
            continue

        per_col = Counter(v['db_col'] for v in violations)
        per_year = Counter(v['year'] for v in violations)
        print(f'  per-column breakdown: {dict(per_col)}')
        print(f'  per-year breakdown:')
        for y in sorted(per_year):
            print(f'    {y}: {per_year[y]}')

        print(f'  Full enumeration (up to first 50):')
        for v in violations[:50]:
            ctx = []
            if v['gid']:
                ctx.append(f"gid={v['gid']!r}")
            else:
                ctx.append('gid=(empty)')
            if v['visteam']:
                ctx.append(f"vis={v['visteam']}")
            if v['hometeam']:
                ctx.append(f"home={v['hometeam']}")
            if v['team']:
                ctx.append(f"team={v['team']}")
            if v['date']:
                ctx.append(f"date={v['date']}")
            if v['number']:
                ctx.append(f"number={v['number']}")
            print(f'    {v["year"]} line {v["line"]}: '
                  f'empty {v["csv_col"]} ({"/".join(ctx)})')
        if len(violations) > 50:
            print(f'    ... ({len(violations) - 50} more)')
        print()

    # 4. Halt-row dump
    dump_halt_row()
    print()

    # 5. Summary
    print('=' * 60)
    print(f'GRAND TOTAL violations across year-scoped tables: {grand_total}')
    print('=' * 60)


if __name__ == '__main__':
    main()
