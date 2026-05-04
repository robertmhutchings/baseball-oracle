# Phase 2 Ingest Plan — Full 1901–2023 Load

**Status:** Draft. Review before any code is written.
**Supersedes:** `ingest_1998.py` (Phase 1, 1998-only).
**Author context:** Produced 2026-04-24 after completing all five initial Phase 1 benchmark queries with verified results.

---

## 0. Context and goals

Phase 1 proved the schema and pipeline against a single modern season (1998 = 200K plays, clean data). Phase 2 scales to **all 123 years 1901–2023**, approximately **20–25M plays** plus proportional growth in `teamstats`, `batting`, `pitching`, `fielding`, `games`.

Goals in priority order:

1. **Correctness.** Data drift or transform errors that silently corrupt rows are worse than outright failures. When in doubt, fail loud.
2. **Resumability.** A multi-hour load that cannot resume from a mid-stream failure will cause real time loss during iteration. The Phase 1 single-transaction model does not scale to Phase 2.
3. **Observability.** Without a progress feed, "is it working or stuck?" becomes unanswerable during the load. Logging is load-bearing, not nice-to-have.
4. **Performance.** Target completion in a single session (< 6 hours). Cutting that further is nice but not a priority.

Non-goals for Phase 2: query performance tuning beyond minimal indexes, agent/NL work (Phase 3), UI (Phase 4).

---

## 1. Year-folder iteration

### What needs to change in the existing script

Three hardcodes:
- `YEAR_DIR = DATA_ROOT / "1998"`
- `TARGET_YEAR = 1998`
- CSV filenames like `"1998gameinfo.csv"` embedded in each per-year `spec_*()` function

Refactor so per-year spec functions take a `year` argument and compute the filenames from it.

### Structural change

- **Stage 1 (reference tables) stays as-is** — teams, ballparks, players, relatives load once from top-level `data/*.csv` files. These are cross-year reference data; no loop needed.
- **Stages 2–4 wrap in an outer year loop** iterating `range(1901, 2024)`.

### Handling missing years

Before the loop, glob `data/` to inventory which year folders actually exist. Compare to the expected 1901–2023 range and **report the diff up front** — Retrosheet has known gaps (Negro League years are patchy, some early-century seasons may be partial, Federal League 1914–15 may be treated specially).

Inside the loop, if a year folder is missing one of the 7 expected CSVs (`{year}gameinfo.csv`, `{year}allplayers.csv`, `{year}batting.csv`, `{year}pitching.csv`, `{year}fielding.csv`, `{year}teamstats.csv`, `{year}plays.csv`), **skip the year with a warning**, not a hard error. Skipping is recorded to the checkpoint file so we can audit post-load.

---

## 2. Data quirks we anticipate at scale

**Recommendation: a dry-run pass before the real load.** It is much cheaper to discover transform failures and width overflows in a read-only scan than to hit them at hour 2 of a 5-hour write.

### (a) `stattype` mixing — 'value' / 'official' / 'lower' / 'upper'

No ingest code change needed — `stattype` passes through as a plain string. Schema already accepts the four values without constraint.

**Post-load verification:** add a per-year `stattype` ratio check. Expect 'value' dominant everywhere, with non-'value' rows showing up pre-1920 and in Negro League years. Any year with >5% non-'value' deserves a spot-check to confirm it reflects genuine historical uncertainty, not an ingest artifact.

### (b) Partial dates (`'19130000'`-style)

- **`players` biographical fields** (`birthdate`, `deathdate`, `debut_*`, `last_*`): declared `VARCHAR(8)` in schema.sql; current `passthrough` transform already handles correctly. ✅
- **`games.date`** declared as `DATE`, transformed via `to_date_yyyymmdd` which raises on `'00'` month/day. Per CLAUDE.md §4 item 9, game-level dates should always be fully populated. **If this assumption is wrong for any old year the ingest halts.** Dry-run will catch it and we'll decide whether to relax the transform or file as a data issue.
- **`batting.date` / `pitching.date` / `fielding.date` / `teamstats.date`** — same `DATE` + `to_date_yyyymmdd` treatment, same assumption, same dry-run exposure.

### (c) Weather sentinels (`temp=0`, `windspeed=-1`) in older games

Pass through as integers. Schema accepts. Filtering at query time remains the consumer's responsibility (per CLAUDE.md §4 item 8). **No code change.**

### (d) Width overflows — hittype, loc, pitch_count, VARCHAR columns in `games`

Run `ingest/scan_widths.py` across all 123 years as part of the discovery pass. Expected hot spots based on known quirks:

