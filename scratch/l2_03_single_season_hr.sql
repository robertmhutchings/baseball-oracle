-- L2.3 — Single-season HR records.
--
-- Targets (regular season):
--   Roger Maris  1961 = 61
--   Mark McGwire 1998 = 70 (already verified Phase 1 Query #2)
--   Barry Bonds  2001 = 73
--
-- Same aggregation pattern as L2.2 but year-scoped.

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== Resolved retroIDs =='
SELECT id, usename, lastname
FROM retro.players
WHERE (usename = 'Roger' AND lastname = 'Maris')
   OR (usename = 'Mark'  AND lastname = 'McGwire')
   OR (usename = 'Barry' AND lastname = 'Bonds')
ORDER BY lastname;

\qecho ''
\qecho '== Single-season HR totals (regular season + value stattype) =='
WITH targets(target_id, label, target_year, target_hr) AS (
    VALUES ('marir101'::varchar, 'Roger Maris',   1961, 61),
           ('mcgwm001'::varchar, 'Mark McGwire',  1998, 70),
           ('bondb001'::varchar, 'Barry Bonds',   2001, 73)
)
SELECT
    t.label,
    t.target_id,
    t.target_year,
    COALESCE(SUM(b.b_hr), 0) AS db_hr,
    t.target_hr,
    COALESCE(SUM(b.b_hr), 0) - t.target_hr AS diff
FROM targets t
LEFT JOIN retro.batting b
       ON b.id = t.target_id
      AND b.stattype = 'value'
      AND b.gametype = 'regular'
      AND EXTRACT(YEAR FROM b.date) = t.target_year
GROUP BY t.label, t.target_id, t.target_year, t.target_hr
ORDER BY t.target_year;

\qecho ''
\qecho '== Per-gametype breakdown for transparency =='
SELECT
    b.id,
    EXTRACT(YEAR FROM b.date)::int AS yr,
    b.gametype,
    SUM(b.b_hr) AS hr,
    COUNT(DISTINCT b.gid) AS games
FROM retro.batting b
WHERE (b.id = 'marir101' AND EXTRACT(YEAR FROM b.date) = 1961)
   OR (b.id = 'mcgwm001' AND EXTRACT(YEAR FROM b.date) = 1998)
   OR (b.id = 'bondb001' AND EXTRACT(YEAR FROM b.date) = 2001)
  AND b.stattype = 'value'
GROUP BY b.id, yr, b.gametype
ORDER BY yr, b.id, b.gametype;
