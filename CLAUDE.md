# Baseball Oracle — Project Context

## Current Status (session paused)

**Phases complete:** 1, 2, 3A, 3B, 3C (Layers 1, 2, 4), 3D Step 1
**Phases deferred:** 3C Layer 3 (streaming), 3E (quality polish)
**Last commits:**
- ae2517b — CLAUDE.md cleanup (1907-2023 corpus consistency)
- a443001 — Phase 3C Layer 4 (trace visibility UI)
- (uncommitted, to be committed in this session) MAX_AGENT_TURNS = 30, was 20

**Tier 2 verified active:** 450k input tokens/min, 1k req/min, 90k output/min for Sonnet.

### Quality Investigation Findings (May 2026)

Through extended testing of hard interpretive questions, identified persistent quality issues that the current architecture does not solve:

**Confirmed pattern: question drift / scope substitution.**
Agent answers a tangentially related question rather than the one asked. Not flagged. Example: "by age X, who had most rings?" interpreted as "at age X, who won AND has lifetime career most?" Documented in LEARNINGS Entry 21.

**Confirmed pattern: confabulation in prose.**
Agent generates plausible-sounding reasoning that isn't actually correct. Example: "extremely rare given birth dates" — confabulated explanation for a result the agent itself misinterpreted. Documented in LEARNINGS Entry 22.

**Confirmed pattern: data inflation in counts.**
Hard questions sometimes return numbers that don't match real-world values (Yogi shows 13 rings, real is 10). Diagnosis incomplete; possibly duplicate counting in joins or off-by-one in age calculation. Worth investigating if project resumes.

**Confirmed pattern: budget changes improve completion, not quality.**
Tier 2 + MAX_TURNS=30 lets more questions finish. Doesn't improve answer correctness on those that do finish. Documented in LEARNINGS Entry 24.

### Architectural Walls Found

These are limits the current architecture can't reliably get past:

1. **NL → SQL question-understanding ambiguity.** Agent decomposes complex questions into queries that often miss the actual intent. No reliable prompt fix.

2. **Confidence-correctness disconnect.** Agent expresses high confidence regardless of answer quality. Affects user trust in unverified outputs.

3. **Non-determinism in exploration.** Same question produces different tool-call sequences across runs. Quality varies with random initial query choice.

4. **Single-pass synthesis without question verification.** Agent computes, then narrates, with no checkpoint to ask "is this what was asked?"

### Architectural Ceilings (Higher with Different Approach)

These could potentially be raised with fundamental architecture changes (not pursued):

1. Multi-call research mode (decompose hard questions into sub-questions, run separately, synthesize)
2. Pre-computed materialized views for common question patterns (cumulative stats, by-age progressions, etc.)
3. Question-confirmation workflow (agent restates interpretation, asks user to confirm before computing)
4. Cross-run verification (run same question multiple times, compare, flag discrepancies)
5. Sub-agent dispatching (specialized agents for different question types)

### Project Decision Point

Project is paused for evaluation as of 2026-05-09. Decision pending:
- Continue and explore one or more ceiling-raising architectures (significant new build)
- Document and conclude (current state captures the learnings)
- Continue at current scope for narrower question types where current architecture works (medium and easy questions perform well)

---

## 1. Project overview

Baseball Oracle is a natural-language Q&A system for historical baseball statistics, sourced from Retrosheet's 1907–2023 play-by-play corpus. Phase 1 goal: load a single season (1998) into PostgreSQL, verify the schema and ingest pipeline end-to-end, and be able to answer 25 benchmark baseball questions via direct SQL. Current state: **Phase 2 complete — full 1907-2023 corpus loaded (28.16M data rows + 28,382 reference rows), verified end-to-end across structural integrity, external statistic cross-checks, and Phase 1 query reproduction.** There is **no agent/LLM pipeline yet** and **no UI yet** — SQL is run manually via psql.

> **Phase taxonomy:** Phase 1 = schema + 1998 data + SQL validation (current). Phase 2 = full 1907–2023 ingest. Phase 3 = agent layer (NL pipeline, clarification, response assembly, narrative enrichment). Phase 4 = hosting + public launch.

> **Phase 3 architecture:** documented in `phase3_architecture.md` at project root. Approved 2026-04-29; implementation work proceeds in 5 sub-phases (3A foundation through 3E quality iteration). All architecture decisions, reasoning, and the decision log are captured there.

> **Phase 3A progress:**
> - Step 1 complete 2026-04-30: read-only DB role + connection helper (`agent/db.py`).
> - Step 2 complete 2026-04-30: agent loop with `run_sql`, three Phase 1 questions verified.
> - Step 3 complete 2026-04-30: `lookup_player`, `lookup_team`, `ask_user` tools added; multi-turn conversation working.
> - Calibration items from Step 2/3 testing tracked in `PHASE3B_NOTES.md`.

> **Phase 3D progress (taken out of architecture-doc order — see deviation note below):**
> - Step 1 complete 2026-05-02: v1 eval framework operational (`eval/benchmarks.py`, `eval/checks.py`, `eval/runner.py`). 10 benchmark questions wired up (7 verifiable, 2 process_check, 1 unverifiable). Baseline run captured at `eval/results/2026-05-02_075131/` — 7 pass / 0 fail / 3 review_needed automated; manual review surfaced 3 prompt-calibration items + 3 framework improvements (`PHASE3B_NOTES.md` items 8-13).

