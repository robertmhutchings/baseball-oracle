-- L1.2 — Date range per year in games + cross-table date sanity.
--
-- Purpose: confirm games.date for each year falls within YYYY-01-01..YYYY-12-31,
-- and that the per-game stat tables (batting/pitching/fielding/teamstats) carry
-- dates that match games.date for the same gid. Out-of-year dates would
-- indicate a gid→date parse corruption surviving ingest.

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== Per-year MIN/MAX/N games.date — should be within YYYY-01-01..YYYY-12-31 =='
SELECT
    EXTRACT(YEAR FROM date)::int  AS yr,
    MIN(date)                     AS min_date,
    MAX(date)                     AS max_date,
    COUNT(*)                      AS games_n,
    COUNT(DISTINCT date)          AS distinct_dates
FROM retro.games
GROUP BY yr
ORDER BY yr;

\qecho ''
\qecho '== games.date out-of-year sanity (should be 0 rows) =='
SELECT gid, date
FROM retro.games
WHERE EXTRACT(MONTH FROM date) < 1
   OR EXTRACT(MONTH FROM date) > 12
   OR EXTRACT(DAY FROM date) < 1
   OR EXTRACT(DAY FROM date) > 31;

\qecho ''
\qecho '== games.date NULL count (should be 0) =='
SELECT COUNT(*) AS null_dates FROM retro.games WHERE date IS NULL;

\qecho ''
\qecho '== Cross-table date consistency: any rows where stat-table date != games.date =='
\qecho '-- batting'
SELECT COUNT(*) AS mismatch
FROM retro.batting b JOIN retro.games g ON b.gid = g.gid
WHERE b.date IS DISTINCT FROM g.date;

\qecho '-- pitching'
SELECT COUNT(*) AS mismatch
FROM retro.pitching p JOIN retro.games g ON p.gid = g.gid
WHERE p.date IS DISTINCT FROM g.date;

\qecho '-- fielding'
SELECT COUNT(*) AS mismatch
FROM retro.fielding f JOIN retro.games g ON f.gid = g.gid
WHERE f.date IS DISTINCT FROM g.date;

\qecho '-- teamstats'
SELECT COUNT(*) AS mismatch
FROM retro.teamstats t JOIN retro.games g ON t.gid = g.gid
WHERE t.date IS DISTINCT FROM g.date;

\qecho ''
\qecho '== gid prefix consistency for non-Negro-League games =='
\qecho '-- For gids whose first 3 chars are a real team, the embedded YYYYMMDD should match games.date.'
\qecho '-- Per CLAUDE.md quirk #18, Negro League gids may not respect this; expect mismatches there only.'
SELECT
    CASE WHEN g.hometeam IS NOT NULL AND SUBSTRING(g.gid, 1, 3) = g.hometeam THEN 'home_prefix_ok'
         ELSE 'home_prefix_off'                                                                 END  AS prefix_status,
    COUNT(*) AS n,
    COUNT(*) FILTER (
        WHERE SUBSTRING(g.gid, 4, 8) <> TO_CHAR(g.date, 'YYYYMMDD')
    ) AS date_mismatch_n
FROM retro.games g
GROUP BY 1
ORDER BY 1;

\qecho ''
\qecho '== Sample date_mismatch rows (limit 20) — gid date-prefix differs from games.date =='
SELECT g.gid, g.date, SUBSTRING(g.gid, 4, 8) AS gid_date_str, g.hometeam, g.visteam
FROM retro.games g
WHERE SUBSTRING(g.gid, 4, 8) <> TO_CHAR(g.date, 'YYYYMMDD')
ORDER BY g.date
LIMIT 20;
