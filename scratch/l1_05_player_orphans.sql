-- L1.5 — Player-ID orphans in plays.
--
-- Purpose: surface plays.batter / plays.pitcher values that don't resolve
-- to a row in retro.players. Per CLAUDE.md quirk #17, Retrosheet falls back
-- to surname strings (and occasionally 9-char IDs) when no canonical RetroID
-- was assigned — almost exclusively for old / Negro League games. Modern
-- orphans would indicate biofile0 is missing real players.

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== Total orphan counts (plays.batter / plays.pitcher not in retro.players) =='
SELECT 'batter'  AS col,
       COUNT(*) FILTER (WHERE pl.id IS NULL) AS orphan_n,
       COUNT(*)                              AS total_n,
       ROUND(100.0 * COUNT(*) FILTER (WHERE pl.id IS NULL) / COUNT(*), 4) AS orphan_pct
FROM retro.plays p LEFT JOIN retro.players pl ON p.batter = pl.id
UNION ALL
SELECT 'pitcher',
       COUNT(*) FILTER (WHERE pl.id IS NULL),
       COUNT(*),
       ROUND(100.0 * COUNT(*) FILTER (WHERE pl.id IS NULL) / COUNT(*), 4)
FROM retro.plays p LEFT JOIN retro.players pl ON p.pitcher = pl.id;

\qecho ''
\qecho '== Orphan plays.batter by year (only years with any) =='
WITH orphans AS (
    SELECT EXTRACT(YEAR FROM g.date)::int AS yr, p.batter
    FROM retro.plays p
    JOIN retro.games g ON p.gid = g.gid
    LEFT JOIN retro.players pl ON p.batter = pl.id
    WHERE p.batter IS NOT NULL AND pl.id IS NULL
)
SELECT yr, COUNT(*) AS orphan_play_rows, COUNT(DISTINCT batter) AS distinct_orphan_ids
FROM orphans
GROUP BY yr
ORDER BY yr;

\qecho ''
\qecho '== Orphan plays.pitcher by year =='
WITH orphans AS (
    SELECT EXTRACT(YEAR FROM g.date)::int AS yr, p.pitcher
    FROM retro.plays p
    JOIN retro.games g ON p.gid = g.gid
    LEFT JOIN retro.players pl ON p.pitcher = pl.id
    WHERE p.pitcher IS NOT NULL AND pl.id IS NULL
)
SELECT yr, COUNT(*) AS orphan_play_rows, COUNT(DISTINCT pitcher) AS distinct_orphan_ids
FROM orphans
GROUP BY yr
ORDER BY yr;

\qecho ''
\qecho '== Sample of orphan batter IDs (first 30 distinct, with character-length distribution) =='
WITH orphans AS (
    SELECT DISTINCT p.batter
    FROM retro.plays p
    LEFT JOIN retro.players pl ON p.batter = pl.id
    WHERE p.batter IS NOT NULL AND pl.id IS NULL
)
SELECT batter, LENGTH(batter) AS id_len
FROM orphans
ORDER BY batter
LIMIT 30;

\qecho ''
\qecho '== Length distribution of orphan batter IDs =='
WITH orphans AS (
    SELECT DISTINCT p.batter
    FROM retro.plays p
    LEFT JOIN retro.players pl ON p.batter = pl.id
    WHERE p.batter IS NOT NULL AND pl.id IS NULL
)
SELECT LENGTH(batter) AS id_len, COUNT(*) AS distinct_ids
FROM orphans
GROUP BY id_len
ORDER BY id_len;

\qecho ''
\qecho '== Modern-era (>=1960) orphan batter IDs — RED FLAG if any =='
WITH orphans AS (
    SELECT DISTINCT p.batter, EXTRACT(YEAR FROM g.date)::int AS yr
    FROM retro.plays p
    JOIN retro.games g ON p.gid = g.gid
    LEFT JOIN retro.players pl ON p.batter = pl.id
    WHERE p.batter IS NOT NULL AND pl.id IS NULL AND EXTRACT(YEAR FROM g.date) >= 1960
)
SELECT yr, batter
FROM orphans
ORDER BY yr, batter
LIMIT 50;

\qecho ''
\qecho '== Modern-era (>=1960) orphan pitcher IDs — RED FLAG if any =='
WITH orphans AS (
    SELECT DISTINCT p.pitcher, EXTRACT(YEAR FROM g.date)::int AS yr
    FROM retro.plays p
    JOIN retro.games g ON p.gid = g.gid
    LEFT JOIN retro.players pl ON p.pitcher = pl.id
    WHERE p.pitcher IS NOT NULL AND pl.id IS NULL AND EXTRACT(YEAR FROM g.date) >= 1960
)
SELECT yr, pitcher
FROM orphans
ORDER BY yr, pitcher
LIMIT 50;
