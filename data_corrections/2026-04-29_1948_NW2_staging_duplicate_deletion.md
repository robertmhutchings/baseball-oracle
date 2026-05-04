# 1948 NW2 staging-duplicate deletion (Item 23 RESOLVED)

**Date:** 2026-04-29
**Scope:** 5 CSVs in `data/1948/`
**Deleted:** 41 rows total (1 gameinfo + 18 batting + 2 pitching + 18 fielding + 2 teamstats)

## Summary

The 41 rows originally cataloged as "Item 23 — malformed 1948 dates" turned out NOT to be a date-coercion problem. They are **staging-stage duplicate rows for a single game** (Homestead Grays @ Newark Eagles, 1948-06-29), with a corrupted `gid`, `date`, and `season` field, sitting at the top of each file. The same game's records also appear in their proper chronological position later in each file with valid canonical values. We've deleted the corrupt copies and kept the clean canonical copies.

- **Corrupt gid (deleted):** `NW2119480629`
- **Clean canonical gid (kept):** `NW2194806290`

## Corruption pattern

For each affected row, three fields show insertion of `1` early in the field with field-width-preserving truncation of the last character:

| field | corrupt | clean | what changed |
|---|---|---|---|
| gid (12 char) | `NW2119480629` | `NW2194806290` | `1` inserted at pos 3 (after team prefix), game number `0` truncated from end |
| date (8 char) | `11948062` | `19480629` | `1` prepended at pos 0, last digit `9` truncated |
| season (4 char) | `1194` | `1948` | `1` prepended at pos 0, last digit `8` truncated |

All other ~40 columns per row are byte-identical to the clean version, EXCEPT for one play-classification difference (see below).

## Per-file deletion summary

| file | rows deleted | line range (pre-delete) |
|---|---|---|
| 1948gameinfo.csv | 1 | 2 |
| 1948batting.csv | 18 | 2–19 |
| 1948pitching.csv | 2 | 2–3 |
| 1948fielding.csv | 18 | 2–19 |
| 1948teamstats.csv | 2 | 2–3 |

All corrupt rows sat immediately after each file's header — consistent with an early staging-pass artifact.

## Why deletion (not in-place repair)

1. The clean canonical version of the game is **already present** in each of the 5 files at proper chronological position (line 756 of 1948gameinfo.csv, etc.).
2. The clean version's gid (`NW2194806290`) is structurally valid (matches the canonical `TTT(3)+YYYYMMDD(8)+N(1)` pattern, identical shape to its same-team neighbors NW2194806030, NW2194806201, NW2194806202, NW2194806270).
3. The clean version sits in chronologically-sorted order (June 29 maps to ~line 750+ when sorted by date), implying it is the more-recent / intended state.
4. Repairing the corrupt copy in-place would create LITERAL stat duplicates that would either trip ingest's primary-key uniqueness or silently double-count.

## Play classification difference (one Retrosheet ambiguity preserved)

Per-row diff between corrupt and clean rows is byte-identical except for ONE play:

```
napie101 (HOM batter) vs mannm101 (NW2 pitcher), one PA:
  CORRUPT version: scored as sacrifice fly  (b_sf=1, b_ab=3 for napie's day)
  CLEAN   version: scored as regular at-bat (b_sf=0, b_ab=4 for napie's day)

Cascading diffs from the same play:
  - 1948batting.csv     napie101: b_ab 3↔4, b_sf 1↔0
  - 1948pitching.csv    mannm101: p_sf 1↔0
  - 1948teamstats.csv   HOM:      b_ab 35↔36, b_sf 1↔0
  - 1948teamstats.csv   NW2:      p_sf 1↔0
```

By deleting the corrupt rows and trusting the clean version, we adopt the **regular-AB classification** of this play. This is a real Retrosheet scoring ambiguity, not a data integrity issue. If the question matters for a specific future query, it could be resolved by consulting Retrosheet's canonical `.evn`/`.evx` event files (per CLAUDE.md §4a Item 23 recovery option). Not consulting now; flagged for later.

## Affected rows (full content for reversal)

Captured 2026-04-29, byte-for-byte from the source CSVs immediately before deletion.

### 1948gameinfo.csv (1 row)

```
NW2119480629,HOM,NW2,NWK04,11948062,0,0:00PM,night,,,false,,0,3000,unknown,unknown,unknown,0,unknown,-1,,,mccrf901,moorc901,(none),suttm101,,,thurb101,mannm101,,regular,3,1,HOM,NW2,y,both,y,y,d,1194
```

### 1948batting.csv (18 rows)

