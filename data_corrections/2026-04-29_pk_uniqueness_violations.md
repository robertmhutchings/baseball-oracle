# 2026-04-29 PK uniqueness violations — 49 source-data deletions + 1 deferred case

**Date:** 2026-04-29
**Scope:** 13 `<year>allplayers.csv` files in `data/`
**Deleted:** 49 rows total
**Deferred:** 1 case (1949 BLG194905152 plays — see CLAUDE.md §4a Item 27)

## Background

Real ingest halted 2026-04-27 at year 1930 with a `psycopg.errors.UniqueViolation`
on `players_team_year_pkey` for `(cannr102, NSH, 1930)`. The dry-run had
not caught this because COPY-time PK enforcement is DB-only — dry-run
validates value-level transforms but cannot enforce uniqueness constraints.

`phase2_pk_uniqueness_scan.py` (read-only) surfaced the full picture:
- **108 PK violations total** across 3 PK-constrained year-tables
  (`games`, `players_team_year`, `plays`)
- 0 in `games`
- 49 in `players_team_year` (across 13 years)
- 59 in `plays` (all in 1 game: 1949 BLG194905152)

Per-row diagnostic (`pk_dup_diagnostic.py`, one-shot, deleted after) classified each:
- **30 row pairs in 1937 NNL block: ALL IDENTICAL** — clean staging duplicate
- **17 single-row pairs across 12 years: IDENTICAL** — clean delete-one-of-each
- **1 single-row INFO-ASYMMETRY** (1930 cannr102 NSH: throw='R' vs throw='?')
- **1 single-row SEMANTIC-CONFLICT** (2006 kigem001 OAK: pos='2B' vs pos='X')
  — collapses to info-asymmetry once the 'X' = "All-Star / no-position"
  Retrosheet convention is recognized (CLAUDE.md §4 Item 26)
- **59 plays pairs (1949 BLG194905152): SEMANTIC-CONFLICT** — NOT a clean
  staging duplicate; appears to be two different play sets sharing one gid.
  Deferred — see CLAUDE.md §4a Item 27.

## Treatment rule for the 49 mechanically-tractable cases

**For every PK-violating duplicate in `players_team_year`, keep the earlier-line
occurrence and delete the later.** This rule works uniformly:
- 30 NNL block: lines 635-664 are earlier (keep), 665-694 are later (delete).
- 17 identical single-row dups: deletion target arbitrary; "delete later" is conventional.
- 1930 cannr102: line 608 (`throw='R'`, more informative) is earlier — keep;
  line 610 (`throw='?'`) is later — delete.
- 2006 kigem001: line 963 (`pos='2B'`, more specific) is earlier — keep;
  line 968 (`pos='X'`, sentinel-like in modern non-ALS context) is later — delete.

For the two non-identical cases, the earlier occurrence happens to be the
more-informative one — convenient.

## Per-file deletion summary

| year | rows deleted | file row count change |
|---|---|---|
| 1930 | 1 | 968 → 967 |
| 1937 | 31 | 1163 → 1132 |
| 1939 | 1 | 1103 → 1102 |
| 1940 | 1 | 1058 → 1057 |
| 1941 | 1 | 1074 → 1073 |
| 1942 | 1 | 1115 → 1114 |
| 1943 | 3 | 1220 → 1217 |
| 1944 | 5 | 1128 → 1123 |
| 1945 | 1 | 1218 → 1217 |
| 1946 | 1 | 1304 → 1303 |
| 1948 | 1 | 1040 → 1039 |
| 2006 | 1 | 1450 → 1449 |
| 2021 | 1 | 1789 → 1788 |
| **total** | **49** | |

## Full enumeration of (year, id, team) targets deleted

Each entry below is the SECOND occurrence in the source CSV; the FIRST occurrence is preserved.

### 1930 (1 deletion — info-asymmetry)
- `(cannr102, NSH)` — was line 610 (`throw='?'`); kept line 608 (`throw='R'`)

### 1937 (31 deletions — 30-row block + 1 single)

30 rows from the NNL roster block (originally lines 665–694 in 1937allplayers.csv;
all byte-identical to the originals at lines 635–664):

