# Phase 2 Smoke Test Plan — `ingest_full.py`

**Authoritative checklist for the Phase 2 ingest smoke test.** Mirrors and expands `phase2_step3_design.md` §10 Q5. Promoted to a durable artifact 2026-04-27 after the `C9a/C9b` step IDs were lost in chat-only state — see CLAUDE.md §5 working convention ("CLAUDE.md only captures claims this session can verify").

**Target environment (all steps):**
- Database: `baseball_oracle_scratch` (NOT `baseball_oracle`)
- Data root: `C:\BaseballOracle\scratch_data` (1925/, 1955/, 1985/ + cross-year reference CSVs)
- Script: `C:\BaseballOracle\ingest\ingest_full.py` invoked via `C:\BaseballOracle\.venv\Scripts\python.exe`
- Checkpoint: `ingest/.ingest_progress.json`
- Log: `ingest/.ingest_progress.log`

**Status legend:** ✅ complete · 🔄 pending · ❌ failed (with notes)

---

## A. Scratch setup — ✅ complete

- A1. Scratch DB `baseball_oracle_scratch` created.
- A2. `scratch_data/` populated with 1925/, 1955/, 1985/ year folders + cross-year reference CSVs (teams, ballparks, biofile0, relatives).
- A3. `retro` schema applied to scratch DB from `schema/schema.sql`.

## B. Happy-path year loads — ✅ complete

Each loaded via `--year-only`. Reference tables loaded once (during the first year run), then skipped on subsequent runs per §9 design.

- B4. 1925 loaded — 4.3s, 171,517 rows, 0 missing columns.
- B5. 1955 loaded — 3.6s, 169,632 rows, 0 missing columns.
- B6. 1985 loaded — 6.6s, 296,578 rows, 0 missing columns.
- B7. Reference tables: teams=274, ballparks=629, players=26,223, relatives=1,256.

## C. Resume + verify mechanics

- **C8** — ✅ complete. `--year-only 1955 --yes` re-run against an already-loaded year. Confirmed idempotent delete-and-reload path: existing 1955 rows deleted, year re-loaded, checkpoint `per_year` entry updated in place. Log line: `Deleted existing rows for year 1955 from all year tables.`

- **C9a** — ✅ complete (2026-04-27). `--verify-existing --year-only 1985 --yes`. All 7 year-bearing tables verified: `ok: retro.plays=369,443`, `teamstats=10,755`, `fielding=107,740`, `pitching=23,088`, `batting=119,252`, `players_team_year=2,805`, `games=4,644` — exact match to checkpoint `row_counts_cumulative`. Proceeded into idempotent 1985 reload (296,578 rows in 8.9s). Exit 0. Incidental note: the `Verifying loaded years against checkpoint�` log line confirms the em-dash mojibake tracked under E13.

- **C9b** — ✅ complete (2026-04-27). `--year-only 1986 --yes`. Pre-flight logged `Year folders in [1986, 1986]: 0 present, 1 missing` and `WARNING Missing year folders: [1986]`. Then `WARNING [1986] year folder missing; skipping.` — no DELETE, no load attempt. Checkpoint `skipped_years` now contains `{"year": 1986, "reason": "year folder missing"}`. `last_completed_year` correctly stayed at 1985 (skipped year does not advance the cursor). Cumulative row counts unchanged: plays=369,443, teamstats=10,755, fielding=107,740, pitching=23,088, batting=119,252, players_team_year=2,805, games=4,644 — identical to post-C8 / post-C9a state. Exit 0.

## D. Corruption tests

Both run **only against `scratch_data`**, never against `C:\BaseballOracle\data`. Each test corrupts a CSV header by renaming a single column, runs the ingest, verifies the expected outcome, then restores the original header.

