-- =============================================================
-- Phase 2 schema migration: attendance INTEGER -> VARCHAR(24)
--
-- Motivation: Item 22 in CLAUDE.md §4a. Phase 2 sentinel scan
-- (2026-04-27) surfaced 8 rows in 1938-1948 Negro League gameinfo
-- with hedged attendance values that Retrosheet preserved verbatim
-- from the source: 'hundreds', '<1000', '700?', '6500?', '1000c.',
-- '5000c.', '6000c.' (x2). Each shape encodes information that
-- NULL would erase (order-of-magnitude, upper bound, uncertain
-- estimate, circa).
--
-- Decision (PM 2026-04-28): option (a) -- preserve verbatim per
-- CLAUDE.md §7 Data Source Principle. The "hedged value -> numeric
-- or NULL" interpretation becomes a query-time / agent-layer
-- decision, not a schema decision. Numeric queries still work via
-- regex cast, e.g.:
--     WHERE attendance ~ '^\d+$' AND attendance::int > 50000
--
-- Sizing: longest observed non-numeric value is 21 chars
-- ('8.1250000000000003E-2'). VARCHAR(24) gives 3 chars headroom.
-- Largest numeric attendance observed is 115,400 (6 chars), so
-- numerics fit comfortably.
--
-- Side effect: 5 additional 1941-1943 rows with decimal-fraction
-- values ('0.125', '0.0625', '0.075', '8.125...E-2', '6.944...E-2')
-- will now load as strings rather than halting. These are
-- suspected row-misalignment artifacts (CLAUDE.md Item 24, decimal
-- shape) and will be investigated under that item; the VARCHAR
-- widening is incidentally permissive of them but does NOT
-- constitute their fix. Item 24 work will revisit.
--
-- Safety: INTEGER -> VARCHAR is a widening cast; existing numeric
-- values render as their decimal text representation (115400 ->
-- '115400'). Real DB has no rows beyond Phase 1's 1998 load.
-- =============================================================

BEGIN;

ALTER TABLE retro.games
    ALTER COLUMN attendance TYPE VARCHAR(24)
    USING (CASE WHEN attendance IS NULL THEN NULL
                ELSE attendance::text
           END);

COMMENT ON COLUMN retro.games.attendance IS
    'Attendance count, stored verbatim. Usually numeric; pre-modern Negro League games (1938-1948) include hedged values like ''hundreds'', ''<1000'', ''6000c.''. Cast with attendance::int when filtering for numerics.';

INSERT INTO retro.schema_version (version, notes) VALUES (
    'phase2-2026-04-28',
    'attendance INTEGER -> VARCHAR(24) to preserve hedged Retrosheet values verbatim (Item 22). Decimal-fraction misalignment artifacts (Item 24) ride along incidentally.'
);

COMMIT;