> **Phase 3B progress (taken out of architecture-doc order — see deviation note below):**
> - Step 1 complete 2026-05-02: items 1, 8, 9 resolved via the new "## Trusting the data" section in `agent/prompts.py`. Verified across 5 eval runs at `eval/results/2026-05-02_*`.
> - Step 2 complete 2026-05-02: items 5, 7 resolved via column-qualification bullet and "## Dynamism — multi-interpretation when warranted" section. Verified at `eval/results/2026-05-02_090331/`.
> - Step 3 complete 2026-05-03: items 2 (behavioral) and 10 resolved via threshold-choice convention bullet in "Useful patterns". Verified at `eval/results/2026-05-03_055901/`.
> - Step 4 complete 2026-05-03: item 6 resolved via new "### Schema gotchas" section (16 entries: 3 cross-cutting + 13 column-level). Verified at `eval/results/2026-05-03_064708/` for non-regression and `scratch/spot_check_item6.py` for HIGH-priority gotcha behavior. ~67% latency cost acknowledged in PHASE3B_NOTES item 6 with future tool-based mitigation noted.
> - Framework v1.5 complete 2026-05-03: items 11, 12, 13, 14 resolved. Item 11: `check_sql_scalar_matches_answer` in `eval/checks.py` catching SQL-vs-stated-answer contradictions. Item 12: per-question `must_not_contain` entries on Q4/Q6/Q8 in `eval/benchmarks.py` catching specific observed hallucinations ("Colorado vs. Colorado", "16 home runs in World Series", "729 in the Retrosheet data", "previous record of 71"). Item 13: `check_threshold_surfaced` catching Q3-shape responses that omit threshold prose. Item 14: documented design decision to keep strict mode on `trace_no_errors` (recovered errors remain fail signals — they surface prompt-tightening opportunities). Reusable validation harness `scratch/replay_historical_evals.py` accepts `--check`/`--expected-fail`/`--runs` flags and uses current benchmarks.py specs against historical responses. Validated against fresh evals `eval/results/2026-05-03_093717/` and `_095609/` (both 7 pass / 0 fail / 3 review_needed, identical structure to baseline `_064708/`).
> - Phase 3B closure complete 2026-05-03: items 3 and 4 resolved, closing Phase 3B at 14 of 14 items. Item 4 resolved via rule reconciliation — the narrative-question bullet in "Disambiguation logic" was rewritten to align with item 7's Dynamism "answer first, ask second" pattern, splitting into 2-3-match (multi-answer with brief bios) and 4+-match (escalate to `ask_user`) tiers. The discovery surfaced a rule conflict, not a calibration miss: the agent's prior "skip `ask_user` for Ken Griffey, multi-bio instead" behavior was the agent already preferring the Dynamism rule over the disambiguation rule. Item 3 closed-to-watch-list as stale evidence (no eval-framework reproduction, no rule-conflict basis identified). Verified at `eval/results/2026-05-03_105219/` — no regressions on disambiguation-adjacent questions. **Phase 3B exit criteria fully met.**

> **Sub-phase order deviation:** `phase3_architecture.md` sequences sub-phases as 3A → 3B → 3C → 3D → 3E. Actual completion order to date: 3A → 3D → 3B → (3C pending). Rationale: doing 3D first gives a baseline-and-checks framework against which to measure Phase 3B prompt iteration, a faster feedback loop than building the web UI first. The architecture doc is left unchanged as a clean reference.

> **Future deliverable — Project retrospective:** After Phase 3 completes, plan to author a comprehensive retrospective document covering project narrative, architectural decisions and their context, engineering patterns learned, meta-learnings about working with AI, and what's different from real production projects. Two intended audiences: future-Robert reviewing project history, and Robert-as-PM extracting principles applicable to real AI work scenarios. Format: markdown drafted then exported to Word/PDF for the final artifact. Estimated 6-10 hours of work across multiple sessions.

> **LEARNINGS.md:** PM-side engineering and AI-collaboration patterns captured incrementally during sessions, as observations surface. Source material for the eventual project retrospective document, but each entry is substantive enough to stand alone for direct reference. Started 2026-05-03 with 4 entries from Phase 3B closure session; remaining entries from earlier sessions backfilled as context allows.

## 2. Database connection

- **Database**: `baseball_oracle`
- **Schema**: `retro` (all tables live here; `public` is unused)
- **PostgreSQL**: version 16.13, at `C:\Program Files\PostgreSQL\16`
- **Service**: Windows service `postgresql-x64-16`, auto-start, port 5432
- **Credentials**: loaded from `C:\BaseballOracle\.env` (gitignored). Variables: `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_PASSWORD`, `PG_DATABASE`

### Running psql (PowerShell)
```powershell
$env:PGPASSWORD = (Get-Content C:\BaseballOracle\.env | Select-String '^PG_PASSWORD=' | ForEach-Object { ($_ -split '=', 2)[1] })
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U postgres -h localhost -d baseball_oracle
```

### Running Python (venv, no activation)
```
C:\BaseballOracle\.venv\Scripts\python.exe <script.py>
```
PowerShell's default ExecutionPolicy blocks `Activate.ps1`, so we invoke the venv's `python.exe` / `pip.exe` by absolute path.

## 3. Schema overview (11 tables in `retro`)

| Table | What it is | Natural key |
|---|---|---|
| `players` | Biographical data for players / coaches / managers / umpires (biofile0.csv) | `id` (8-char RetroID) |
| `players_team_year` | Per-season roster entries; one row per (player, team, year) | `(id, team, year)` |
| `relatives` | Player-to-player family relationships | `(id1, relation, id2)` |
| `teams` | Franchise-era team codes | `team` (3-char) |
| `ballparks` | Park metadata | `parkid` (5-char) |
| `games` | One row per game (gameinfo.csv) | `gid` (12-char: `team`+`YYYYMMDD`+`N`) |
| `batting` | Per-game per-player batting line; a player can appear multiple times per game | no PK; grain = `(gid, id, stattype, b_lp, b_seq)` |
| `pitching` | Per-game per-pitcher line; one row per appearance | no PK; grain = `(gid, id, stattype, p_seq)` |
| `fielding` | Per-game per-player per-position line | no PK; grain = `(gid, id, stattype, d_seq, d_pos)` |
| `teamstats` | Per-game per-team aggregate (inning scores + totals + starters) | no PK; grain = `(gid, team, stattype)` |
| `plays` | Per-play event log | `(gid, pn)` |

### Column naming quirks
- `retro.pitching.save` was renamed to `retro.pitching.is_save` (reserved-word adjacency; LLM-safety).
- `retro.plays.count` was renamed to `retro.plays.pitch_count`.
- `retro.games.save` was **not** renamed — in `games` it's a player ID (the save pitcher), not a flag.

### Schema versioning convention

`retro.schema_version` rows use date-string labels (`phase2-YYYY-MM-DD`) as **unique identifiers for traceability**, not strict calendar dates. Multiple migrations may land on the same wall-clock day; later labels may post-date the actual day. Don't read calendar meaning into the label — the row's `applied_at` timestamp is the real-time anchor.

### Primary key uniqueness (DB-enforced)

Three year-scoped tables have declared PRIMARY KEY constraints that the DB enforces at COPY time:

- `retro.games` — `gid` (cross-year scope; gid encodes year)
- `retro.players_team_year` — `(id, team, year)` (year is per-file constant)
- `retro.plays` — `(gid, pn)` (per-file scope; gid encodes year)

These constraints can halt real ingest even when dry-run completes cleanly, since dry-run only validates value-level transforms, not DB-level uniqueness. Any source-data correction that adds rows to these tables, or any future Retrosheet refresh, should be checked against the PK uniqueness scan (`ingest/phase2_pk_uniqueness_scan.py`) before resuming ingest.

The other 4 year-scoped tables (`batting`, `pitching`, `fielding`, `teamstats`) have grain keys per §3 above but no DB-enforced PRIMARY KEY constraints — their cell-level uniqueness is not COPY-time-enforced.

## 4. Data quirks discovered during ingestion

**Future-you will thank present-you for reading this section before writing queries.**

1. **Fractional weights exist.** `players.weight` is `NUMERIC(4,1)`. Willie V. Davis (`daviw104`) has `weight = 172.5`. Exactly one half-pound value in ~26k players, but the schema needed to accommodate it.

