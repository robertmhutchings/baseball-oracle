-- L1.6 — games ↔ teamstats symmetry.
--
-- Per CLAUDE.md §4 item 6: each game appears in teamstats twice (one row
-- per team) per stattype. So for any (gid, stattype), expect exactly 2
-- distinct teams. Asymmetry would indicate the ingest dropped half a game.
--
-- Two checks:
--   (a) Per (gid, stattype): expect exactly 2 rows AND 2 distinct teams.
--   (b) gids in games not in teamstats, and vice versa.

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== Per (gid, stattype) row count distribution =='
WITH per_gid_stattype AS (
    SELECT gid, stattype, COUNT(*) AS n_rows, COUNT(DISTINCT team) AS n_teams
    FROM retro.teamstats
    GROUP BY gid, stattype
)
SELECT n_rows, n_teams, COUNT(*) AS n_combos
FROM per_gid_stattype
GROUP BY n_rows, n_teams
ORDER BY n_combos DESC;

\qecho ''
\qecho '== Per gid: total teamstats row count distribution (across all stattypes) =='
WITH per_gid AS (
    SELECT gid, COUNT(*) AS n_rows, COUNT(DISTINCT team) AS n_teams,
           COUNT(DISTINCT stattype) AS n_stattypes
    FROM retro.teamstats
    GROUP BY gid
)
SELECT n_rows, n_teams, n_stattypes, COUNT(*) AS n_gids
FROM per_gid
GROUP BY n_rows, n_teams, n_stattypes
ORDER BY n_gids DESC
LIMIT 20;

\qecho ''
\qecho '== gids in games but NOT in teamstats — RED FLAG =='
SELECT g.gid, g.date, g.hometeam, g.visteam
FROM retro.games g
WHERE NOT EXISTS (SELECT 1 FROM retro.teamstats t WHERE t.gid = g.gid)
ORDER BY g.date
LIMIT 50;

\qecho ''
\qecho '== gids in teamstats but NOT in games — RED FLAG =='
SELECT DISTINCT ts.gid
FROM retro.teamstats ts
WHERE NOT EXISTS (SELECT 1 FROM retro.games g WHERE g.gid = ts.gid)
ORDER BY ts.gid
LIMIT 50;

\qecho ''
\qecho '== Anomalous (gid, stattype) combos — anything other than 2 rows / 2 teams =='
WITH per_gid_stattype AS (
    SELECT gid, stattype, COUNT(*) AS n_rows, COUNT(DISTINCT team) AS n_teams
    FROM retro.teamstats
    GROUP BY gid, stattype
)
SELECT pgs.gid, g.date, g.hometeam, g.visteam, pgs.stattype, pgs.n_rows, pgs.n_teams
FROM per_gid_stattype pgs
JOIN retro.games g ON pgs.gid = g.gid
WHERE NOT (pgs.n_rows = 2 AND pgs.n_teams = 2)
ORDER BY g.date, pgs.gid, pgs.stattype
LIMIT 50;

\qecho ''
\qecho '== Cross-check: every game has exactly 2 distinct teams in teamstats (any stattype) =='
WITH per_gid AS (
    SELECT g.gid, COUNT(DISTINCT ts.team) AS n_distinct_teams
    FROM retro.games g
    LEFT JOIN retro.teamstats ts ON g.gid = ts.gid
    GROUP BY g.gid
)
SELECT n_distinct_teams, COUNT(*) AS n_gids
FROM per_gid
GROUP BY n_distinct_teams
ORDER BY n_distinct_teams;
