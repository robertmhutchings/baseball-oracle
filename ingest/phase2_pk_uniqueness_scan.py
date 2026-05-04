#!/usr/bin/env python3
"""
Phase 2 PK uniqueness scan — surfaces duplicate primary-key tuples in
the source CSVs that load into PK-constrained tables.

Companion to phase2_sentinel_scan.py, phase2_boolean_audit.py, and
phase2_decimal_fraction_scan.py. Read-only against data/<year>/*.csv plus
the cross-year reference CSVs. Saved as a durable artifact.

Background
----------
Real ingest halted 2026-04-29 at year 1930, loading retro.players_team_year
from 1930allplayers.csv with: UniqueViolation on (cannr102, NSH, 1930).
The dry-run did not catch this because COPY-time PK enforcement is
DB-only — dry-run validates value-level transforms but cannot enforce
uniqueness constraints.

This scan covers the gap: enumerate ALL PK violations in the source CSVs
across the corpus before resuming ingest, so we can batch-fix.

Tables with declared PRIMARY KEY constraints (per schema.sql)
--------------------------------------------------------------
Year-scoped (relevant for this scan):
  retro.games                  PK = gid                       (cross-year scope)
  retro.players_team_year      PK = (id, team, year)          (within-year scope; year is per-file constant)
  retro.plays                  PK = (gid, pn)                 (within-year scope; gid encodes year)

Reference (NOT scanned — already loaded cleanly in stage 1 of the halted run):
  retro.players, retro.relatives, retro.teams, retro.ballparks

Scope nuances
-------------
- games.gid: track across ALL years' gameinfo.csv simultaneously. Cross-year
  collisions would indicate corrupt gids (e.g. the 1948 NW2 staging-duplicate
  pattern, post-Item-3 should be clean). Within-year duplicates would also
  surface here.
- players_team_year.(id, team): year is supplied at ingest from the folder
  name (extras=[(year, year)]), not the CSV. So duplicates can only exist
  within a single year's CSV.
- plays.(gid, pn): gid embeds year, so cross-year impossible by construction.

Output
------
1. Per-table summary of duplicate-key counts
2. Full enumeration of each duplicate (year, key, occurrence-count)
3. For the immediate halt at (cannr102, NSH, 1930): dump the matching
   rows from 1930allplayers.csv with all column values for diagnosis.
"""

import csv
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path('C:/BaseballOracle/data')
YEARS = list(range(1901, 2024))


def scan_games() -> dict:
    """gid uniqueness across ALL years' gameinfo.csv."""
    gid_counts: Counter = Counter()
    gid_files: dict = defaultdict(list)  # gid -> list of (year, line_num)
    for year in YEARS:
        f = DATA / str(year) / f'{year}gameinfo.csv'
        if not f.exists():
            continue
        with f.open(newline='', encoding='utf-8') as fp:
            r = csv.reader(fp)
            try:
                next(r)
            except StopIteration:
                continue
            for line_num, row in enumerate(r, start=2):
                if not row:
                    continue
                gid = row[0].strip()
                if not gid:
                    continue
                gid_counts[gid] += 1
                gid_files[gid].append((year, line_num))
    duplicates = {g: c for g, c in gid_counts.items() if c > 1}
    return {'duplicates': duplicates, 'locations': gid_files}


def scan_players_team_year() -> dict:
    """(id, team) uniqueness within each year's allplayers.csv."""
    per_year_dups: dict = defaultdict(dict)  # year -> {key: count}
    per_year_locations: dict = defaultdict(lambda: defaultdict(list))
    for year in YEARS:
        f = DATA / str(year) / f'{year}allplayers.csv'
        if not f.exists():
            continue
        key_counts: Counter = Counter()
        key_locations: dict = defaultdict(list)
        with f.open(newline='', encoding='utf-8') as fp:
            r = csv.DictReader(fp)
            for line_num, row in enumerate(r, start=2):
                id_ = (row.get('id') or '').strip()
                team = (row.get('team') or '').strip()
                if not id_ or not team:
                    continue
                key = (id_, team)
                key_counts[key] += 1
                key_locations[key].append(line_num)
        for key, c in key_counts.items():
            if c > 1:
                per_year_dups[year][key] = c
                per_year_locations[year][key] = key_locations[key]
    return {'duplicates': per_year_dups, 'locations': per_year_locations}


