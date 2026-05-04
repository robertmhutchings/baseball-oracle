-- =============================================================
-- Phase 2 schema migration: tiebreaker BOOLEAN -> SMALLINT
--
-- Motivation: Phase 2 sentinel scan (2026-04-27) surfaced 8,210 rows
-- in 2020-2023 gameinfo.csv with tiebreaker='2'. Per the 2020 MLB
-- extra-innings rule, tiebreaker now encodes the BASE NUMBER where
-- the runner is placed (currently always 2 = second base), not a
-- yes/no flag. Pre-2020 the column was exclusively empty across
-- 1907-2019 (verified), so this migration is forward-only with no
-- historical translation required.
--
-- The Layer 1 ingest fix (in the same release) also adds sentinel
-- handling for {'?', 'x', 'X', 'unknown'} -> NULL in to_int/to_float/
-- to_bool. That's purely transform-side, no schema impact.
--
-- Safety: BOOLEAN -> SMALLINT requires a USING clause; the CASE
-- below is defensive against any DB state (real DB has no rows yet
-- for the column post-load; scratch had no non-null tiebreaker
-- values either). NULL stays NULL; TRUE -> 1; FALSE -> 0.
-- =============================================================

BEGIN;

ALTER TABLE retro.games
    ALTER COLUMN tiebreaker TYPE SMALLINT
    USING (CASE WHEN tiebreaker IS NULL THEN NULL
                WHEN tiebreaker THEN 1
                ELSE 0
           END);

COMMENT ON COLUMN retro.games.tiebreaker IS
    'Base where extras-runner is placed (2020+ rule). NULL pre-2020 or where rule does not apply.';

INSERT INTO retro.schema_version (version, notes) VALUES (
    'phase2-2026-04-27',
    'tiebreaker BOOLEAN -> SMALLINT (2020+ runner-on-2B rule). Bundled with ingest_full.py Layer 1 sentinel handling for {?, x, X, unknown}.'
);

COMMIT;
