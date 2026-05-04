# Phase 2 Step 3 — Ingest Refactor Design Sketch

**Status:** Draft for PM + senior-dev review. **No code written yet.**
**Predecessor:** `ingest/phase2_plan.md` (canonical Phase 2 guide).
**Successor:** `ingest/ingest_full.py` (to be written after this sketch is approved).

This document makes every consequential decision explicit before we commit code. Each section either **confirms** Robert's proposal, **refines** it, or **pushes back**.

---

## 1. Script identity

**Decision: new file at `ingest/ingest_full.py`. Preserve `ingest/ingest_1998.py` unchanged.** ✅ confirm Robert's preference.

**Why preserve the 1998 script:**
- It is Phase 1 evidence — five benchmark queries were validated against the data it produced. Changing it muddies that provenance.
- Operational model is genuinely different (per-year transactions, checkpointing, CLI surface, progress logging). The diff would be dominated by mechanical shuffling rather than focused changes; reviewers would lose signal.
- Re-runnability against 1998 is useful: if we ever doubt a Phase 2 result, we can re-run `ingest_1998.py` against a scratch DB and compare.

**What `ingest_full.py` reuses:** the value-transform helpers (`passthrough`, `to_int`, `to_bool`, `to_date_yyyymmdd`, `to_date_mdy`, `to_float`) and the per-table `spec_*()` functions, parameterized over `year`. The COPY-based `load_table()` core stays similar in shape but gains the lenient-missing-column behavior (§8).

**What changes structurally:**
- Stage 1 (reference tables) becomes a one-shot setup, idempotent on resume.
- Stages 2–4 wrap in an outer year loop with per-year commit + checkpoint.
- All `1998`-specific paths and constants become `year`-parameterized.

---

## 2. CLI surface

Refining Robert's list. Recommend these flags:

| Flag | Default | Purpose |
|---|---|---|
| `--dry-run` | off | Run all transforms; never write to DB. Surfaces transform failures and missing-column patterns without committing. |
| `--from-year YYYY` | 1901 | Inclusive lower bound. |
| `--to-year YYYY` | 2023 | Inclusive upper bound. |
| `--year-only YYYY` | — | Load exactly one year. Mutually exclusive with `--from-year` / `--to-year`. Useful for reloading a single year after a targeted fix. |
| `--force-restart` | off | Ignore checkpoint, TRUNCATE all 11 tables, start over from scratch. Gated by an interactive y/N prompt unless `--yes` is also passed. |
| `--reload-reference` | off | Truncate **only** the 4 reference tables and reload them. Year data untouched. (See §9.) |
| `--verify-existing` | off | On resume, re-count already-loaded years and compare to checkpoint before continuing. (See §4.) |
| `--verbose` | off | Per-CSV-row periodic heartbeat (`every N rows: pos, rate`) instead of just per-stage milestones. |
| `--max-runtime-hours N` | 8 | Wall-clock cap. After current year commits, halt cleanly if exceeded. (See §7.) Default raised from initial 6h proposal: throughput estimates have been wobbly (Step 1 width scan ran 3–4× faster than projected) so a generous cap with manual Ctrl-C as the practical halt is safer than a tight cap that fires near the finish line. |
| `--no-pg-tuning` | off | Skip the session-level `synchronous_commit=off` / `maintenance_work_mem` SET commands. Slower but no crash-recovery risk to in-flight commits. |
| `--yes` | off | Suppresses the y/N prompt for `--force-restart`. Required for unattended runs that would otherwise stall on the prompt. |

**Pushback on Robert's list:** none. Additions justify themselves: `--year-only` makes targeted re-runs trivial; `--reload-reference` and `--verify-existing` were already proposed in #9 / #4 and just need to be explicit at the CLI layer; `--max-runtime-hours` makes the 6-hour cap configurable rather than baked in; `--no-pg-tuning` gives us an escape hatch if Postgres tuning surfaces problems mid-load.

**What I'm explicitly NOT adding:** `--parallel-years` (per phase2_plan.md §3 "What we're NOT doing"), `--skip-verification` (verification is cheap and load-bearing — disabling it should require a code change, not a flag).

