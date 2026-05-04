# 1949 MEM194904112 — fielding d_seq text-duplication corruption

**Date:** 2026-04-29
**File:** `data/1949/1949fielding.csv`
**Game:** `MEM194904112` (NY6 @ MEM, 1949-04-11, doubleheader game 2, exhibition)
**Affected lines:** 92, 93, 94, 95, 96, 97, 98 (all 7 fielding records for this game)
**Column:** `d_seq`

## Affected rows

| line | id | team | d_pos | (other cols) |
|---|---|---|---|---|
| 92 | barnd101 | NY6 | 1 | well-formed |
| 93 | ferra103 | NY6 | 1 | well-formed |
| 94 | noblr101 | NY6 | 2 | well-formed |
| 95 | woods103 | MEM | 1 | well-formed |
| 96 | sharp101 | MEM | 1 | well-formed |
| 97 | jonec108 | MEM | 2 | well-formed |
| 98 | colac101 | MEM | 2 | well-formed |

## Change

For all 7 rows: `d_seq` value changed from the literal string `'value'` to empty (NULL).
- 4 rows with d_pos=1: `,value,1,value,` → `,,1,value,`
- 3 rows with d_pos=2: `,value,2,value,` → `,,2,value,`

All other columns (gid, id, team, d_pos, stattype, d_gs, date, number, site, opp, wl, gametype, box) untouched.

## Why

The literal text `'value'` appeared in column `d_seq` (an integer-typed column for fielding-stint sequence number). The value was duplicated from the adjacent `stattype` column, where `'value'` is the canonical Retrosheet stattype literal. Diagnostic from `phase2_decimal_fraction_scan.py` (which incidentally caught these via the `'e'` in `'value'`) plus column-by-column inspection confirmed:

1. Field count is correct (24/24); no column shift.
2. Every column except `d_seq` is well-formed (valid retroIDs, dates, parkids, team codes).
3. `d_pos` holds clean integers (1 or 2) — if a column shift had occurred, d_pos would have inherited stattype's `'value'`, which it didn't.
4. Pattern is uniform across all 7 records of the same game — points to a game-level data prep step, most likely an Excel-style auto-fill that propagated the `'value'` literal from `stattype` into `d_seq` for this game's records.

This is text-duplication into a single cell, NOT a horizontal shift.

## Why NULL rather than infer 1

Retrosheet's own data is inconsistent for 1949 exhibitions:
- Lines 2–13 (BIR194903270, similar early-1949 Negro League exhibition): `d_seq` is empty for all 12 records.
- Lines 87–91 (HOE194904111, same date 1949-04-11): `d_seq=1` for all records.

Both readings exist on the same calendar day. Setting `d_seq=1` for the affected rows would be defensible inference (every player in the 7 affected rows appears exactly once → sequence 1 is the only plausible value if d_seq is populated), but inference is silent substitution of a fabricated value, which violates CLAUDE.md §7 Data Source Principle.

NULL is consistent with Retrosheet's own conventions for similar early-1949 exhibition data (BIR pattern). When both readings are defensible, conservative wins.

## Cross-references

- Surfaced by `ingest/phase2_decimal_fraction_scan.py` (incidentally — 'e' in 'value' triggered the regex).
- Pattern type: CLAUDE.md §4a Item 24 (suspected misalignment / sentinel literals in pre-modern numeric columns).
- Companion to data_corrections/2026-04-29_1943_timeofgame_excel_fraction.md (same Layer 3 cleanup pass).

## How to reverse

For all 7 lines, restore the `'value'` literal in d_seq:
- Lines 92, 93, 95, 96: change `,,1,value,` back to `,value,1,value,`
- Lines 94, 97, 98: change `,,2,value,` back to `,value,2,value,`
