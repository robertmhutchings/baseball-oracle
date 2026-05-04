-- L2.2 — Career HR for Babe Ruth, Hank Aaron, Barry Bonds.
--
-- Targets (regular season, published canon):
--   Ruth:   714
--   Aaron:  755
--   Bonds:  762
--
-- Aggregation source: retro.batting (one row per player per game per
-- stattype). A player can have multiple b_seq rows in one game; b_hr is
-- per-row, so SUM is correct.
--
-- Required filters:
--   stattype = 'value'        (per CLAUDE.md §4 #4: avoid double-count vs official)
--   gametype = 'regular'      (canon HR totals exclude postseason)
--
-- Player lookup is by usename + lastname per CLAUDE.md §4 #5.

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== Resolved retroIDs from biofile0 =='
SELECT id, usename, lastname, fullname, debut_p, last_p
FROM retro.players
WHERE (usename = 'Babe'  AND lastname = 'Ruth')
   OR (usename = 'Hank'  AND lastname = 'Aaron')
   OR (usename = 'Barry' AND lastname = 'Bonds')
ORDER BY lastname;

\qecho ''
\qecho '== Career HR totals (regular season + value stattype) =='
WITH targets(target_id, label, target_hr) AS (
    VALUES ('ruthb101'::varchar, 'Babe Ruth',    714),
           ('aaroh101'::varchar, 'Hank Aaron',   755),
           ('bondb001'::varchar, 'Barry Bonds',  762)
)
SELECT
    t.label,
    t.target_id,
    COALESCE(SUM(b.b_hr), 0) AS db_hr_regular,
    t.target_hr,
    COALESCE(SUM(b.b_hr), 0) - t.target_hr AS diff
FROM targets t
LEFT JOIN retro.batting b
       ON b.id = t.target_id
      AND b.stattype = 'value'
      AND b.gametype = 'regular'
GROUP BY t.label, t.target_id, t.target_hr
ORDER BY t.label;

\qecho ''
\qecho '== Per-gametype HR breakdown (transparency — confirms postseason is excluded) =='
SELECT
    b.id,
    b.gametype,
    SUM(b.b_hr) AS hr,
    COUNT(DISTINCT b.gid) AS games
FROM retro.batting b
WHERE b.id IN ('ruthb101','aaroh101','bondb001')
  AND b.stattype = 'value'
GROUP BY b.id, b.gametype
ORDER BY b.id, b.gametype;

\qecho ''
\qecho '== Cross-check via plays.hr (alternate aggregation source) =='
SELECT
    p.batter        AS id,
    SUM(p.hr)       AS plays_hr,
    COUNT(DISTINCT p.gid) AS games_with_hr
FROM retro.plays p
JOIN retro.games g ON p.gid = g.gid
WHERE p.batter IN ('ruthb101','aaroh101','bondb001')
  AND g.gametype = 'regular'
GROUP BY p.batter
ORDER BY p.batter;