---

## 3. Checkpoint file format

**Path:** `ingest/.ingest_progress.json` for real runs; `ingest/.ingest_progress.json.dryrun` for `--dry-run` mode (prevents dry-run from clobbering real-run state). Both gitignored, dotfiles so they sort away from source.

**Write semantics:** atomic — write to `.ingest_progress.json.tmp`, `fsync`, then rename. A mid-write crash leaves the previous checkpoint intact. Update happens **after** the per-year transaction commits, never before (per phase2_plan.md §4).

**Fields:**

```
{
  "schema_version":         "phase2-2026-04-24",   # bumps when schema changes
  "script_version":         "ingest_full.py@<git-sha-or-hardcoded>",
  "run_id":                 "<uuid4>",             # new uuid each invocation
  "started_at":             "<iso8601>",
  "last_updated_at":        "<iso8601>",
  "reference_tables_loaded": {
      "loaded": true,
      "loaded_at": "<iso8601>",
      "row_counts": { "teams": ..., "ballparks": ..., "players": ..., "relatives": ... }
  },
  "last_completed_year":    1934,
  "skipped_years":          [
      { "year": 1916, "reason": "missing 1916plays.csv" }
  ],
  "row_counts_cumulative":  {
      "games": ..., "players_team_year": ..., "batting": ...,
      "pitching": ..., "fielding": ..., "teamstats": ..., "plays": ...
  },
  "per_year": [
      {
          "year": 1934,
          "started_at": "<iso8601>",
          "completed_at": "<iso8601>",
          "duration_seconds": 64,
          "row_counts": { "games": 1232, "plays": 142550, ... },
          "missing_columns": [
              { "table": "plays", "columns": ["pitch_count", "pitches"] }
          ]
      },
      ...
  ]
}
```

**Refinements over Robert's proposal:**
- `script_version` in addition to `schema_version`. A schema is unchanged but a script bug fix is still a meaningful change to track.
- `run_id` per invocation. Useful for correlating with the progress log.
- `reference_tables_loaded` as a structured object rather than a bool — captures when and what was loaded, so we can detect tampering.
- `per_year` array with full per-year detail. Lets post-hoc analysis answer "which year took longest" or "which years had missing columns" without re-parsing the log.
- `row_counts_cumulative` is what gets cross-checked against the live DB on `--verify-existing`.

**File size concern:** with 123 years × moderate per-year detail, file stays comfortably under 100 KB. Re-write the whole file on each commit (no append, no journal).

---

## 4. Resume semantics

**Recommendation: trust the checkpoint by default; `--verify-existing` for paranoid re-verification.** ✅ confirm Robert's proposal.

**Default-trust behavior:**
- Read checkpoint. If it exists and is valid, skip years ≤ `last_completed_year`, resume at `last_completed_year + 1`.
- Reference tables: skip if `reference_tables_loaded.loaded` is true.
- Year is considered "completed" only if it appears in `per_year` AND `last_completed_year >= year`.

**`--verify-existing` behavior:**
- Before resuming, query live DB for cumulative row counts on each year-bearing table.
- Compare against `row_counts_cumulative` in the checkpoint.
- Mismatch → halt with diagnostic. Do not silently proceed.

**Sanity guards (always-on, regardless of `--verify-existing`):**
- Checkpoint says reference loaded but `SELECT count(*) FROM retro.players = 0` → halt, refuse to resume. State is corrupt; user must `--force-restart` or `--reload-reference`.
- `--from-year` is < `last_completed_year + 1` and `--force-restart` not given → halt with clear message ("would re-load year X already in DB"). Forces the user to think.
- Checkpoint `schema_version` doesn't match current schema's version stamp → halt, refuse to resume. The current version is read at ingest startup via `SELECT version FROM retro.schema_version ORDER BY applied_at DESC LIMIT 1` — the table is append-only history; latest row by `applied_at` is current. (See §10 Q1.)

**Pushback on Robert's framing:** "trust by default" is right, but it needs the sanity guards above to avoid silent corruption when the DB and checkpoint disagree. The guards make trust safe rather than blind.

---

## 5. Transaction boundaries

