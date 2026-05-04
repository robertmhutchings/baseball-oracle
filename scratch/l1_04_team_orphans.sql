-- L1.4 — Team-code orphans.
--
-- Purpose: surface team codes that appear in stat tables but not in
-- retro.teams. With no FKs, orphans are quiet — this query catches them.
-- Negro League and Federal League franchises are the most likely orphan
-- sources; if any orphan appears for a modern era (>=1960), it indicates
-- teams.csv is missing a real franchise.

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== games.hometeam orphans (codes not in retro.teams) =='
SELECT g.hometeam AS team, COUNT(*) AS n,
       MIN(EXTRACT(YEAR FROM g.date))::int AS first_yr,
       MAX(EXTRACT(YEAR FROM g.date))::int AS last_yr
FROM retro.games g
LEFT JOIN retro.teams t ON g.hometeam = t.team
WHERE t.team IS NULL
GROUP BY g.hometeam
ORDER BY g.hometeam;

\qecho ''
\qecho '== games.visteam orphans =='
SELECT g.visteam AS team, COUNT(*) AS n,
       MIN(EXTRACT(YEAR FROM g.date))::int AS first_yr,
       MAX(EXTRACT(YEAR FROM g.date))::int AS last_yr
FROM retro.games g
LEFT JOIN retro.teams t ON g.visteam = t.team
WHERE t.team IS NULL
GROUP BY g.visteam
ORDER BY g.visteam;

\qecho ''
\qecho '== teamstats.team orphans =='
SELECT ts.team AS team, COUNT(*) AS n,
       MIN(EXTRACT(YEAR FROM ts.date))::int AS first_yr,
       MAX(EXTRACT(YEAR FROM ts.date))::int AS last_yr
FROM retro.teamstats ts
LEFT JOIN retro.teams t ON ts.team = t.team
WHERE t.team IS NULL
GROUP BY ts.team
ORDER BY ts.team;

\qecho ''
\qecho '== batting.team orphans =='
SELECT b.team AS team, COUNT(*) AS n,
       MIN(EXTRACT(YEAR FROM b.date))::int AS first_yr,
       MAX(EXTRACT(YEAR FROM b.date))::int AS last_yr
FROM retro.batting b
LEFT JOIN retro.teams t ON b.team = t.team
WHERE t.team IS NULL
GROUP BY b.team
ORDER BY b.team;

\qecho ''
\qecho '== pitching.team orphans =='
SELECT p.team AS team, COUNT(*) AS n,
       MIN(EXTRACT(YEAR FROM p.date))::int AS first_yr,
       MAX(EXTRACT(YEAR FROM p.date))::int AS last_yr
FROM retro.pitching p
LEFT JOIN retro.teams t ON p.team = t.team
WHERE t.team IS NULL
GROUP BY p.team
ORDER BY p.team;

\qecho ''
\qecho '== fielding.team orphans =='
SELECT f.team AS team, COUNT(*) AS n,
       MIN(EXTRACT(YEAR FROM f.date))::int AS first_yr,
       MAX(EXTRACT(YEAR FROM f.date))::int AS last_yr
FROM retro.fielding f
LEFT JOIN retro.teams t ON f.team = t.team
WHERE t.team IS NULL
GROUP BY f.team
ORDER BY f.team;

\qecho ''
\qecho '== plays.batteam / plays.pitteam orphans =='
SELECT 'batteam' AS col, p.batteam AS team, COUNT(*) AS n
FROM retro.plays p
LEFT JOIN retro.teams t ON p.batteam = t.team
WHERE p.batteam IS NOT NULL AND t.team IS NULL
GROUP BY p.batteam
UNION ALL
SELECT 'pitteam', p.pitteam, COUNT(*)
FROM retro.plays p
LEFT JOIN retro.teams t ON p.pitteam = t.team
WHERE p.pitteam IS NOT NULL AND t.team IS NULL
GROUP BY p.pitteam
ORDER BY col, team;

\qecho ''
\qecho '== players_team_year.team orphans =='
SELECT pty.team AS team, COUNT(*) AS n,
       MIN(pty.year)::int AS first_yr,
       MAX(pty.year)::int AS last_yr
FROM retro.players_team_year pty
LEFT JOIN retro.teams t ON pty.team = t.team
WHERE t.team IS NULL
GROUP BY pty.team
ORDER BY pty.team;
