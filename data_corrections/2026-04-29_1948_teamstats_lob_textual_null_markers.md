# 1948 teamstats lob — textual NULL markers in 4 Negro League games

**Date:** 2026-04-29
**File:** `data/1948/1948teamstats.csv`
**Affected lines:** 812, 813, 2000, 2001, 2002, 2003, 4091, 4092 (8 rows across 4 games)
**Column:** `lob` (left on base, integer count column)

## Affected games

| game | date | teams | lines | lob value |
|---|---|---|---|---|
| MEM194805231 | 1948-05-23 (DH game 1) | CVB @ MEM | 812, 813 | `'No'` (×2) |
| MEM194807051 | 1948-07-05 (DH game 1) | BIR @ MEM | 2000, 2001 | `'n'` (×2) |
| MEM194807052 | 1948-07-05 (DH game 2) | BIR @ MEM | 2002, 2003 | `'n'` (×2) |
| MEM194809200 | 1948-09-20 (single) | NW2 @ MEM | 4091, 4092 | `'n'` (×2) |

All 4 games are 1948 Negro League games hosted by Memphis Red Sox (MEM02 / LRK02 sites).

## Change

For all 8 rows: `lob` value changed from textual marker (`'No'` or `'n'`) to empty (NULL).

| pattern | replacement | occurrences |
|---|---|---|
| `,No,,value,` | `,,,value,` | 2 |
| `,n,,value,` | `,,,value,` | 6 |

The `,,value,` anchor (empty `mgr` column + `stattype='value'`) ties each substitution to the lob position adjacent to the canonical stattype column. All 8 substitutions are uniquely identified within the file by these bracketed patterns.

All other columns in all 8 rows untouched — verified by full-row diagnostic before and after the edit.

## Why

`lob` is "left on base," a non-negative integer count of runners stranded at game end. Typical real-game values are 5–15. Values `'n'` and `'No'` are clearly NOT integers. The most likely meaning: **textual NULL markers — "no [value recorded]" or "[value] not available."**

For 1948 Negro League games, where seasonal records were partially reconstructed from incomplete contemporaneous box scores, "lob unknown" is plausible. The marker is structurally equivalent to CLAUDE.md §4 item 19's `'?'` and `'unknown'` (already in the null-sentinel list, mapped to NULL via `_is_null_sentinel`), but uses different surface text.

The 4 affected games share three notable features:
- All hosted by Memphis Red Sox in 1948
- All have the same uniform marker per-game (both teams' rows show the same value)
- Single-cell corruption only — every other column in all 8 rows is well-formed

This points to a per-game data-prep artifact applied at score-keeping time when the lob count couldn't be determined from the source box score.

## Why source-data fix (not adding to sentinel list)

Three options were considered:

- **(A) Source-data fix to NULL** ← chosen
- (B) Add `'n'` and `'No'` to `_is_null_sentinel` in `ingest_full.py`
- (C) Both A and B

Option (A) chosen because:

1. **The 8 affected cells are bounded and fully characterized.** No evidence that `'n'`/`'No'` is a stable Retrosheet convention — only 4 games in 1 year exhibit this shape.

2. **Forward-compatibility (option B) is "design for hypothetical future requirements"** — explicitly warned against in CLAUDE.md §5 working conventions. We don't preemptively add sentinels for hypothetical future data refreshes.

3. **The boolean-audit lesson applies here in reverse.** That audit warned against silent acceptance of values that LOOK like booleans but might be Retrosheet codes. Symmetrically: silently accepting `'n'`/`'No'` as NULL across all int_cols would erase corruption signal in any future ingest that surfaces these markers in a different column. Loud halt is better than silent swallow when we don't have evidence of a stable convention.

4. **Side-effect concern with option (B): `to_bool` currently maps `'n'`/`'no'` → False.** Adding to the null-sentinel list would change that behavior for any future bool_col data containing these. The boolean audit found no such values in the current corpus, but it's still a forward-compat hazard.

If `'n'`/`'No'` recur in a future Retrosheet refresh, the ingest will halt loudly and we'll re-evaluate then.

## Cross-references

- Surfaced as the residual after Items 1–3 in the post-fix `phase2_sentinel_scan.py` run (8 hits, all in `retro.teamstats.lob`).
- Pattern type: 4th distinct sub-pattern of CLAUDE.md §4a Item 24 (general "non-numeric values in numeric columns"). Not row-misalignment, not text-duplication from adjacent column, not staging-duplicate — this is a unique textual NULL marker shape.
- Companion to:
  - data_corrections/2026-04-29_1943_timeofgame_excel_fraction.md
  - data_corrections/2026-04-29_1949_fielding_value_textdup.md
  - data_corrections/2026-04-29_1948_NW2_staging_duplicate_deletion.md

## How to reverse

For each affected line, restore the lob marker value:

| line | gid | team | restore lob to |
|---|---|---|---|
| 812 | MEM194805231 | CVB | `No` |
| 813 | MEM194805231 | MEM | `No` |
| 2000 | MEM194807051 | BIR | `n` |
| 2001 | MEM194807051 | MEM | `n` |
| 2002 | MEM194807052 | BIR | `n` |
| 2003 | MEM194807052 | MEM | `n` |
| 4091 | MEM194809200 | NW2 | `n` |
| 4092 | MEM194809200 | MEM | `n` |

Pattern-based reversal: change `,,,value,` back to `,No,,value,` (lines 812–813) and `,n,,value,` (lines 2000–2003, 4091–4092). Note: the loose `,,,value,` pattern would NOT be unique to the affected rows after restoration (other rows have the same shape with empty lob and empty mgr legitimately), so reversal would need to be line-specific.