**Confirming the plan with one explicit refinement.**

| Phase | Boundary | Behavior on failure |
|---|---|---|
| Stage 1 (reference tables) | One transaction. Runs once. | Roll back, halt. No partial reference state. |
| Stages 2–4 per year | **One transaction per year**, covering all of games + per-game stats + plays for that year. | Roll back that year only. Prior years' commits stand. Halt with diagnostic. |

**Refinement:** explicitly NOT one-tx-per-(year,stage). It is one-tx-per-year covering stages 2–4 together. Rationale: if `plays.csv` (stage 4) fails for 1934 but `games.csv` (stage 2) and the stage-3 tables already committed, we'd have a "partial 1934" — `games` rows with no `plays`, downstream queries would silently miss data. Atomic year is the right grain.

**TRUNCATE behavior:**
- First run (no checkpoint): TRUNCATE all 11 tables, then proceed. Confirmation prompt unless `--yes`.
- Resume (checkpoint exists): no TRUNCATE.
- `--force-restart`: TRUNCATE all 11 tables, delete checkpoint, proceed. Confirmation prompt unless `--yes`.
- `--reload-reference`: TRUNCATE only the 4 reference tables (teams, ballparks, players, relatives), update checkpoint's `reference_tables_loaded`, then either exit or continue depending on whether other flags imply a year load.

---

## 6. Progress logging

**Confirming Robert's proposal with implementation detail.**

**Mechanism:** Python `logging` module, two handlers:
- StreamHandler → stdout (for live human monitoring)
- FileHandler → `ingest/.ingest_progress.log` for real runs; `ingest/.ingest_progress.log.dryrun` for `--dry-run` mode

**Format:** `<iso8601> [<level>] <year>/<stage>: <message>`

**Cadence:**
- One line per CSV started: `[1934 stage 4] plays.csv: starting (estimated 142,000 rows)`
- One line per CSV completed: `[1934 stage 4] plays.csv: 142,550 rows in 64s (2,227 rows/s) — cumulative 3h 17m`
- Heartbeat every 30 seconds inside long COPY operations: `[1934 stage 4] plays.csv: still loading, position 87,300 rows`
  - This doubles as the stuck-detection signal (§7).
- One line per year completed: `[1934] year complete: 7 tables, 187,432 rows total, 71s, checkpoint written`
- End-of-run summary table: per-year row counts, total rows, total runtime, skipped years, missing-column summary.

**Log rotation:** on each invocation, if `.ingest_progress.log` exists, rename to `.ingest_progress.log.<timestamp>` before opening fresh. Keeps history without unbounded append.

**`--verbose` adds:** per-N-row progress inside each CSV (every 10K rows). Useful when chasing a specific issue; off by default to keep the log readable.

---

## 7. Stop conditions for async mode

**Confirming Robert's list. Refinements on detection mechanism for each.**

