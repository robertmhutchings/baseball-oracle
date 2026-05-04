# 1943 KCM194307182 — timeofgame Excel-fraction recovery

**Date:** 2026-04-29
**File:** `data/1943/1943gameinfo.csv`
**Row identifier:** line 918, gid `KCM194307182`
**Column:** `timeofgame`

## Change

| | value |
|---|---|
| before | `0.0590277777777778` |
| after | `85` |

## Why

Retrosheet's source CSV exported this single row with the time-of-game value
encoded as a fraction-of-day decimal (Excel-artifact pattern) instead of an
integer-minutes count. Mathematically: `0.0590277777777778 × 1440 = 85.0`
exactly. The value is recoverable losslessly — 85 is the source's intended
85 minutes.

## Why source-data fix vs. ingest transform

This is the only row in 123 years of gameinfo data that exhibits this
pattern (verified by `ingest/phase2_decimal_fraction_scan.py`). A generic
ingest-time transform would be ~10 lines of code for one row. Single-byte
source fix is simpler, fully documented, and reversible.

## Cross-references

- Halt surfaced 2026-04-27 dry-run (post-Item-22 + Item-25 fixes).
- Pattern type: same as CLAUDE.md §4 item 16 (`starttime` fraction-of-day
  encoding) but in `timeofgame` instead.
- Bounded scope confirmed by `ingest/phase2_decimal_fraction_scan.py`:
  zero other gameinfo int_cols, zero batting / pitching / teamstats hits;
  only fielding had unrelated `'value'`-bleed misalignment in 1949
  MEM194904112 (separate Item 24 work).

## How to reverse

Edit `data/1943/1943gameinfo.csv` line 918, change `,85,` (in the
timeofgame position, between `htbf` empty and `attendance` empty) back
to `,0.0590277777777778,`.