def scan_plays() -> dict:
    """(gid, pn) uniqueness within each year's plays.csv."""
    per_year_dups: dict = defaultdict(dict)
    per_year_locations: dict = defaultdict(lambda: defaultdict(list))
    for year in YEARS:
        f = DATA / str(year) / f'{year}plays.csv'
        if not f.exists():
            continue
        key_counts: Counter = Counter()
        key_locations: dict = defaultdict(list)
        with f.open(newline='', encoding='utf-8') as fp:
            r = csv.DictReader(fp)
            for line_num, row in enumerate(r, start=2):
                gid = (row.get('gid') or '').strip()
                pn = (row.get('pn') or '').strip()
                if not gid or not pn:
                    continue
                key = (gid, pn)
                key_counts[key] += 1
                key_locations[key].append(line_num)
        for key, c in key_counts.items():
            if c > 1:
                per_year_dups[year][key] = c
                per_year_locations[year][key] = key_locations[key]
    return {'duplicates': per_year_dups, 'locations': per_year_locations}


def dump_halt_rows() -> None:
    """Dump rows from 1930allplayers.csv matching (cannr102, NSH)
    for diagnosis of the immediate halt."""
    f = DATA / '1930' / '1930allplayers.csv'
    print('=' * 60)
    print('Immediate halt: (cannr102, NSH, 1930) row dump')
    print('=' * 60)
    if not f.exists():
        print(f'  ! file not found: {f}')
        return
    with f.open(newline='', encoding='utf-8') as fp:
        r = csv.DictReader(fp)
        headers = r.fieldnames
        print(f'  Headers: {headers}')
        matches = []
        for line_num, row in enumerate(r, start=2):
            id_ = (row.get('id') or '').strip()
            team = (row.get('team') or '').strip()
            if id_ == 'cannr102' and team == 'NSH':
                matches.append((line_num, row))
    print(f'  Matches: {len(matches)}')
    for line_num, row in matches:
        print(f'  -- line {line_num} --')
        for h in headers:
            v = (row.get(h) or '').strip()
            print(f'    {h}: {v!r}')
    print()


def main() -> None:
    print('Phase 2 PK Uniqueness Scan')
    print('=' * 60)
    print()

    # 1. retro.games (gid across all years)
    print('=' * 60)
    print('retro.games — PK = gid (across all years)')
    print('=' * 60)
    games = scan_games()
    n_dup_gids = len(games['duplicates'])
    print(f'  Duplicate gids: {n_dup_gids}')
    if n_dup_gids:
        print('  Full enumeration:')
        for gid, count in sorted(games['duplicates'].items(),
                                  key=lambda x: (-x[1], x[0])):
            locs = games['locations'][gid]
            print(f'    {gid}: {count} occurrences at {locs}')
    print()

    # 2. retro.players_team_year ((id, team) per year)
    print('=' * 60)
    print('retro.players_team_year — PK = (id, team, year), per-year scope')
    print('=' * 60)
    pty = scan_players_team_year()
    total_pty_dups = sum(len(v) for v in pty['duplicates'].values())
    n_years_with_dups = len(pty['duplicates'])
    print(f'  Total duplicate (id, team) keys: {total_pty_dups}')
    print(f'  Years with duplicates: {n_years_with_dups}')
    if total_pty_dups:
        print('  Full enumeration:')
        for year in sorted(pty['duplicates']):
            for key, count in sorted(pty['duplicates'][year].items(),
                                      key=lambda x: (-x[1], x[0])):
                locs = pty['locations'][year][key]
                print(f'    [{year}] {key}: {count} occurrences at lines {locs}')
    print()

    # 3. retro.plays ((gid, pn) per year)
    print('=' * 60)
    print('retro.plays — PK = (gid, pn), per-year scope')
    print('=' * 60)
    plays = scan_plays()
    total_plays_dups = sum(len(v) for v in plays['duplicates'].values())
    n_years_with_dups_plays = len(plays['duplicates'])
    print(f'  Total duplicate (gid, pn) keys: {total_plays_dups}')
    print(f'  Years with duplicates: {n_years_with_dups_plays}')
    if total_plays_dups:
        print('  Full enumeration (truncated to 50 if larger):')
        shown = 0
        for year in sorted(plays['duplicates']):
            for key, count in sorted(plays['duplicates'][year].items(),
                                      key=lambda x: (-x[1], x[0])):
                if shown >= 50:
                    print(f'    ... ({total_plays_dups - shown} more)')
                    break
                locs = plays['locations'][year][key]
                print(f'    [{year}] {key}: {count} occurrences at lines {locs}')
                shown += 1
            if shown >= 50:
                break
    print()

    # 4. Immediate halt diagnosis
    dump_halt_rows()

    # Summary
    print('=' * 60)
    print('Corpus-wide totals')
    print('=' * 60)
    print(f'  games.gid duplicates:                {n_dup_gids}')
    print(f'  players_team_year (id,team) dups:    {total_pty_dups} (across {n_years_with_dups} years)')
    print(f'  plays.(gid,pn) duplicates:           {total_plays_dups} (across {n_years_with_dups_plays} years)')
    grand_total = n_dup_gids + total_pty_dups + total_plays_dups
    print(f'  GRAND TOTAL violations:              {grand_total}')


if __name__ == '__main__':
    main()