| Condition | Detection |
|---|---|
| Per-row transform failure | Existing behavior. Try/except in load loop, halt on first failure. |
| DB connection lost | `psycopg.OperationalError` caught at the year-transaction boundary. **One** retry with 5-second backoff before halting (network blips happen; total flameout doesn't). |
| Disk full | Pre-check at start: free space on the data partition must be ≥ 10 GB. Re-check between years. Catching `OSError errno=28` mid-COPY is unreliable. |
| Stuck (>10 min on one CSV) | Heartbeat thread. Main thread updates `last_progress_ts` every 1000 rows. Heartbeat thread checks every 30s; if `now - last_progress_ts > 600s`, raises a `StuckError` flag the main loop polls between rows. (Avoids signals on Windows.) |
| Cumulative runtime > N hours | Wall-clock check after each year commit. If exceeded, halt cleanly (finish current commit if in flight; do not start the next year). Default N=8 (configurable via `--max-runtime-hours`). |
| Checkpoint write failure | Treat as fatal. The checkpoint is load-bearing; running blind is not acceptable. Halt with explicit "checkpoint write failed" diagnostic. |

**Halt behavior (uniform across all conditions):**
1. Roll back any in-flight transaction.
2. Write `ingest/.ingest_halt_reason.txt`:
   ```
   timestamp: <iso8601>
   year: 1934
   stage: 4
   csv: 1934plays.csv
   condition: stuck-no-progress
   error_class: StuckError
   message: no progress for 612s
   last_completed_year: 1933
   partial_state: <rolled back>
   ```
3. Exit with non-zero status.

**Format choice:** plain key:value text rather than JSON. Cheaper to read at a glance during a 6-AM diagnostic. Post-hoc agents can still parse it trivially.

**SIGINT (Ctrl-C):** install a handler. On first Ctrl-C, set a "graceful shutdown" flag the main loop checks between rows; rolls back current year, writes halt reason, exits. On second Ctrl-C, hard exit (psycopg cleanup may not happen, but user has explicitly asked).

**Not adding:** automatic restart on halt. The whole point of halting is to surface a problem for human review. Auto-restart loops would mask quirks we need to know about.

---

## 8. Lenient missing-column policy

**Confirming Robert's proposal with operational detail.**

**Behavior:**
- For each per-year CSV, compute `missing = expected_csv_headers - set(actual_csv_headers)`.
- If `missing` is non-empty: warn (not error), fill those columns with NULL for every row of this year-table, log to `ingest/.missing_columns.log`, continue.
- For unexpected CSV columns (i.e., headers in CSV that are NOT in the spec): silently skip with a one-line note in the same log. (This is already the current 1998 behavior — preserve it explicitly.)

**Log format** (`ingest/.missing_columns.log`):
```
<iso8601> year=1916 table=plays missing=[pitch_count,pitches,bat_f]
<iso8601> year=1916 table=plays unexpected=[old_col_we_dont_care_about]
```
One line per (year, table, direction). Not per row — the 1998 boundary stripping log taught us per-row spam is unreadable.

**End-of-run summary:** the summary table includes a "missing columns" section grouped by column → years it appeared in. Pattern detection becomes obvious: if `pitch_count` is missing in every year ≤ 1987, we know what to expect for the agent layer; if it's missing for one random 1953 file, that's an investigate-worthy anomaly.

**Pre-flight check on NOT NULL:** before relying on lenient mode, audit `schema.sql` for NOT NULL constraints on any column we might NULL-fill. If found, either (a) confirm those columns will always be present (in which case the NULL-fill is unreachable for them), or (b) relax the NOT NULL. Phase2_plan.md §2(e) flagged this; we should run the audit as part of writing this script.

---

## 9. Reference-table handling on resume

**Confirming Robert's proposal.** ✅ skip if checkpoint says they're loaded; `--reload-reference` flag for explicit reload.

**Sanity check (always-on):** if checkpoint says reference loaded but a smoke query (`SELECT count(*) FROM retro.players`) returns 0, treat as corrupt state and halt (per §4 sanity guards). Do not silently re-load — that masks an unknown problem.

**`--reload-reference` behavior:**
- TRUNCATE retro.relatives, retro.players, retro.ballparks, retro.teams (children-first order).
- Reload from `data/teams.csv`, `data/ballparks.csv`, `data/biofile0.csv`, `data/relatives.csv`.
- One transaction.
- On success: update checkpoint's `reference_tables_loaded` block (new timestamp, new row counts).
- Does NOT touch year-bearing tables. Year data continues to reference reference-table rows by RetroID; if a player ID's row contents change, the reference is still valid — but if a player ID is *removed* (e.g., reference CSV no longer contains it), the year tables now have orphan references. Acceptable; phase2_plan.md §5 layer 1 catches orphans as a verification step.

**When you'd use `--reload-reference`:** Retrosheet publishes an updated `biofile0.csv` (corrects a death date, adds a recent retiree's nickname). Cheaper to reload reference tables than to re-ingest 123 years.

---

## 10. Resolved decisions

Answers to the original open questions, confirmed by PM 2026-04-25.

