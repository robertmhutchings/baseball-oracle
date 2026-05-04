-- =============================================================
-- Phase 2 schema migration: forfeit BOOLEAN -> VARCHAR(2)
--
-- Motivation: Phase 2 boolean audit (2026-04-29) confirmed that
-- retro.games.forfeit is the only bool_col across all 4 ingest
-- spec functions that carries Retrosheet codes rather than
-- booleans. The corpus contains 8 non-empty values across 1938-
-- 1948 Negro League games:
--     Y x6  (1939, 1940, 1944, 1945, 1946, 1948)
--     H x2  (1938, both HOM193806191/2)
--
-- Per Retrosheet's gameinfo spec, forfeit is a single-char code:
--     V = forfeit awarded to visiting team
--     H = forfeit awarded to home team
--     T = tied / score-as-is
--     Y = forfeited (direction not specified) -- observed-only
-- The 1998 Phase 1 ingest worked because 1998 has zero forfeits.
--
-- The bug had TWO symptoms:
--   (a) HALT: 'H' raised ValueError in to_bool (surfaced 2026-04-28
--       dry-run at HOM193806191).
--   (b) SILENT CORRUPTION: 'Y' lowercased to 'y' which to_bool maps
--       to True, erasing the distinction between a "Y / not specified"
--       forfeit and an "H / awarded to home" forfeit. The 6 Y rows
--       had been silently miscoerced before any halt fired.
--
-- Decision: option (a) -- preserve verbatim per CLAUDE.md §7 Data
-- Source Principle, same shape as Item 22's attendance fix. forfeit
-- moves out of bool_cols in spec_games; passthrough only.
--
-- Sizing: VARCHAR(2). All observed values are 1 char; documented
-- Retrosheet codes (V/H/T) also 1 char; +1 headroom against
-- surprises.
--
-- Safety: BOOLEAN -> VARCHAR widening with USING. Real DB has no
-- 1998 rows with non-NULL forfeit; scratch DB's 1925/1955/1985
-- smoke-test years also have no non-NULL forfeit (per audit). So
-- the USING clause never fires on a non-NULL row in either DB.
-- Defensive mapping kept anyway: TRUE -> 'Y' (the only "truthy"
-- value the source ever produced); FALSE -> NULL (FALSE in this
-- column is meaningless -- the source never encodes a "no-forfeit"
-- value, only empty or a code).
-- =============================================================

BEGIN;

ALTER TABLE retro.games
    ALTER COLUMN forfeit TYPE VARCHAR(2)
    USING (CASE WHEN forfeit IS NULL THEN NULL
                WHEN forfeit THEN 'Y'
                ELSE NULL
           END);

COMMENT ON COLUMN retro.games.forfeit IS
    'Forfeit code, stored verbatim. Retrosheet spec: V=awarded to visitor, H=awarded to home, T=tied/score-as-is. Corpus also uses Y (forfeited, direction not specified). Empty / NULL means no forfeit.';

INSERT INTO retro.schema_version (version, notes) VALUES (
    'phase2-2026-04-29',
    'forfeit BOOLEAN -> VARCHAR(2) (Item 25): preserve Retrosheet code semantics. Surfaced via 2026-04-28 dry-run halt + boolean audit; only column at risk in any spec.'
);

COMMIT;