2. **`hittype` is not always single-character.** Retrosheet docs list B/G/P/F/L but 1998 data includes `BG` (2,982 rows) and `BP` (123 rows) — bunts classified by trajectory. Schema widened to `VARCHAR(4)`.

3. **`pitch_count` placeholder is `??`** when unknown (vs. e.g. `32` for a 3-2 count). Stored as `VARCHAR(4)` for future-year headroom.

4. **All 1998 rows have `stattype = 'value'`.** Other years (especially pre-1920 and Negro League games) will have `'official'`, `'lower'`, `'upper'` for uncertain stats. **Any aggregation query on `batting`, `pitching`, `fielding`, or `teamstats` MUST include `WHERE stattype = 'value'` once pre-1920 data is loaded** or it will silently double-count. Skipping the filter against 1998 data happens to work, but the habit will bite us later.

5. **`players.fullname` is the legal/birth name, not the common name.** Derek Jeter is `Derek Sanderson Jeter` with `usename = 'Derek'`, `lastname = 'Jeter'`. **Always look up players via `usename + lastname`**, not `fullname`. `WHERE fullname = 'Derek Jeter'` returns zero rows.

6. **Each game appears in `teamstats` twice** — once per team (more if multiple `stattype` rows). Counting games from `teamstats` requires `COUNT(DISTINCT gid)`, not `COUNT(*)`.

7. **Each play appears in `plays` exactly once.** No perspective duplication — `plays` is event-oriented. `batteam`/`pitteam` identify the perspective; no `DISTINCT` gymnastics needed when counting plays.

8. **Pre-1920 weather sentinels.** In older `games` rows, `temp = 0` means "unknown" (not 0°F) and `windspeed = -1` means "unknown" (not -1 mph). Ingest does not normalize these. Weather analysis must filter `temp > 0 AND windspeed >= 0` for real values.

9. **Partial dates in biofile0.** `birthdate`, `deathdate`, `debut_*`, `last_*` use `YYYYMMDD` but may contain `'00'` for unknown month/day — e.g. `'19010000'` means "born 1901, exact date unknown". Stored as **VARCHAR(8), not DATE**. Cast with `to_date(col, 'YYYYMMDD')` only when the value is fully known, or use `LEFT(col, 4)::int` for year-only extraction.

10. **Ballparks `start_date`/`end_date` are often NULL** for older parks where Retrosheet lacks exact open/close dates. Source uses mixed M/D/YYYY formatting.

11. **`plays.pitch_count` is a two-char ball-strike encoding, not a pitch-number.** First char = balls, second char = strikes. `"10"` = 1 ball / 0 strikes (batter ahead), `"32"` = full count, `"00"` = first pitch, `"??"` = unknown. Any user-facing rendering must translate (e.g. "on a 1-0 count"), never display the raw two-char string. **Pre-1960 data is not uniformly 2-char** — see item 15 for the pitch-sequence leakage pattern observed in 1950s records.

12. **`ballparks.name` sometimes carries multiple historical names for one `parkid`, joined by `;`.** Example: `CHI10` → `"Guaranteed Rate Field;U.S. Cellular Field"`. The canonical display name is era-dependent (which name was current at the game's date). Defer a proper era-sensitive resolver to the agent layer; for ad-hoc queries, `split_part(name, ';', 1)` gives the first / most recent name if a single string is needed.

13. **`plays.bathand='B'` does NOT mean "switch-hitter."** It means "this PA was by a switch-hitter, but which side they batted wasn't encoded in the event string." About 16% of 1998 plays (31,906 rows) carry this value. For "true left-handed batter" or "true right-handed batter" queries, join through `players.bats` rather than filtering `plays.bathand` — `players.bats='L'` is unambiguous, `plays.bathand='L'` plus a `plays.bathand!='B'` exclusion only approximates it. Counter-intuitive but important: verified in Query #3.

14. **Plays-table per-game aggregation verified clean for 1998.** The HAVING-clause cycle query returned exactly the three known 1998 cycles with no false positives or missing events. Confirms no per-play double-counting, no stattype artifacts at play grain, and no missing game data. The pattern (`GROUP BY batter, gid` with `HAVING` on hit-type sums) should work reliably for similar per-game aggregate questions (multi-HR games, five-hit games, 4-walk games, etc.).

15. **`plays.pitch_count` may contain pitch-sequence leakage in 1950s data.** Values longer than 2 characters are suspect — likely the actual count concatenated with pitch-sequence letters (F=foul, B=ball, S=strike, etc.) that should have gone into the separate `pitches` column. Example: `'22FFBBS'` observed in 1957. Schema widened to VARCHAR(8) to allow ingest, but queries using `pitch_count` for 1950s games may get malformed values. Future work: detect and split during ingest, or filter at query time.

16. **`games.starttime` is multi-format and must be handled carefully.** Three observed formats: `'HH:MM'` (modern), `'H:MMPM'` (some 1990s), `'0.5833...'` (fractional-day notation, some 1940s — `0.5833 = 14:00`). Schema is VARCHAR(20). Any time-of-game analysis must parse all three formats.

17. **`teamstats.start_l*` and `start_f*` may contain RetroIDs, malformed RetroIDs, or raw surnames depending on era.** Retrosheet falls back to surname (e.g. `'Patterson'`) when no canonical RetroID was assigned, and occasionally uses 9-char IDs (e.g. `'brownr103'`). Schema widened to VARCHAR(10) across all 19 starter slots (`start_l1..l9`, `start_f1..f10`). Lookup-by-id joins to `retro.players` will silently miss the surname-only rows for old games — Phase 3 agent should warn or fall back appropriately.

18. **Negro League gids don't fit the `team(3)+YYYYMMDD(8)+N(1)` shape.** Examples: `IN6193706131` (1937 KCM game), `BIR193704252`. The 12-char width is preserved but the team-prefix slot may not be a real 3-char team code, so date-extraction by string slice (positions 3–10) is unsafe for these rows. For date queries, use the dedicated `games.date` column instead of parsing `gid`.

19. **`?` and `unknown` are Retrosheet "value unknown" markers in numeric columns.** Distinct from the numeric sentinels in item 8.
    - `?`: 13 rows total. fielding.d_pos for Negro League games (1937–38, 5 rows) and teamstats numeric columns in 1945–46 (8 rows).
    - `unknown`: 156 rows total. games.temp (1950, 1969, 1970) and games.windspeed (1969–70). 78+78 split.
    - Both convert to NULL via `to_int` / `to_float` / `to_bool` (handled in `_is_null_sentinel`, added 2026-04-27).
    - Note: this is a SECOND "unknown weather" convention layered on top of item 8's numeric sentinels (`temp=0`, `windspeed=-1`). The numeric sentinels still pass `to_int` and store as their literal numbers — they're a query-time concern, not an ingest concern.

20. **`x` / `X` in teamstats inning-score columns means "team did not bat in this inning."** Standard baseball notation: when the home team is leading after the top of the 9th, they don't bat in the bottom of the 9th; the inning shows X in the box score. 328 occurrences in 1937–49, all in teamstats.inn5–inn9. Converts to NULL via `to_int` (handled in `_is_null_sentinel`, added 2026-04-27). **Distinguish in queries:** `inn9 = 0` means "team batted, scored 0 runs"; `inn9 IS NULL` means "team did not bat in inning 9" (or the data quality is unknown for that row — these are indistinguishable at the storage layer).

21. **`games.tiebreaker` semantics changed in 2020.** Pre-2020: column was exclusively empty across 1907–2019 (verified). 2020+: Retrosheet encodes the base number where the runner is placed under MLB's extra-innings runner-on-2B rule. Currently always `2` (= 2nd base). Schema column type was changed from BOOLEAN to SMALLINT in the `phase2-2026-04-27` migration to accommodate. Future-proofs for hypothetical rule variants (runner on 1B or 3B). **For queries:** 2020+ regular-season games have `tiebreaker = 2`; pre-2020 games have `tiebreaker IS NULL`.

26. **`players_team_year.pos = 'X'` is Retrosheet's convention for All-Star Game / no-regular-season-position appearances.** Used systematically for All-Star Game rosters (e.g., the 1998 ALS team has the entire roster — Jeter, Griffey, Ripken, Pedro Martinez, Frank Thomas, Manny Ramirez, etc. — all with `pos='X'`). 3,708 total rows across 1933–2015. Also extends to a small number of modern non-ALS cases (5 rows across 2005–2015) for cup-of-coffee or postseason-only appearances (e.g., Mark Kiger's 2 PR appearances in the 2006 ALCS, J.T. Snow's 2008 farewell appearance, Raul Mondesi Jr.'s 2015 WS debut). **NOT a data quality sentinel — a real Retrosheet convention.** Queries that filter by position should account for X-coded rows or exclude them depending on intent. Distinct from `'X'` in `teamstats.inn5..inn9` (item 20) which is the "didn't bat" notation; same surface character, different semantic context.