```
benjj101 NNL    browr103 NNL    byrdb101 NNL    carlm101 NNL    dandr101 NNL
day-l101 NNL    duket102 NNL    dulal101 NNL    gibsj101 NNL    harrv102 NNL
hollb106 NNL    hughs101 NNL    jenkf102 NNL    kimbh102 NNL    leonb101 NNL
mackb102 NNL    mcdut101 NNL    parkt101 NNL    perej103 NNL    porta103 NNL
snowf101 NNL    taylj108 NNL    walke103 NNL    wellw101 NNL    welmr101 NNL
westj102 NNL    willc106 NNL    wilsj106 NNL    wrigb104 NNL    wrigz102 NNL
```

Plus 1 single-row identical pair: `(millp101, DT2)` — was line 593; kept line 435.

### 1939 (1 deletion — identical)
- `(cainm101, ECG)` — was line 608; kept line 469

### 1940 (1 deletion — identical)
- `(mackb102, NW2)` — was line 722; kept line 630

### 1941 (1 deletion — identical)
- `(smitb114, SNO)` — was line 1018; kept line 566

### 1942 (1 deletion — identical)
- `(alleh106, JAX)` — was line 555; kept line 249

### 1943 (3 deletions — all identical)
- `(boonl102, HSL)` — was line 865; kept line 550
- `(calhl101, HSL)` — was line 867; kept line 552
- `(wilsd103, HSL)` — was line 885; kept line 572

### 1944 (5 deletions — all identical)
- `(westo102, CAG)` — was line 399; kept line 295
- `(willc107, NW2)` — was line 851; kept line 750
- `(willm107, PH5)` — was line 913; kept line 852
- `(wilsa101, BIR)` — was line 111; kept line 108
- `(younl102, BIR)` — was line 112; kept line 109

### 1945 (1 deletion — identical)
- `(washf101, CIA)` — was line 610; kept line 410

### 1946 (1 deletion — identical)
- `(thomd104, NY6)` — was line 944; kept line 768

### 1948 (1 deletion — identical)
- `(browt105, MEM)` — was line 712; kept line 565

### 2006 (1 deletion — semantic-conflict, treated as info-asymmetry)
- `(kigem001, OAK)` — was line 968 (`pos='X'`, "no position" sentinel for
  postseason-only appearances); kept line 963 (`pos='2B'`, more specific).
  Mark Kiger had 2 PR appearances in the 2006 ALCS only; the `'X'` in the
  modern non-ALS context is consistent with Retrosheet's convention
  documented in CLAUDE.md §4 Item 26.

### 2021 (1 deletion — identical)
- `(barnm001, ALS)` — was line 8; kept line 4

## How to reverse

For each (year, id, team) target above, locate the kept row in the
corresponding `<year>allplayers.csv` and duplicate it at the deleted line
position. The two non-identical cases (1930 cannr102 and 2006 kigem001)
require restoring the specific differing values:

- 1930 cannr102 NSH: restore a duplicate row with `throw='?'` at the original line 610 position.
- 2006 kigem001 OAK: restore a duplicate row with `pos='X'` at the original line 968 position.

For the 1937 NNL block: the 30 rows from lines 635–664 (kept) were originally
duplicated at lines 665–694 — re-duplicating that block restores the original state.

## Cross-references

- Phase 2 PK uniqueness scan: `ingest/phase2_pk_uniqueness_scan.py`
- Per-row diagnostic (one-shot, deleted): `ingest/scratch/pk_dup_diagnostic.py`
- Companion log files (same Layer 3 cleanup pass):
  - `data_corrections/2026-04-29_1943_timeofgame_excel_fraction.md`
  - `data_corrections/2026-04-29_1949_fielding_value_textdup.md`
  - `data_corrections/2026-04-29_1948_NW2_staging_duplicate_deletion.md`
  - `data_corrections/2026-04-29_1948_teamstats_lob_textual_null_markers.md`
- Deferred case for 1949 BLG194905152 plays: CLAUDE.md §4a Item 27 (handled
  via `SKIP_PLAYS_GIDS` constant in `ingest_full.py`, not source-data deletion).
- Retrosheet `pos='X'` convention: CLAUDE.md §4 Item 26.
