-- =============================================================
-- Phase 2 schema migration
-- Widens three column groups surfaced in Step 1 discovery (width scan
-- across 1901-2023). No new columns, no new constraints, no table
-- rewrites — all three changes are metadata-only VARCHAR widenings
-- in PostgreSQL.
--
-- Motivations:
--   games.starttime:   1940s data sometimes uses fractional-day
--                      notation ('0.58333333333333337' = 14:00), up to
--                      19 chars instead of the expected 'HH:MM'.
--   plays.pitch_count: 1957 data contains pitch-sequence leakage
--                      ('22FFBBS'), up to 7 chars vs. the expected
--                      2-char ball-strike form.
--   teamstats.start_l*/start_f*: pre-1940s data falls back to raw
--                      surnames ('Patterson') or uses malformed IDs
--                      ('brownr103'), up to 9 chars vs. standard
--                      8-char RetroIDs. All 19 starter slots widened
--                      uniformly for consistency.
--
-- Safety: VARCHAR widening is metadata-only in PostgreSQL (no table
-- rewrite, brief catalog lock). Reversible by narrowing later if all
-- rows still fit.
-- =============================================================

BEGIN;

ALTER TABLE retro.games     ALTER COLUMN starttime   TYPE VARCHAR(20);
ALTER TABLE retro.plays     ALTER COLUMN pitch_count TYPE VARCHAR(8);

ALTER TABLE retro.teamstats ALTER COLUMN start_l1  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_l2  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_l3  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_l4  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_l5  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_l6  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_l7  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_l8  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_l9  TYPE VARCHAR(10);

ALTER TABLE retro.teamstats ALTER COLUMN start_f1  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_f2  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_f3  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_f4  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_f5  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_f6  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_f7  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_f8  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_f9  TYPE VARCHAR(10);
ALTER TABLE retro.teamstats ALTER COLUMN start_f10 TYPE VARCHAR(10);

COMMIT;