## 4a. Known unresolved data anomalies (will halt ingest if encountered)

The Phase 2 sentinel scan (2026-04-27) surfaced three categories of halt-prone data values that have NOT been resolved by the Layer 1+2 fix. They are documented here so they're not lost. If a future ingest halts on one of them, this section is the first place to look. None of these have been encountered against the post-Layer-1+2 fix yet — if they are, the dry-run will surface them.

22. **Approximate-attendance notation in pre-modern data — RESOLVED 2026-04-28.** 8 rows have hedged textual attendance values in `games.attendance` for 1938–1948 Negro League games: `'6000c.'` (×2), `'1000c.'`, `'5000c.'` (`c.` = circa); `'700?'`, `'6500?'` (uncertain); `'<1000'` (interval); `'hundreds'` (order-of-magnitude). Pre-modern records lacked exact attendance; Retrosheet preserved the source's hedging. **Resolution:** widened `retro.games.attendance` from INTEGER to VARCHAR(24) — option (a), preserve verbatim per §7 Data Source Principle. Numeric queries cast at use: `WHERE attendance ~ '^\d+$' AND attendance::int > N`. The "hedged value → numeric or NULL" interpretation is a query-time / agent-layer concern, not a schema concern. Migration: `schema/migrations/2026-04-28_attendance_varchar.sql`. Note: 5 additional decimal-fraction rows in `attendance` (Item 24, decimal-shape) were also surfaced by the verification scan; they ride along with the VARCHAR widening as side effect but remain Item 24's problem to investigate properly. Cross-referenced in Item 24.

23. **1948 NW2-game staging-duplicate rows — RESOLVED 2026-04-29 (originally cataloged as "malformed 1948 dates").** 41 rows in 1948 (1 gameinfo + 18 batting + 2 pitching + 18 fielding + 2 teamstats) carried date values shaped like `'11948062'` — initially hypothesized as a "leading-1 prepended" date corruption affecting many games. Investigation found a different and narrower truth: ALL 41 rows are duplicate copies of records for a single game (Homestead Grays @ Newark Eagles, 1948-06-29), with three fields corrupted by a `1`-insertion + last-character truncation pattern (gid `NW2119480629` instead of `NW2194806290`, date `11948062` instead of `19480629`, season `1194` instead of `1948`). The same game's records also exist in their proper chronological position in each file with valid canonical values. The corrupt copies are an early-staging-pass artifact that was never cleaned up before the seasonal CSVs were finalized. **Resolution:** delete the 41 corrupt-gid rows from the 5 source CSVs; keep the 41 clean canonical rows. Correction logged at `data_corrections/2026-04-29_1948_NW2_staging_duplicate_deletion.md` with full byte content of deleted rows for reversibility. The two versions also differ in one play's classification (napie101 PA, sac fly vs regular AB) — adopting the clean version's regular-AB classification; documented in the correction log.

    **Recovery option (registered for later):** Retrosheet's canonical event files (`.evn` / `.evx` per-team-per-year files) are the primary source from which the seasonal CSVs are generated. If a pattern-based coercion can't recover correct dates from a corrupted gameinfo CSV, the event files are the authoritative fallback. Not consulted for Item 23 (deletion was sufficient); flagged here so future work knows the option exists.