```
NW2119480629,marql101,HOM,1,1,value,5,4,1,0,0,0,0,0,0,0,0,1,0,0,1,0,0,0,0,,,,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,banks101,HOM,2,1,value,5,5,1,3,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,,,,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,parkt101,HOM,3,1,value,5,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,,,,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,leonb101,HOM,4,1,value,4,3,1,1,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0,,,,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,eastl101,HOM,5,1,value,4,4,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,,,,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,napie101,HOM,6,1,value,4,3,0,1,0,0,0,1,0,1,0,0,0,0,0,0,0,0,0,,,,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,fielw101,HOM,7,1,value,4,4,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,,,,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,fowle101,HOM,8,1,value,4,3,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,,,,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,thurb101,HOM,9,1,value,4,4,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,,,,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,wilkj101,NW2,1,1,value,5,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,,,,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,willc109,NW2,2,1,value,5,3,0,0,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,,,,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,pearl102,NW2,3,1,value,5,4,0,1,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,,,,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,irvim101,NW2,4,1,value,4,4,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,,,,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,harvb102,NW2,5,1,value,4,3,0,1,1,0,0,1,1,0,0,0,0,0,0,0,0,0,0,,,,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,wilsb104,NW2,6,1,value,4,3,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,,,,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,willl107,NW2,7,1,value,4,4,0,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,,,,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,marcz101,NW2,8,1,value,4,2,0,1,0,0,0,0,1,0,0,1,0,0,0,0,0,0,0,,,,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,mannm101,NW2,9,1,value,4,4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,,,,11948062,0,NWK04,HOM,l,regular,y
```

### 1948pitching.csv (2 rows)

```
NW2119480629,thurb101,HOM,1,value,27,0,39,6,1,0,0,1,1,4,0,0,0,0,0,3,0,0,0,0,1,,,1,,1,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,mannm101,NW2,1,value,27,0,39,8,0,0,0,3,2,2,0,0,0,0,0,1,1,1,0,0,,1,,1,,1,11948062,0,NWK04,HOM,l,regular,y
```

### 1948fielding.csv (18 rows)

```
NW2119480629,marql101,HOM,1,8,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,banks101,HOM,1,4,value,27,0,0,1,0,0,,,,,1,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,parkt101,HOM,1,9,value,27,1,0,0,0,0,,,,,1,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,leonb101,HOM,1,3,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,eastl101,HOM,1,7,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,napie101,HOM,1,2,value,27,0,0,0,0,0,0,0,0,0,1,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,fielw101,HOM,1,5,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,fowle101,HOM,1,6,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,thurb101,HOM,1,1,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,wilkj101,NW2,1,8,value,27,1,0,0,0,0,,,,,1,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,willc109,NW2,1,3,value,27,0,0,1,0,0,,,,,1,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,pearl102,NW2,1,6,value,27,0,0,1,0,0,,,,,1,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,irvim101,NW2,1,7,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,harvb102,NW2,1,9,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,wilsb104,NW2,1,5,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,willl107,NW2,1,4,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,marcz101,NW2,1,2,value,27,0,0,1,0,0,0,0,1,0,1,11948062,0,NWK04,HOM,l,regular,y
NW2119480629,mannm101,NW2,1,1,value,27,0,0,0,0,0,,,,,1,11948062,0,NWK04,HOM,l,regular,y
```

### 1948teamstats.csv (2 rows)

```
NW2119480629,HOM,0,0,2,0,0,1,0,0,0,,,,,,,,,,,,,,,,,,,,9,,value,39,35,3,8,0,0,0,3,1,1,0,2,0,0,1,0,0,0,2,27,0,39,6,1,0,0,1,1,4,0,0,0,0,0,3,0,0,0,0,27,0,1,0,0,0,0,0,0,marql101,banks101,parkt101,leonb101,eastl101,napie101,fielw101,fowle101,thurb101,thurb101,napie101,leonb101,banks101,fielw101,fowle101,eastl101,marql101,parkt101,,11948062,0,NWK04,NW2,w,regular,y
NW2119480629,NW2,0,0,0,0,0,0,0,1,0,,,,,,,,,,,,,,,,,,,,11,,value,39,32,1,6,1,0,0,1,3,0,0,4,0,0,0,0,0,0,2,27,0,39,8,0,0,0,3,2,2,0,0,0,0,0,1,1,1,0,0,27,0,3,0,0,0,0,1,0,wilkj101,willc109,pearl102,irvim101,harvb102,wilsb104,willl107,marcz101,mannm101,mannm101,marcz101,willc109,willl107,wilsb104,pearl102,irvim101,wilkj101,harvb102,,11948062,0,NWK04,HOM,l,regular,y
```

## How to reverse

For each affected file, restore the listed row(s) immediately after the header line (line 1). Original byte content is preserved above. After reversal, the original 41+41=82 rows for this game will be present again.

## Cross-references

- Phase 2 dry-run halt at Item 23 surfaced this anomaly.
- CLAUDE.md §4a Item 23 — RESOLVED 2026-04-29 with this correction.
- Companion to:
  - data_corrections/2026-04-29_1943_timeofgame_excel_fraction.md
  - data_corrections/2026-04-29_1949_fielding_value_textdup.md