- `plays.hittype` — currently `VARCHAR(4)`. Saw `BG`/`BP` in 1998. Earlier eras may have other combinations.
- `plays.pitch_count` — currently `VARCHAR(4)`. 1998 values were 2 chars (`"32"`, `"??"`). Retrosheet's documentation suggests the format is stable, but pre-1988 pitch-by-pitch data may be sparse or formatted differently.
- `plays.loc` — location codes may exceed 10 chars in old or unusual plays.
- `games` VARCHAR columns: `starttime`, `daynight`, `fieldcond`, `precip`, `sky`, `winddir`. Older CSVs may use longer text forms ("Partly Cloudy" vs "sunny").

Width findings → schema migration (widen columns) applied **before** the real load begins.

### (e) Column-set drift across decades (biggest risk)

**The current ingest errors if any expected CSV header is missing** — line 451 of `ingest_1998.py`:

```python
missing = expected_csv_headers - set(csv_headers)
if missing:
    raise RuntimeError(...)
```

Retrosheet CSV schemas have genuinely evolved. Early-era `plays.csv` may lack columns like `pitch_count`, `pitches`, pitch-sequence data, some fielder-position columns, or advanced hit classification. Halting on every missing column makes pre-1988 years un-ingestible.

**Recommendation: relax "missing header" from error to warning** and fill the missing column with NULL for every row of that year. This matches Retrosheet's own convention of omitting rather than blank-filling when a field doesn't apply to an era.

Caveats:
- Audit every schema column that is currently `NOT NULL` to confirm it truly must be populated. Any non-structural NOT NULLs may need relaxing. Initial schema uses NOT NULL only on natural-key columns, which should be safe.
- Per-year **report** of which expected columns were missing, logged to the checkpoint/progress file. This lets us audit after the load.

### (f) Boolean and enum drift

`to_bool` raises on unknown string values. Pre-modern CSVs may encode booleans with different conventions (e.g. `Y`/`N` vs `1`/`0` vs `true`/`false`). Dry-run will expose these; fix case-by-case.

### (g) Team/player/ballpark reference drift

Early-era team codes may not all appear in the cross-year `teams.csv`. Short-lived Federal League, early AL/NL franchises, and Negro League teams may surface `hometeam`/`visteam` values not in `teams.team`. We have no foreign key enforcement in the schema (per CLAUDE.md §3 design note 12), so orphans simply load — but the post-load integrity check will catch them (§5 below).

Similarly: `plays.batter`/`plays.pitcher` may reference player IDs not in `players.id` for older eras where Retrosheet has an event but not a bio record. Expect a small number; report and decide whether to ignore or backfill.

### (h) Unknowns