24. **Misalignment-suspect rows in pre-modern data — RESOLVED 2026-04-29.** Originally cataloged as "~16 rows where `'value'`, `'n'`, `'No'`, or fractional decimal values appear in numeric columns (1937–49)." Investigation broke this into 4 distinct sub-patterns, each treated separately:

    - **(a) Excel-fraction encoding leakage in `games.timeofgame`** — 1 row in 1943 (`KCM194307182`, `timeofgame=0.0590277777777778` → 85 minutes). Source-data fix. Logged at `data_corrections/2026-04-29_1943_timeofgame_excel_fraction.md`.

    - **(b) Text-duplication of `'value'` literal into `fielding.d_seq`** — 7 rows in 1949 (all in game `MEM194904112`). Caused by per-game data-prep auto-fill; `'value'` is the canonical `stattype` literal that got duplicated into the adjacent `d_seq` integer column. Source-data fix to NULL. Logged at `data_corrections/2026-04-29_1949_fielding_value_textdup.md`.

    - **(c) Textual NULL markers `'n'`/`'No'` in `teamstats.lob`** — 8 rows in 1948 across 4 Memphis-hosted Negro League games (`MEM194805231`, `MEM194807051`, `MEM194807052`, `MEM194809200`). Markers indicate "lob value not recoverable from incomplete box score." Source-data fix to NULL — chose not to add `'n'`/`'No'` to the global null-sentinel list because (i) only 8 cells in 1 year exhibit the pattern (not a stable convention), (ii) doing so would change `to_bool`'s mapping of `'n'`/`'no'` → False to NULL, a forward-compat hazard. Logged at `data_corrections/2026-04-29_1948_teamstats_lob_textual_null_markers.md`.

    - **(d) Whole-row staging duplicates with corrupted gid/date/season** — 41 rows in 1948 for game `NW2 vs HOM 1948-06-29`. Originally mis-cataloged as "Item 23 malformed dates." Resolution: deletion of corrupt copies (canonical clean copies already present). Logged at `data_corrections/2026-04-29_1948_NW2_staging_duplicate_deletion.md`. Tracked separately under Item 23 above for historical clarity.

    **Cross-reference (2026-04-28):** the Item 22 verification scan surfaced 5 additional decimal-fraction values in `games.attendance` (not teamstats) — `'0.125'`, `'0.0625'`, `'0.075'`, `'8.1250000000000003E-2'`, `'6.9444444444444434E-2'` — at gids `BLG194107271`, `BLG194107272`, `HOM194109011`, `KCM194305162`, `MEM194306280`. Same shape as the timeofgame Excel-fraction value (sub-pattern a). The Item 22 VARCHAR(24) widening incidentally allows these to load as strings, so they don't halt ingest. They remain stored verbatim in the attendance column and are not currently corrected — the source value is recoverable mathematically (multiply by 1440 → minutes) but the cells are in the wrong column anyway, so a recovery would also need to decide what `attendance` should be (likely NULL since the source clearly doesn't have it). Deferred for now; flagged here in case future work wants to clean up.

25. **`games.forfeit` is a Retrosheet code column, not a boolean — RESOLVED 2026-04-29.** The column carries single-char codes per Retrosheet's gameinfo spec: `V` (forfeit awarded to visitor), `H` (awarded to home), `T` (tied / score-as-is). Corpus also uses `Y` (forfeited, direction unspecified) — 6 rows across 1939–1948 — alongside 2 `H` rows in 1938. Total 8 non-empty rows across 1907–2023, all Negro League. The schema originally declared `forfeit BOOLEAN` and the ingest spec put it in `bool_cols`, which had two failure modes: (a) `'H'` halted ingest (`to_bool` raised); (b) `'Y'` silently mapped to TRUE, erasing the distinction between Y and H/V/T. The 1998 Phase 1 ingest worked only because 1998 has zero forfeits. **Resolution:** widened `retro.games.forfeit` from BOOLEAN to VARCHAR(2); removed from `bool_cols` in `spec_games`; passes through verbatim. Migration: `schema/migrations/2026-04-29_forfeit_varchar.sql`. Audit: `ingest/phase2_boolean_audit.py` confirmed `forfeit` is the only bool_col across all 4 spec functions (13 columns total) at risk — every other bool_col is either a true word-form boolean (`usedh`, `htbf`), a `'1'`-only flag-when-applicable column (10 cases across batting/pitching), or a genuine `'0'`/`'1'` boolean (`d_gs`). Class-of-bug refuted; this is a one-off.