- **D10** — ✅ complete (2026-04-27). **NOT NULL halt path.** Test corrupted `gid` → `xgid` header in `scratch_data/1955/1955gameinfo.csv`, ran `--year-only 1955 --yes`. Halt detection worked correctly on the first attempt (RuntimeError raised, `.ingest_halt_reason.txt` written, exit 1). However, the **rollback** did NOT work as designed — the test surfaced a real bug:
  - **Bug.** The pre-fix re-load path used three separate transaction boundaries: `delete_year_rows` opened+committed its own txn, `checkpoint.remove_year` wrote to disk, then `load_year` opened a fresh txn for the load. A halt during load only rolled back the load txn — leaving the DELETE durable in the DB and the checkpoint already mutated.
  - **Fix.** Restructured to put DELETE + LOAD inside a single `conn.transaction()` owned by `load_year` (new `replace_existing` parameter; renamed helper `_delete_year_rows_in_txn` runs inside caller's txn). Replaced `Checkpoint.record_year` + `remove_year` with a single atomic `Checkpoint.upsert_year` called only after the per-year DB transaction commits. `main()` simplified to compute `is_replace = year in already_done` and pass it through; `--year-only` idempotency block reduced to a confirmation prompt.
  - **Re-verification.** With the fixed script, D10 re-run: halt fired identically (same error path); DB scratch counts for 1955 unchanged at games=1243, plays=97909 (rollback unwound the DELETE); checkpoint per_year[1955] run_id and row_counts intact; cumulative counts unchanged. `partial_state: rolled back` in halt-reason is now truthful.
  - **Visible structural signature.** "Deleted existing rows for year 1955..." log line moved from before the `YEAR 1955` banner to after it — confirms the DELETE now runs inside `load_year`'s transaction.
  - Restored: CSV header renamed back to `gid`, SHA256 verified.

- **D11** — ✅ complete (2026-04-27). **Lenient NULL-fill path.** Test corrupted `temp` → `xtemp` header in `scratch_data/1955/1955gameinfo.csv` (nullable SMALLINT column per schema.sql:219). Ran `--year-only 1955 --yes` against the (post-D10-fix) script.
  - Lenient behavior verified end-to-end:
    - Exit 0; load completed cleanly (1243+741+31698+6304+28739+2998+97909 = 169,632 rows).
    - Stdout: `[retro.games] NULL-filling missing columns: ['temp']` AND `[retro.games] silently skipping unexpected CSV columns: ['xtemp']` (companion line from the rename — the CSV's `xtemp` column is unknown to the spec and silently skipped).
    - `.missing_columns.log` gained two entries: `missing=[temp]` and `unexpected=[xtemp]`. (The unexpected side does NOT propagate to the checkpoint — by design.)
    - Checkpoint `per_year[1955].missing_columns = [{"table": "retro.games", "columns": ["temp"]}]`.
    - End-of-run summary's "missing CSV columns (rolled up):" section reported `retro.games.temp: [1955]` — bonus signal that the per-table-per-column rollup works.
  - DB NULL-fill verified: `temp IS NULL` flipped from 0 (pre-test) to 1,243 (post-corruption) for 1955 games; `temp IS NOT NULL` flipped from 1,243 to 0. Row counts intact at games=1243, plays=97909.
  - Re-loaded with restored CSV (replace_existing=True path, exercising the D10 fix on the happy path): clean run, no NULL-fill log lines, no missing-columns summary section. Post-restore temp distribution `temp_null=0  temp_notnull=1243  temp_zero=1180  temp_distinct_nonzero=32` — exact match to pre-test baseline.
  - Restored: CSV SHA256 verified back to `8B957F…2137A`.
  - Side note: D11 also functioned as the happy-path verification of the D10 structural fix. Two consecutive `replace_existing=True` re-loads of 1955 (one with NULL-fill, one clean) both succeeded with DELETE inside the YEAR transaction.

## E. Cleanup

- E12. Scratch DB and `scratch_data/` persist between sessions for re-testing — do not drop or delete.
- E13. Em-dash log encoding fix — separate small task, tracked outside this checklist.

---

## Open questions / parking lot

- D11 column choice: which year and which nullable column should we corrupt? Decide before executing D11.
- C9b confirmed `--year-only 1986` short-circuits to the missing-folder branch without touching reference tables. (Resolved during execution.)

## Cleanup follow-ups (separate from smoke-test, tracked here for visibility)

These are minor / low-priority items surfaced during smoke testing. None block phase progression.

- ✅ (2026-04-27) Add `--database` CLI flag so `PG_DATABASE` isn't shell-state-dependent. Default None; falls back to env var → .env. Override is conditional and self-documenting on the CLI.
- ✅ (2026-04-27) Add startup log lines `Connecting to database: <db> on <host>:<port>` (pre-connect, fires even on connect failure) and `Connected to database: <db>` (post-connect).
- 🔄 deferred. Em-dash → `--` (or similar) in log strings to fix PowerShell stdout rendering. UTF-8 file write is unaffected.
- 🔄 deferred. Pass `stage` and `csv` as structured fields to the halt-reason writer (currently `(n/a)` even though both are known at the raise site).
- 🔄 deferred. Logging clarification in `_delete_year_rows_in_txn`: log DELETE after commit, not before, so the message is truthful regardless of outcome.
- 🔄 deferred. Unify `skipped_years` cleanup with successful load completion (currently `--year-only Y` for a previously-skipped year leaves a stale `skipped_years` entry in place).

---

## Phase 2 readiness status (as of 2026-04-29)

**All known Layer 3 data quality issues RESOLVED.** Sentinel scan reports **0 halt-prone values across the entire 1901–2023 corpus** (859 files scanned, 833s duration, 2026-04-29 run). Ready for end-to-end dry-run + real ingest.

### Layer 3 resolution summary

All four items resolved through a mix of schema migrations (Items 22, 25), source-data corrections (Items 1, 2, 3, 4), and pattern decomposition (Item 24's original "~16 misalignment-suspect" rows split into 4 distinct sub-patterns). Per-item details:

| Item | Originally cataloged as | Actual resolution | Rows touched | Logged at |
|---|---|---|---|---|
| 22 | 13 hedged attendance values | `retro.games.attendance` BOOLEAN → VARCHAR(24) | 0 (schema only) | `schema/migrations/2026-04-28_attendance_varchar.sql` |
| 25 | (new) `forfeit` codes overloaded onto bool | `retro.games.forfeit` BOOLEAN → VARCHAR(2) | 0 (schema only) | `schema/migrations/2026-04-29_forfeit_varchar.sql` |
| 24(a) | 1 timeofgame Excel-fraction | Source-data fix `0.0590277777777778` → `85` | 1 | `data_corrections/2026-04-29_1943_timeofgame_excel_fraction.md` |
| 24(b) | 7 fielding `'value'` text-duplications | Source-data fix d_seq → NULL | 7 | `data_corrections/2026-04-29_1949_fielding_value_textdup.md` |
| 23 | 41 "malformed 1948 dates" | Were staging-stage duplicates of clean rows; deleted | 41 | `data_corrections/2026-04-29_1948_NW2_staging_duplicate_deletion.md` |
| 24(c) | 8 teamstats lob `'n'`/`'No'` markers | Source-data fix lob → NULL | 8 | `data_corrections/2026-04-29_1948_teamstats_lob_textual_null_markers.md` |

### Cumulative code + schema changes (across 2026-04-27, 2026-04-28, 2026-04-29)

- **`ingest_full.py`:** `_is_null_sentinel` helper handles `{'?', 'x', 'X', 'unknown'}`; `spec_games` int_cols/bool_cols updated to drop `attendance` and `forfeit` (now VARCHAR), keep `tiebreaker` as int. `EXPECTED_SCHEMA_VERSION` + `SCRIPT_VERSION` at `2026-04-29`. CLI flag `--database` + connection log lines landed.
- **Schema:** Both `baseball_oracle` and `baseball_oracle_scratch` at `phase2-2026-04-29`. Migration files in `schema/migrations/` (5 files: original phase2 widening, schema_version table, tiebreaker SMALLINT, attendance VARCHAR(24), forfeit VARCHAR(2)). `schema/schema.sql` and `schema/schema_for_scratch.sql` reflect the cumulative current state.
- **CLAUDE.md:** §3 now includes a schema-versioning convention note. §4 items 18–21 (data quirks). §4a items 22–25 with full RESOLVED-state documentation. §5 added the "source-data corrections are an exception" working convention. §9.4 era-aware response calibration. §10 future architecture considerations (Retrosheet event-file migration registered).
- **Source-data corrections (`data_corrections/`):** 4 markdown logs covering 57 row-edits/deletions across 4 distinct corruption sub-patterns.

### Verification done

- **Sentinel scan**: 8,779 halt-prone values pre-Layer-1+2-fix → 72 post-Layer-1+2-fix → 0 post-Layer-3-fix. Confirmed by full corpus scan 2026-04-29.
- **Decimal-fraction scan** (`ingest/phase2_decimal_fraction_scan.py`): 0 hits across all 5 spec functions' int_cols.
- **Boolean audit** (`ingest/phase2_boolean_audit.py`): 0 halt-prone, 0 suspect across all 13 bool_cols.
- **Full end-to-end dry-run** (2026-04-29): **PASSED.** Total runtime 9.0 min. 117 years processed (1907–2023). 6 years soft-skipped (1901–1906, missing plays.csv). Zero halts, zero errors. Cumulative row counts:
  - retro.games: 209,311
  - retro.players_team_year: 123,607
  - retro.batting: 5,396,575
  - retro.pitching: 1,199,416
  - retro.fielding: 4,933,199
  - retro.teamstats: 465,024
  - retro.plays: 15,836,683
  - **Total: ~28.2M data rows + 28,382 reference rows**
  - Missing-column rollup: `retro.plays.hittype` absent in 1907–1911 (handled by lenient NULL-fill policy).

### State for next session

- **DB state:** `baseball_oracle` unchanged from Phase 1 (1998 only). `baseball_oracle_scratch` retains smoke-test years (1925, 1955, 1985) at `phase2-2026-04-29`.
- **Checkpoints:**
  - `ingest/.ingest_progress.json.dryrun` — preserves 1907–1937 validation; will need `--force-restart` to re-run from scratch under the new schema_version.
  - `ingest/.ingest_progress.json` (real-run) — stale; will be cleared by `--force-restart` at real ingest time.
- **Code:** `ingest_full.py`, `phase2_sentinel_scan.py`, `phase2_boolean_audit.py`, `phase2_decimal_fraction_scan.py` all py_compile-clean.
- **Halt artifacts:** `ingest/.ingest_halt_reason.txt` records prior halts; will be overwritten or cleared by next dry-run.

### Next steps

1. **End-to-end dry-run** with `--force-restart`. Expected: clean across 123 years (1907–2023; 1901–1906 soft-skip per missing `plays.csv`). Estimated runtime: 30–60 min based on prior partial-run scaling.
2. **If dry-run halts on a previously-uncatalogued issue**: investigate-and-fix per the Layer 3 pattern (boolean audit + decimal-fraction scan demonstrated that "expected next halt" can be wrong — actual halts may surface new sub-patterns).
3. **If dry-run completes clean**: `--force-restart` real ingest against `baseball_oracle`. Background, with periodic check-ins. Estimated runtime: ~6–12 hours based on smoke-test per-year timings × 117 years.
4. **Post-ingest verification**: Layer 1/2/3 verification queries per `ingest/phase2_plan.md` §5.

---

## Phase 2 verification complete (2026-04-29)

**All three post-load verification layers passed.** Phase 2 data layer (28.16M data rows + 28,382 reference rows, 1907-2023) is fully verified. One source-data anomaly surfaced and was resolved end-to-end during Layer 1 — see CLAUDE.md §4a Item 29 (`PH5193704130` gid typo).

### Per-layer summary

| Layer | Checks | Result |
|---|---|---|
| Layer 1 — Internal integrity | 7 (row counts, date ranges, stattype distribution, team-code orphans, player-ID orphans, games↔teamstats symmetry, PK uniqueness) | ✅ all clean (1 anomaly resolved: Item 29) |
| Layer 2 — External cross-checks | 5 (games per year, career HR Ruth/Aaron/Bonds, season HR Maris/McGwire/Bonds, Ichiro 2004 hits, 4 landmark games) | ✅ every numeric target matched exactly |
| Layer 3 — Phase 1 reproducibility | 5 (re-run of Phase 1 Q1-Q5 against full corpus) | ✅ identical results across all 5 |

Layer 1 anchor numbers: DB grand totals match `.ingest_progress.json` checkpoint exactly across all 7 year tables and 4 reference tables. 117 expected years all present, 0 cross-table date mismatches across 28M+ rows. Modern-era (≥1960) team-code and player-ID orphan counts both 0. All 7 PK constraints declared and satisfied.

Layer 2 anchor numbers: Ruth=714, Aaron=755, Bonds=762 career HR (cross-aggregated via two paths). Maris 1961=61, McGwire 1998=70, Bonds 2001=73 season HR. Ichiro 2004=262 hits (.372 BA via plays cross-check). Landmark games: 1923 Yankee Stadium opener NYA 4 BOS 1 with Ruth 3-run HR off Ehmke; 1956 Larsen 27-up-27-down with 0 H / 0 BB / 7 K CG; 1974 Aaron 715 off Downing in 4th; 2001 WS G7 Gonzalez walk-off vs Rivera with full 6-play bottom-9th sequence reconstructed.

### Verification artifacts

All queries are durable, in `scratch/`, paired with captured `.out` files. **Reusable for any future Retrosheet refresh or re-ingest** — the same files re-run against a refreshed DB to confirm structural integrity, statistical canon, and Phase 1 baseline reproduction without re-deriving the queries.

- **Layer 1 (7 files):** `l1_01_row_counts.sql`, `l1_02_date_ranges.sql`, `l1_03_stattype_distribution.sql`, `l1_04_team_orphans.sql`, `l1_05_player_orphans.sql`, `l1_06_games_teamstats_symmetry.sql`, `l1_07_pk_uniqueness.sql`
- **Layer 2 (5 files):** `l2_01_games_per_year.sql`, `l2_02_career_hr.sql`, `l2_03_single_season_hr.sql`, `l2_04_ichiro_hits.sql`, `l2_05_landmark_games.sql`
- **Layer 3 (5 queries):** `l3_05_jeter_may_1998.sql` (new); plus the existing Phase 1 `q02_mcgwire_hr_chase.sql`, `q03_lhb_vs_lhp_1998.sql`, `q04_cycles_1998.sql`, `q05_yankees_close_vs_blowouts.sql` (run as L3.1-L3.4 with output captured as `l3_01_mcgwire.out` etc.)

**Total: 17 verification queries + paired output captures.**

### Status

Phase 2 is closed. Phase 3 (agent layer) is the next major arc.

---

*Update this file inline as steps progress. Do not let step state drift back into chat-only memory.*