Anything else surfaces in the dry-run. Plan: for each new quirk, update CLAUDE.md §4 with a new data-quirk item (we're at #14 post-Phase-1; Phase 2 likely adds several more). This keeps the quirks list as the living authoritative guide for future query-writing.

---

## 3. Performance

### Baseline extrapolation

Phase 1: 1998 = 200K plays in ~90s = **2.2K plays/sec**.
Phase 2: 123 years × ~160K plays/year avg = ~20M plays.
Linear projection: **~2.5 hours just for `plays`**. Plus other tables: realistic total **3–5 hours**.

Too long to run in foreground. Operational setup must support backgrounding and checkpointing.

### Recommended configuration

- **Per-year transactions for stages 2–4.** Reference tables (stage 1) remain one upfront transaction — they're the foundation and must be all-or-nothing. Year-level commits isolate failures to one year and let us resume.
- **No indexes during load.** Schema currently has zero indexes (by design, per schema.sql note 12). Keep them off for COPY throughput. Add after load as a separate migration (§5 tail below).
- **Background execution.** Run the script with stdout redirected to a logfile, monitored via `tail -f`. Progress line per year-stage completion (e.g. `[1934] plays.csv: 142,550 rows, 64s, cumulative 3h 17m`).
- **Checkpoint file at `ingest/.ingest_progress.json`.** Updated after each successful year commit: `{last_completed_year, timestamp, row_counts_by_table, skipped_years}`. On restart, skip already-completed years.
- **Optional session-level Postgres tuning** via `SET` at connection start: `maintenance_work_mem = '1GB'`, `synchronous_commit = 'off'`. These are session-scoped, not persistent cluster changes. Modest ~10–15% speedup on multi-hour COPY jobs. Risk: `synchronous_commit=off` means a crash mid-commit may lose the most recent year; re-runnable via checkpoint. Acceptable trade.

### What we're NOT doing

- **Parallelizing by year** — tempting but risky with a single Postgres instance (lock contention, connection overhead). Not worth the complexity.
- **Disabling fsync cluster-wide** — affects all databases and persists until reset. Out of proportion to the problem.
- **Rewriting COPY with a different driver** — `psycopg` COPY is already near bandwidth-bound; further gains need infra changes.

---

## 4. Risk mitigation

### Transaction strategy

Previous Phase 1 model: single transaction wrapping the entire load. Any failure → total rollback → DB empty → redo everything.

Phase 2 model:
- **Stage 1 (reference tables)**: one transaction, all-or-nothing. Foundation must be coherent.
- **Stages 2–4 per year**: one transaction per year. Success → commit + checkpoint. Failure → rollback that year only, prior years intact, halt with diagnostic output.

Rationale: the "Willie Davis fractional weight" kind of surprise is essentially guaranteed at this scale. Localizing the blast radius to one year means we fix forward instead of starting over.

### Per-year failure response

1. Ingest halts on first failure inside a year's transaction
2. Transaction rolls back → that year's rows are gone from stages 2–4
3. Script exits with clear output: year, stage, table, failing row, error
4. Human investigates (likely: new data quirk, schema too narrow, transform too strict)
5. Fix (widen column, relax transform, etc.) — updating CLAUDE.md if durable
6. Restart script; it reads the checkpoint and resumes from the failed year

### What should NOT trigger halt

- Missing CSV for a year → skip the year, log, continue (Retrosheet gaps)
- Missing CSV column within a file → NULL-fill, log, continue (era drift)
- Per-row transform error → **halt** (don't silently drop rows — CLAUDE.md §5 "do not patch data silently")

### Checkpoint reliability

The checkpoint file must be written **after** the per-year transaction commits, not before. Otherwise a mid-commit crash could mark a year complete that isn't actually in the DB.

---

## 5. Verification

Three layers, following CLAUDE.md §7 Data Source Principle: internal checks are mandatory; external cross-checks are appropriate **dev-time pipeline validation** (not user-facing answers).

### Layer 1 — Internal integrity (Retrosheet only)

- **Row counts per year per table.** Produce a table with columns `year, games, teamstats, batting, pitching, fielding, plays` and sort by year. Expected shape: dead-ball-era smaller counts, modern era larger. Any year with zero rows in a populated table is a red flag.
- **Date range per partitioned table.** `SELECT year, MIN(date), MAX(date)` — should match the year folder.
- **`stattype` distribution per year.** Mostly `'value'`; non-'value' rows cluster in pre-1920 / Negro League years.
- **Team-code orphans.** `SELECT DISTINCT hometeam FROM games EXCEPT SELECT team FROM teams` — expect small or zero.
- **Player-ID orphans in plays.** Sample `plays.batter`/`plays.pitcher` values not in `players.id` — expect small or zero.
- **`games` ↔ `teamstats` consistency.** Every `games.gid` should have exactly 2 rows in `teamstats` (per CLAUDE.md §4 item 6). Any deviation is a data or ingest issue.

### Layer 2 — External cross-checks (dev-time validation per §7)

These are the user-requested cross-checks. Each is a one-shot query run against the loaded DB, compared to a published number.

- **Games per year totals.** Reference table of expected per-year MLB game totals from public record. Known expected values:
  - 1901–1903: 140 games per AL team, 140 per NL team (early era varies)
  - 1904–1961: 154-game schedule (AL); 154 NL
  - 1962–present: 162-game schedule, with documented exceptions:
    - 1972: strike-shortened (most teams played 153–156)
    - 1981: split-season strike (~105 games)
    - 1994: strike wiped out most of August + all of September (~112 games)
    - 1995: shortened to 144 (delayed start)
    - 2020: COVID-shortened to 60
  - Expansion years: 1961 AL added 2 teams, 1962 NL added 2 teams, 1969 both leagues added 2 each, 1977 AL added 2, 1993 NL added 2, 1998 both added 1
  - Query: `SELECT EXTRACT(year FROM date) AS yr, COUNT(DISTINCT gid) FROM games GROUP BY yr ORDER BY yr`. Cross-reference the count against expected. Any year off by more than 1–2 games is a red flag.

- **Known-player career HR totals.** Stresses cross-year player-ID stability — a player's `retroID` must be the same across all years they played. Test cases:
  - Babe Ruth (`ruthb101`): career HR = 714 (published). Career span: 1914–1935.
  - Hank Aaron (`aaroh101`): career HR = 755.
  - Barry Bonds (`bondb001`): career HR = 762.
  - Query: `SELECT SUM(p.hr) FROM retro.plays p JOIN retro.players pl ON p.batter = pl.id WHERE pl.usename = ? AND pl.lastname = ?` — filtering to regular-season and stattype='value' as applicable.
  - Any mismatch > 2 HR suggests either (a) a player-ID break across years, (b) a stattype or gametype classification issue, or (c) Retrosheet's count differs from published canon (occasionally happens in very old games due to scoring reclassifications — see CLAUDE.md §7 note about external sources having different rules).

- **Single-season record years.** Same approach, different scope.
  - Maris 1961: 61 HR
  - McGwire 1998: 70 HR (already verified in Phase 1 Query #2)
  - Bonds 2001: 73 HR
  - Ichiro 2004: 262 hits
  - Any off by more than 1 is investigate-worthy.

- **Landmark games spot-check.** Pull full box-score reconstructions from plays for 3–4 historically significant games spanning eras:
  - 1923-04-18 Yankee Stadium opener (Ruth's 3-run HR)
  - 1956-10-08 Larsen perfect game (27 up, 27 down, World Series Game 5)
  - 1974-04-08 Aaron's 715th HR (breaks Ruth's record)
  - 2001-11-04 Luis Gonzalez walk-off (World Series Game 7)
  - For each: confirm attendance (where recorded), final score, key stats. Cross-check against Baseball-Reference game page. Era-spanning coverage stresses different schema aspects.

### Layer 3 — User-facing dry-run

After the full load and index build:

- Re-run Phase 1 Queries #1–#5 filtered to 1998. **All five verified results must reproduce exactly.** If any drift, something about the 1998 ingest changed under us and we investigate before proceeding.

---

## 6. Proposed sequencing

Each step is a separate conversation / approval gate. No DB writes happen until step 4.

1. **Discovery pass (read-only).**
   - Glob `data/` to inventory year folders vs. expected 1901–2023 range
   - Run `scan_widths.py` across all 123 years; report any VARCHAR/CHAR overflows
   - Sample CSV header sets across eras (e.g., 1905, 1925, 1945, 1975, 2005, 2022) and diff against the 1998 baseline
   - Report: missing years, width findings, header drift, any other surprises
2. **Schema migration.** Widen overflowing columns. Review-and-approve SQL before applying. One transaction.
3. **Ingest refactor.** Parameterize year; add the outer loop; add per-year commit; add checkpoint file; add progress logging; add `--check` dry-run flag (transforms but does not write).
4. **Dry-run across all 123 years.** No writes. Surfaces per-year transform failures and missing-column patterns. Fix each before proceeding.
5. **Real full load.** Run in background. Monitor progress output. Expected runtime: 3–5 hours.
6. **Post-load verification.** Layers 1, 2, 3 above. ✅ Complete 2026-04-29 — see `scratch/l1_*.sql`, `l2_*.sql`, `l3_*.sql` (17 queries + `.out` captures); full status in `ingest/phase2_smoke_test_plan.md` "Phase 2 verification complete" section.
7. **Index build.** Separate migration script. Priority indexes: `games(date, season)`, `games(hometeam)`, `games(visteam)`, `plays(batter)`, `plays(pitcher)`, `batting(gid, id)`, `pitching(gid, id)`, `teamstats(gid, team)`. Refine based on observed query patterns from Queries #6 onward.
8. **CLAUDE.md update.** New data quirks discovered at scale; ingest-script convention changes; updated Phase status.

---

## 7. Resolved decisions

The questions raised here have been answered through the Phase 2 Step 3 design review (see `ingest/phase2_step3_design.md` for full context). Summary:

- **Missing-column policy.** Lenient. Missing CSV columns NULL-fill and log to `ingest/.missing_columns.log`. Codified in design sketch §8.
- **synchronous_commit=off during load.** Yes, applied as a session-level SET. Escape hatch via `--no-pg-tuning` flag if it surfaces problems. Design sketch §2.
- **Scope of post-load cross-checks.** Approved as proposed in §5 layer 2 above (Ruth/Aaron/Bonds career HR, Maris '61, McGwire '98, Bonds '01, Ichiro '04 hits; landmark games: 1923 Yankee Stadium opener, 1956 Larsen perfect game, 1974 Aaron's 715th, 2001 WS Game 7).
- **Who runs the ingest.** Claude Code background bash for both dry-run and real run. Checkpoint + progress log are session-independent, so a new Claude Code session can re-attach by reading the files.
- **Rollback plan.** Deferred to post-load. Decision will depend on the nature of the issue (systemic vs isolated). Per-year transactions + checkpoint mean re-running a single year is cheap; truncate-and-retry vs patch-forward will be chosen when we know the failure mode.

---

*Phase 2 closed 2026-04-29. Steps 1-6 complete (discovery, schema migration, ingest refactor, dry-run, real load, post-load verification). Steps 7 (index build) and 8 (CLAUDE.md update of new quirks) deferred to as-needed. Phase 3 (agent layer) is the next major arc.*