27. **1949 BLG194905152 plays — two-game merge artifact, plays-only skip.** The 1949 corpus has 134 plays for gid `BLG194905152` (PH5 @ BLG doubleheader game 2, 1949-05-15) — 16 distinct pn values appearing 1× and 59 distinct pn values appearing 2× across two non-contiguous blocks (lines 50829–50884 and 50904–50962 in 1949plays.csv). Pairwise comparison shows ALL 59 duplicate pn pairs differ semantically (different pitchers, different inning halves, different teams batting). The five distinct pitchers in the plays — `byrdb101`, `grifb102`, `rickb102`, `rombb101`, `thomg105` — split: only `rickb102` and `rombb101` appear in the gameinfo (as wp/lp). The other three (`byrdb101`, `grifb102`, `thomg105`) appear in NO 1949 gameinfo entry near this date.

    **Diagnosis:** the missing `BLG194905151` (game 1 of the same doubleheader, absent from 1949gameinfo.csv, 1949teamstats.csv, and 1949plays.csv as a separate gid) had its play-by-play merged into `BLG194905152`. Both halves of the doubleheader's plays now share one gid. Cannot disambiguate without external evidence.

    **Resolution:** plays-only skip via `SKIP_PLAYS_GIDS` constant in `ingest_full.py`. The gameinfo and teamstats for `BLG194905152` load normally (they're internally consistent — final score and decision pitchers match). The plays file is filtered to exclude all rows with this gid. No play-by-play queries against this game will return data; gameinfo and teamstats queries work normally. Filter is applied at row-iteration level in `load_table`, with per-file log line `[retro.plays] {csv}: skipped N rows matching SKIP_PLAYS_GIDS` and an end-of-run rollup line in the run summary.

    **Recovery option (registered for later):** Retrosheet's canonical `.evn`/`.evx` event files (per CLAUDE.md §4a Item 23 recovery option) are the primary source. They could disambiguate which plays belong to game 2 vs game 1, allowing `BLG194905151` to be restored as a separate gid with its own plays. Not undertaken now.

28. **1937 NY5 @ NW2 missing-gid reconstruction — RESOLVED 2026-04-29.** Real ingest halted at year 1937 (post-PK-fix) with `psycopg.errors.NotNullViolation` on `retro.games.gid`. The single affected row in `1937gameinfo.csv` line 335 had every identifying field populated (`visteam=NY5`, `hometeam=NW2`, `site=NWK04`, `date=19370530`, `number=1`, `wp=mcdut101`, `lp=hollb106`, score 0–3 NW2 win) but an empty gid. **Resolution:** source-data fix — reconstructed `gid='NW2193705301'` from the canonical `TTT(home)+YYYYMMDD(date)+N(game_number)` pattern (CLAUDE.md §3 Schema overview). Logged at `data_corrections/2026-04-29_1937_NW2_missing_gid.md` with reversal procedure. **Scope verified:** `ingest/phase2_not_null_scan.py` (durable artifact, run 2026-04-29) confirmed this is the only NOT NULL violation across the entire 1907–2023 corpus across all 7 year-scoped tables. Class-of-bug ruled out — this is a one-off data-prep miss, not a systemic pattern. **Why dry-run missed it:** NOT NULL is enforced only at COPY time, not by the value-level transform layer the dry-run validates. Same enforcement-layer gap as the PK uniqueness halts; cross-referenced at CLAUDE.md §3 PK uniqueness subsection.

29. **1937 PH5 vs KCM teamstats gid typo — RESOLVED 2026-04-29.** Layer 1 post-load verification (check L1.6, `scratch/l1_06_games_teamstats_symmetry.sql`) surfaced one game with no teamstats coverage — `PH5193704130` (1937-04-13 KCM @ PH5 exhibition at HOU06, final 4-5) — paired with one teamstats-only "ghost" gid `PH5194704130` whose 2 rows carried correct date='1937-04-13', correct team codes (KCM, PH5), and correct scores (4-5) matching the canonical 1937 game. Single-digit year typo in the gid string: `1937` → `1947` (3→4). **Resolution:** source-data fix in 4 CSVs (`data/1937/1937teamstats.csv` 2 rows, `data/teamstats.csv` 2 rows, `data/teamlogs/1937KCM_stats.csv` 1 row, `data/teamlogs/1937PH5_stats.csv` 1 row — 6 occurrences total) plus a 2-row `UPDATE retro.teamstats SET gid='PH5193704130' WHERE gid='PH5194704130' AND date='1937-04-13' AND team IN ('KCM','PH5') AND stattype='value'`. Logged at `data_corrections/2026-04-29_1937_PH5_gid_typo.md` with reversal procedure. **Scope verified:** L1.6's cross-table symmetry check covered all 209,311 games; this was the only games↔teamstats orphan pair across the entire 1907-2023 corpus. The 24,882 single-team `(gid, stattype)` cases surfaced alongside this one are all `official`-stattype one-sided published-box-score supplements, not corruption — working as designed per CLAUDE.md §4 item 4. **Why dry-run missed it:** the typo is a valid VARCHAR(12) string at the value level; teamstats has no DB-enforced PK so the gid-uniqueness scan didn't flag it (gid `PH5194704130` is "unique" in teamstats by accident — there's no real 1947 game to collide with). Surfaces only as a structural cross-table assertion (every `games.gid` should appear in `teamstats` and vice-versa), which is Layer 1 verification, not a value-level transform or PK constraint. **Class-of-bug:** isolated single-game data-prep typo, distinct from the staging-duplicate pattern (Item 23) and the missing-gid pattern (Item 28). One-off; no systemic remediation needed.

## 5. Working conventions

- **Show before destructive execution.** Before running anything that modifies the DB or filesystem (schema changes, ingests, truncates, file writes outside scratch), surface the SQL / commands / content and wait for approval. Reads and `SELECT` queries are safe to run directly.

- **CLAUDE.md only captures claims this session can verify.** Evidence introduced via parallel conversations — the upstream PM/advisor chat, prior Claude Code sessions, or any external thread — does not count until the evidence is pasted into the current session. This prevents the CLAUDE.md artifact from drifting away from what was actually demonstrated. Applies to factual claims, external source attributions, and design decisions alike. If a prompt references something you haven't seen, ask for the evidence rather than encoding the claim.

- **Python venv: direct invocation, no activation.** Call `C:\BaseballOracle\.venv\Scripts\python.exe` by absolute path.

- **Ingest stops on failure.** The ingest script wraps the entire load in a single transaction and rolls back on any per-row transform failure or DB error. **Do not patch data silently** — surface the issue and wait for direction.

- **CSV value stripping**: All CSV string values are universally `.strip()`'d at the read boundary in ingest scripts. No Retrosheet field uses leading or trailing whitespace as meaningful content; this defensive strip handles known whitespace artifacts (e.g., `'VMA '` in 1946 allplayers.csv) and prevents whitespace from leaking into downstream transforms (e.g., date parsing).

- **Use the venv Python for all project scripts**, not system Python. System Python has no project packages installed; the venv has `psycopg`, `pandas`, `python-dotenv`, `SQLAlchemy`.

- **Collaboration model**: **Robert** is the product owner / PM and is not a developer. Technical decisions of any complexity are reviewed by a senior developer working in a separate Claude conversation before changes land. Expect Robert to relay architectural / design direction from that off-screen review. For non-trivial calls, it is fine (and often right) to ask Robert to check with the senior developer before proceeding.

- **Phase 2 ingest detail**: the multi-year (1907–2023) ingest plan — quirks-at-scale catalog, per-year transaction strategy, verification layers, and open questions — lives in `ingest/phase2_plan.md`. Consult before writing or modifying any Phase 2 ingest code.

- **Source-data corrections are an exception to "preserve Retrosheet verbatim."** The Phase 2 default is to accommodate Retrosheet quirks at the schema or ingest-transform layer, not by editing the source CSVs. The exception: when a value is a *demonstrable artifact* (Excel-fraction encoding, column-shift, prepended-digit error) AND the correct value is recoverable AND the affected row count is too small to justify a transform, edit the source CSV directly. Every such edit MUST be logged in `data_corrections/<date>_<description>.md` with the before/after values, the reasoning, and a reversal procedure. The original Retrosheet CSVs are otherwise committed unmodified.

## 6. Phase 1 acceptance criteria

> **Phase 1 SQL validation complete.** All five initial benchmark queries verified end-to-end. The data layer (`retro` schema, 1998 load) is trustworthy for player-level, game-level, team-level, and narrative queries. Proceeding to Phase 2 (full 1907–2023 ingest) or Phase 3 (agent layer) based on direction from PM.

The brief defines **25 benchmark questions** the system must answer. Phase 1 only requires answering them with manually-written SQL against the 1998 dataset — the agent / natural-language layer is Phase 3. The first five we're tackling:

1. **How many home runs did Derek Jeter hit in May 1998?** — ✅ verified: 4 HRs (5/2 vs KCA, 5/6 vs TEX, 5/13 vs TEX, 5/15 vs MIN)
2. **McGwire's 1998 HR chase** — ✅ verified: 70 HRs returned in chronological order. #1 was the Opening Day grand slam off Ramon Martinez (3/31 vs LAN); #62 (record-breaker) off Steve Trachsel 9/8 vs CHN; #70 off Carl Pavano on the final day 9/27 vs MON. Confirms the plays/games/players/ballparks narrative join works end-to-end.
3. **Left-handed batters vs. left-handed pitchers, 1998** — ✅ verified. Top 10 leaders with 150-AB floor: Olerud .375, Vaughn .340, Greer .328, Floyd .325, Vina .324, Clark .320, Palmeiro .317, Hamilton .317, Gwynn .316, Griffey .303. Platoon splits verified at league level (.262 LvL vs .277 LvR). Switch-hitter handling: exclude by `players.bats='B'` filter rather than `plays.bathand` (`plays.bathand='B'` means "side for this PA unknown," not "switch hitter"). 150-AB threshold locked in as single-season handedness convention.
4. **Who hit for the cycle in 1998?** — ✅ verified. Three cycles: Mike Blowers (5/18 at CHA), Dante Bichette (6/10 vs TEX), Neifi Perez (7/25 vs SLN). Zero natural cycles. Cross-checked against Baseball-Almanac and multi-source web search (Wikipedia, Baseball-Reference, MLB.com aggregated) — complete and exact match to authoritative record. This validates plays-table per-game aggregation as clean for 1998.
5. **1998 Yankees in close games vs. blowouts** — ✅ verified. Sanity check matched historical record (162 games, 114-48, .704 W%). Close-game performance: 77 games, 54-23, .701 W% — essentially identical to overall, a remarkable consistency that distinguishes great teams from lucky ones. Blowouts: 15-0 when leading 7+ after 6; 0-6 when trailing 7+ after 6. Zero comeback games — the 1998 Yankees had no games where a 7+ run deficit tightened to ≤2 runs. Validated teamstats inning-level data and confirmed `gametype='regular'` as the correct filter literal for regular-season games.

Question 1 was verified against public records (Baseball-Reference splits) as a data-pipeline sanity check.

---

> **Phase 2 verification complete (2026-04-29).** All three post-load verification layers passed. The data layer (`retro` schema, full 1907-2023 corpus, 28.16M data rows + 28,382 reference rows) is trustworthy for player-level, season-level, career-level, game-level, and play-level queries across the entire era. One source-data anomaly surfaced and was resolved end-to-end during Layer 1 — see §4a Item 29.

### Phase 2 verification summary

- **Layer 1 (internal integrity):** 7 checks — row counts vs checkpoint, date-range sanity, stattype distribution, team-code and player-ID orphans, games↔teamstats symmetry, PK uniqueness. All clean.
- **Layer 2 (external cross-checks):** 5 checks — games-per-year vs published schedule, career HR (Ruth 714, Aaron 755, Bonds 762), season HR (Maris '61=61, McGwire '98=70, Bonds '01=73), Ichiro 2004=262 hits, 4 landmark games (1923 Yankee Stadium opener, 1956 Larsen perfect game, 1974 Aaron 715, 2001 WS G7). Every numeric target matched exactly.
- **Layer 3 (Phase 1 reproducibility):** 5 queries (Phase 1 Q1-Q5 re-run against the full corpus). All identical to Phase 1 verified baselines.

### Institutional verification artifacts

Two complementary asset families, durable across re-ingests:

**Pre-ingest scan scripts** (`ingest/`) — read-only diagnostics surfacing halt-prone source data before COPY-time enforcement:
- `phase2_sentinel_scan.py` — value-level halt-prone strings (e.g. textual NULL markers in numeric columns)
- `phase2_boolean_audit.py` — bool_cols carrying non-bool values
- `phase2_decimal_fraction_scan.py` — Excel-fraction encoding leakage in int_cols
- `phase2_pk_uniqueness_scan.py` — duplicate keys before PK constraints reject them
- `phase2_not_null_scan.py` — empty values in NOT NULL columns

**Post-ingest verification queries** (`scratch/`) — 17 SQL files + paired `.out` captures (Layer 1: `l1_01_*` through `l1_07_*`; Layer 2: `l2_01_*` through `l2_05_*`; Layer 3: `q02-q05` reused + new `l3_05_jeter_may_1998.sql`). Re-run any time to validate a refreshed DB.

Phase 3 (agent layer) is the next major arc.

## 7. Data source principle

All statistical claims made by this system — batting averages, home run totals, game outcomes, career stats, any quantitative answer — MUST come from the loaded Retrosheet dataset in the `retro` schema. The agent layer (Phase 3) MUST NOT fetch statistics from external sources such as Baseball-Reference, FanGraphs, Wikipedia, StatCrunch, or any other site. This constraint is foundational, not a preference.

**Rationale:**
- **Authoritative source.** Retrosheet is compiled and peer-reviewed by baseball historians from primary sources. External sites may have been updated by non-authorities or may use different classification rules.
- **Internal consistency.** If different queries draw from different sources, numbers can silently disagree (e.g. Retrosheet vs Baseball-Reference classify passed balls vs wild pitches differently in older eras). Users who spot a discrepancy lose trust in the whole system.
- **Provenance.** Users want to know the data source. We can state "all statistics from Retrosheet 1907–2023" on the site and that claim must remain literally true.
- **Legal clarity.** Retrosheet data is freely licensed for research use with attribution. Scraping other stats sites has ToS implications.

**Permitted external use (agent layer only, Phase 3):**
- Narrative / contextual content (team backstory, biographical color, historical framing) may come from the Wikipedia RAG layer described in the original brief.
- Strict separation: external sources may describe WHY something happened, never WHAT the number is.

**Dev-time validation:**
This principle governs user-facing answers, not dev-time pipeline validation. When validating that our ingestion or query logic is producing correct results, cross-checking against external authoritative sources (Baseball-Reference, newspapers of record, etc.) is encouraged — that's how we catch ingestion bugs and SQL errors before they become user-facing. The test is **who consumes the output**: if a user sees it, Retrosheet-only. If the dev team is using it to verify the pipeline, external sources are appropriate and in fact advised.

Queries #1 (Jeter HRs) and #2 (McGwire chase) were both cross-checked against Baseball-Reference during development as pipeline validation. This was correct practice.

**Unanswerable questions:**
Some stats are not in Retrosheet and cannot be derived from it. Examples: **WAR** (Wins Above Replacement) — Baseball-Reference and FanGraphs each publish their own versions using computed park factors and positional adjustments that are not themselves in Retrosheet; HOF voting percentages; contract/salary data; Statcast metrics (pre-2015 games don't have these anywhere).

For these, the correct behavior is explicit honesty: "This system answers using Retrosheet data, which does not include WAR. I can tell you [related stats we DO have: OBP, SLG, OPS, batting runs…] if useful." We **NEVER silently substitute** another source for an unanswerable question.


## 8. Answer design principles — the dynamism philosophy

This system is a conversational research partner, not a query-to-answer translator. When a user asks a question, the agent should:

1. **Anticipate definitional ambiguity and surface the key choice in the answer itself.** Example: for "best LHB vs LHP in 1998," default to players with 150+ at-bats and phrase the response "For players with 150 or more at-bats against LHP in 1998, the leaders are…" — making the threshold visible, not hidden.

2. **When a question is genuinely multi-faceted, answer multiple valid interpretations at once.** Example: "Who won the most World Series with the fewest appearances?" — the definition of "appearance" is ambiguous. The agent should respond with 2–3 reasonable interpretations ("if you mean took the field in a postseason game: …; if you mean anyone on the postseason roster: …; if you include receiving a full share without postseason action: …") and let the user pick or appreciate the variations.

3. **Invite follow-ups that expose what was set aside.** Example: after the 150+ AB answer, offer "Want to see players with 50+ at-bats too? That would include smaller sample sizes." This lets users get to the other half of the data without feeling stuck with a single interpretation.

4. **Scale the depth of dynamism to the ambiguity of the question.** Trivial / unambiguous questions just get answered ("Jeter's HRs in May 1998 = 4"). Ambiguous questions get multi-interpretation treatment. A question with one obvious answer should NOT be padded with alternatives — over-offering is its own failure mode.

**Heuristic triggers** (not exhaustive; these will be refined through examples):
- Threshold/cutoff questions: always surface the threshold, always offer the alternative cutoff
- Definitional ambiguity: list multiple interpretations
- Time-range ambiguity: offer to clarify era if unspecified
- Single-interpretation factual questions: just answer

**Applicability to phases:**
- **Phase 1 (current, SQL only):** apply as a language convention — threshold-based queries phrase their output with the threshold visible (e.g., "For players with 150+ ABs…"). No multi-interpretation or follow-up behavior yet — we don't have the agent to deliver it.
- **Phase 3 (agent layer):** full implementation of all four principles above.


## 9. Agent Design Considerations (DEFERRED)

> **Status: DEFERRED.** The following are known requirements for the future Intake / Clarification Agent. They are **captured here so they're not forgotten** when we build Phase 3. **Do not start implementing any of this now** — Phase 1 is SQL-only.

### 9.1 Player name disambiguation

Common surnames map to multiple players. A naive `WHERE lastname = 'Bonds'` is almost never what the user wanted:

| Surname | Players |
|---|---|
| Bonds | Barry, Bobby |
| Griffey | Ken Sr., Ken Jr. |
| Ripken | Cal, Billy |
| Alou | Felipe, Matty, Jesús, Moisés |

**Tiered lookup strategy** the agent should follow:

- **1 match** → answer directly.
- **2–5 matches** → ask the user to pick. Era + team + position is usually enough context to disambiguate without requiring a full first name.
- **Many matches** → ask for the first name or some other narrowing predicate before running anything.

**Lookup rules**:
- Primary lookup is **`usename + lastname`**, NOT `fullname`. `fullname` includes middle names and rarely matches what a user types (see data quirk #5 — Derek Jeter is `Derek Sanderson Jeter`).
- **`players.altname`** may hold nicknames ("A-Rod", "Big Papi"). Needs investigation before we rely on it — column contents are not yet characterized.
- **Eventually add `pg_trgm`** (PostgreSQL trigram extension) for fuzzy matching to handle misspellings and accent-insensitive lookup ("Ramirez" vs "Ramírez").

### 9.2 Team name disambiguation

Same tiered pattern as players — disambiguate by era when multiple matches exist. `teams.first_year` / `teams.last_year` are the anchors.

- **"Washington"** → Senators (`WS1` 1901–1960, `WS2` 1961–1971) or Nationals (`WAS` 2005–present). Three distinct franchises, all called "the Washington team" at different times.
- **"New York"** → Yankees (`NYA`), Mets (`NYN`), Giants pre-1958 (`NY1`), Highlanders (pre-Yankees-branding AL NY), and several 19th-century entries.
- Most historical team names have this problem. The agent cannot safely answer "How did Washington do in 1925?" without knowing the user means Senators-era `WS1`.

### 9.3 Conceptual ambiguity beyond names

Harder than name lookups. Likely requires a mix of biographical context (the `biofile0` fields we have) and LLM world-knowledge:

- **"How did Babe Ruth do as a pitcher?"** — the agent needs to know Ruth pitched primarily 1914–1919, then shifted to the outfield. `players.debut_p` / `last_p` only spans his whole career; role changes aren't in our schema.
- **"Did the Yankees win the playoffs in 1996?"** — requires knowing the playoff structure of that era (Division Series / LCS / World Series, wild card rules of the day). Our schema has `games.gametype` that distinguishes `regular` from postseason games, but does not label which round.
- Likely approach: lean on LLM world-knowledge for framing and context, use the database only for verifiable stat lookups.

### 9.4 Era-aware response calibration

The agent's response confidence should be calibrated to the data era, with explicit caveats for known-thin periods. This is a corollary of §8 Answer Design Principle 1 (anticipate definitional ambiguity, surface threshold) — extended to acknowledge that data quality itself varies by era.

Known data-era limitations:

- **Pre-1907**: No play-by-play data (no `plays.csv`). Game-level results exist but at-bat-level queries return nothing. Agent should respond "play-by-play data isn't available for [year]" rather than reporting empty results as zero.
- **1907–1949 Negro Leagues**: Records are reconstructed from incomplete contemporaneous box scores. Some games have approximate attendance (`'hundreds'`, `'6000c.'`, `'<1000'` — see CLAUDE.md §4a Item 22). Statistical totals are reliable for documented games but season totals may be incomplete.
- **WWII era (1942–1945)**: Player rosters and competitive context were significantly altered by military service. Comparisons spanning this era warrant note.
- **1969 expansion**: League structure changed (NL/AL → divisions). Era-comparisons of league-leading totals should account for this.
- **2020**: 60-game season due to pandemic. Per-game-rate comparisons valid; counting-stat comparisons across this and other seasons are misleading without context.
- **Post-2020 tiebreaker rule**: `tiebreaker = 2` indicates the runner-on-2B extra-innings rule is in effect (see §4 item 21). Walk-off and extra-inning records before/after 2020 are not directly comparable.

This list is illustrative, not exhaustive. The agent should:
1. Recognize when a query touches an era with known limitations
2. Provide the answer as best the data supports
3. Caveat with the relevant era characteristic
4. Not pretend equal confidence across eras

This pairs with the Andy Fox / dynamism / threshold-in-headline principles: all are about not faking confidence we don't have. Era characteristics are real, documented features of baseball history — surfacing them honestly is more useful than papering over them.

---

*Reminder: section 9 is DEFERRED. Phase 1 work is SQL-only against the loaded 1998 data. Revisit this section when we start building the Intake / Clarification Agent in Phase 3.*

## 10. Future architecture considerations

### Retrosheet data source

The loaded corpus runs 1907–2023. Retrosheet has no play-by-play coverage before 1907; pre-1907 years (1901–1906) have box-score data only, which is not in the agent's scope. The pre-1907 year folders exist on disk in `data/` but are not ingested.

Phase 2 ingests from local CSV snapshots at C:\BaseballOracle\data\. Long-term, we may shift to direct integration with Retrosheet's event files or database (pending permission), which would give us:
- Fresher data (Retrosheet corrections propagate without manual re-pulling)
- Authoritative source (event files are primary; CSVs are box-score-derived)
- Programmatic re-ingestion (can re-pull a specific year on demand)
- Possibly richer per-play detail than current CSV exposes

Implication for current work: source-data corrections in data_corrections/ are provisional pending potential migration. They should NOT be treated as permanent fixes to be carried forward indefinitely. When migration happens, re-evaluate whether each correction is still needed against the new source.

## Repository layout

```
C:\BaseballOracle\
├── .env                     # DB creds (gitignored)
├── .gitignore
├── CLAUDE.md                # this file
├── data\                    # Retrosheet CSVs (1907-2023 year folders + cross-year files)
├── schema\
│   └── schema.sql           # source of truth for the retro schema
├── ingest\
│   ├── ingest_1998.py       # Phase-1 loader (4-stage COPY pipeline)
│   └── scan_widths.py       # diagnostic for VARCHAR/CHAR width issues
└── .venv\                   # Python 3.12.10 virtualenv
```