1. **Schema version stamp.** Approved option (a): add `retro.schema_version` 1-row table. Version string format: `phase<N>-YYYY-MM-DD` (e.g. `phase2-2026-04-24`). Bumped on each schema migration.
2. **Year ordering.** Ascending (1901 → 2023). Surfaces reference-table orphans early; partial-completion state is more useful with old years done.
3. **Where the script runs.** Claude Code background bash for **both** dry-run and real run. Checkpoint + progress log are session-independent — a new Claude Code session can re-attach by reading the files. (The original concern about Claude Code session timeouts is mitigated by this independence.)
4. **Dry-run writes checkpoint and log.** Yes, with distinct filenames so dry-run cannot clobber real-run state: `ingest/.ingest_progress.json.dryrun` and `ingest/.ingest_progress.log.dryrun` (see §3 and §6).
5. **Smoke test on 3 scratch years.** Yes. Years: 1925, 1955, 1985 against a separate scratch database `baseball_oracle_scratch`. Smoke test additionally exercises the error path: deliberately corrupt one year (rename a CSV column header on a NOT NULL column to test halt path; on a nullable column to test lenient path), confirm clean halt with correct diagnostic, restore, confirm `--year-only` re-loads that year alone. Estimated runtime: ~10 minutes total.

---

## 11. What this design does NOT cover

- **Indexes.** Built post-load as a separate migration (phase2_plan.md §6 step 7). Out of scope for `ingest_full.py`.
- **Verification queries.** Layer 1/2/3 verification (phase2_plan.md §5) lives in separate scripts run after the load completes. Out of scope here.
- **CLAUDE.md updates.** Discovered-at-scale quirks get added to §4 as we encounter them. Out of scope for this design.
- **Performance tuning beyond `synchronous_commit=off` and `maintenance_work_mem`.** Phase2_plan.md §3 already decided what we are and aren't doing.

---

## 11a. Known design-vs-implementation discrepancies (registered for follow-up)

These are places where the design doc and the implemented `ingest_full.py` behave differently. Both are defensible; flagged here so a future iteration can decide whether to tighten the design wording or change the implementation. Not blocking real ingest.

### 11a.1 Resume-from-year: auto-bump vs. explicit-flag

- **Design (§4 "Default-trust behavior"):** "Read checkpoint. If it exists and is valid, skip years ≤ `last_completed_year`, resume at `last_completed_year + 1`." Reads as an automatic resume — pass no `--from-year` and the script picks up where it left off.
- **Implementation (`ingest_full.py:1622`):** sanity guard halts if `--from-year < last_completed_year + 1` and `--force-restart` is not given. Default `--from-year=1901` therefore halts on every resume; the user must pass `--from-year` explicitly to ≥ `last_completed_year + 1`. The error message is clear and includes the right value.
- **Surfaced:** 2026-04-29 real-ingest resume attempt — typed `ingest_full.py --database baseball_oracle --yes` (no `--from-year`); halt fired immediately with a clear message; corrected on retry with `--from-year 1930`. No DB state mutation, no data risk; just an extra round-trip.
- **Tradeoff:**
  - Current implementation is **safer** — forces the operator to confirm the resume year, prevents a mistyped `--from-year` from silently re-loading already-completed years.
  - Design wording is **more ergonomic** — the user types the same command for both fresh and resume runs, and the script Just Works.
- **Decision deferred.** Either harmonize the design wording to match the implementation (document the explicit-flag requirement as the intended UX), or change the implementation to auto-bump `from-year` to `last_completed_year + 1` when the checkpoint exists and the user didn't pass an explicit `--from-year`. Both have merit.

---

## 12. Implementation sequence (once design is approved)

1. Audit schema.sql NOT NULL constraints (§8 pre-flight).
2. (If approved) Add `retro.schema_version` 1-row table migration (§10 Q1).
3. Write `ingest_full.py`:
   - Parameterize spec functions over `year`.
   - Add CLI argparse layer (§2).
   - Refactor `load_table` for lenient missing-column behavior (§8).
   - Add per-year transaction loop with checkpoint write (§3, §5).
   - Add progress logging (§6).
   - Add stop-condition handlers (§7).
4. Smoke test on 3 scratch years (§10 Q5).
5. Full dry-run across 1901–2023 (`--dry-run`).
6. Review dry-run output. Fix any surfaced quirks.
7. Real load.

---

*End of design sketch. Awaiting PM + senior-dev review before any code is written.*
