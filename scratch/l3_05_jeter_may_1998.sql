-- L3.5 — Jeter HRs in May 1998 (Phase 1 Q1 baseline = 4 HRs).
--
-- Phase 1 baseline (per CLAUDE.md §6 acceptance criteria):
--   4 HRs: 5/2 vs KCA, 5/6 vs TEX, 5/13 vs TEX, 5/15 vs MIN.
--
-- Aggregation source: retro.plays (per Phase 1 Q2 pattern).
-- No stattype filter (plays is event-oriented per CLAUDE.md §4 #7).
-- gametype filter not added — May is regular season anyway, but defensive.

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho 'Jeter HRs in May 1998 — expected 4 HRs (5/2 KCA, 5/6 TEX, 5/13 TEX, 5/15 MIN).'

WITH jeter AS (
    SELECT id FROM retro.players WHERE usename = 'Derek' AND lastname = 'Jeter'
)
SELECT
    g.date                                                          AS game_date,
    CASE WHEN p.batteam = g.hometeam THEN g.visteam
         ELSE g.hometeam END                                        AS opposing_team,
    p.inning,
    pl.usename || ' ' || pl.lastname                                AS pitcher_name,
    p.pitch_count                                                   AS ball_strike,
    CASE
        (CASE WHEN p.br1_pre IS NOT NULL THEN 1 ELSE 0 END
       + CASE WHEN p.br2_pre IS NOT NULL THEN 1 ELSE 0 END
       + CASE WHEN p.br3_pre IS NOT NULL THEN 1 ELSE 0 END)
        WHEN 0 THEN 'solo'
        WHEN 1 THEN '2-run'
        WHEN 2 THEN '3-run'
        WHEN 3 THEN 'grand slam'
    END                                                             AS runners_on
FROM retro.plays    p
JOIN retro.games    g  ON p.gid    = g.gid
JOIN retro.players  pl ON p.pitcher = pl.id
WHERE p.batter = (SELECT id FROM jeter)
  AND p.hr = 1
  AND g.date BETWEEN '1998-05-01' AND '1998-05-31'
  AND g.gametype = 'regular'
ORDER BY g.date, p.inning, p.pn;

\qecho ''
\qecho '-- Summary count:'
WITH jeter AS (
    SELECT id FROM retro.players WHERE usename = 'Derek' AND lastname = 'Jeter'
)
SELECT
    COUNT(*) AS may_1998_hrs
FROM retro.plays  p
JOIN retro.games  g ON p.gid = g.gid
WHERE p.batter = (SELECT id FROM jeter)
  AND p.hr = 1
  AND g.date BETWEEN '1998-05-01' AND '1998-05-31'
  AND g.gametype = 'regular';
