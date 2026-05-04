-- L1.1 — Row counts per (year, table) and grand totals.
--
-- Purpose: confirm DB matches checkpoint .ingest_progress.json. Any drift
-- indicates COPY-time data loss the script did not detect.
--
-- Year derivation:
--   games:                EXTRACT(YEAR FROM date)
--   batting/pitching/fielding/teamstats: EXTRACT(YEAR FROM date)
--   players_team_year:    year column directly
--   plays:                JOIN games ON plays.gid = games.gid (plays has no date column)
--
-- Reference tables also surfaced for completeness.

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== Reference table totals =='
SELECT 'teams'        AS table_name, COUNT(*) AS row_count FROM retro.teams
UNION ALL SELECT 'ballparks',  COUNT(*) FROM retro.ballparks
UNION ALL SELECT 'players',    COUNT(*) FROM retro.players
UNION ALL SELECT 'relatives',  COUNT(*) FROM retro.relatives
ORDER BY table_name;

\qecho ''
\qecho '== Year-scoped table grand totals =='
SELECT 'games'              AS table_name, COUNT(*) AS row_count FROM retro.games
UNION ALL SELECT 'players_team_year', COUNT(*) FROM retro.players_team_year
UNION ALL SELECT 'batting',           COUNT(*) FROM retro.batting
UNION ALL SELECT 'pitching',          COUNT(*) FROM retro.pitching
UNION ALL SELECT 'fielding',          COUNT(*) FROM retro.fielding
UNION ALL SELECT 'teamstats',         COUNT(*) FROM retro.teamstats
UNION ALL SELECT 'plays',             COUNT(*) FROM retro.plays
ORDER BY table_name;

\qecho ''
\qecho '== Per-year, per-table row counts (full enumeration, 117 years) =='
WITH per_year AS (
    SELECT EXTRACT(YEAR FROM date)::int AS yr, 'games'    AS tbl, COUNT(*) AS n FROM retro.games     GROUP BY 1
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, 'batting',     COUNT(*) FROM retro.batting   GROUP BY 1
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, 'pitching',    COUNT(*) FROM retro.pitching  GROUP BY 1
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, 'fielding',    COUNT(*) FROM retro.fielding  GROUP BY 1
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, 'teamstats',   COUNT(*) FROM retro.teamstats GROUP BY 1
    UNION ALL SELECT EXTRACT(YEAR FROM g.date)::int, 'plays',     COUNT(*) FROM retro.plays p JOIN retro.games g ON p.gid = g.gid GROUP BY 1
    UNION ALL SELECT year::int,                    'pty',         COUNT(*) FROM retro.players_team_year GROUP BY 1
)
SELECT
    yr,
    COALESCE(MAX(CASE WHEN tbl='games'     THEN n END), 0) AS games,
    COALESCE(MAX(CASE WHEN tbl='pty'       THEN n END), 0) AS players_team_year,
    COALESCE(MAX(CASE WHEN tbl='batting'   THEN n END), 0) AS batting,
    COALESCE(MAX(CASE WHEN tbl='pitching'  THEN n END), 0) AS pitching,
    COALESCE(MAX(CASE WHEN tbl='fielding'  THEN n END), 0) AS fielding,
    COALESCE(MAX(CASE WHEN tbl='teamstats' THEN n END), 0) AS teamstats,
    COALESCE(MAX(CASE WHEN tbl='plays'     THEN n END), 0) AS plays
FROM per_year
GROUP BY yr
ORDER BY yr;

\qecho ''
\qecho '== Zero-count cells (any table empty for a given year — RED FLAG) =='
WITH per_year AS (
    SELECT EXTRACT(YEAR FROM date)::int AS yr, 'games'    AS tbl, COUNT(*) AS n FROM retro.games     GROUP BY 1
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, 'batting',     COUNT(*) FROM retro.batting   GROUP BY 1
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, 'pitching',    COUNT(*) FROM retro.pitching  GROUP BY 1
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, 'fielding',    COUNT(*) FROM retro.fielding  GROUP BY 1
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, 'teamstats',   COUNT(*) FROM retro.teamstats GROUP BY 1
    UNION ALL SELECT EXTRACT(YEAR FROM g.date)::int, 'plays',     COUNT(*) FROM retro.plays p JOIN retro.games g ON p.gid = g.gid GROUP BY 1
    UNION ALL SELECT year::int,                    'pty',         COUNT(*) FROM retro.players_team_year GROUP BY 1
)
SELECT yr, tbl, n
FROM per_year
WHERE n = 0
ORDER BY yr, tbl;
