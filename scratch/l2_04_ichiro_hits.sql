-- L2.4 — Ichiro Suzuki 2004 single-season hits = 262 (canonical record).
--
-- Ichiro is a tricky lookup: in MLB he goes by his given name "Ichiro",
-- not the family name. Resolve via Retrosheet's lookup conventions.
--
-- Aggregation: SUM(b_h) where b_h = singles + doubles + triples + HR
-- (per Retrosheet schema). Filter stattype='value' AND gametype='regular'.

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== Resolve Ichiro retroID — try multiple lookup forms =='
SELECT id, usename, lastname, fullname, debut_p, last_p
FROM retro.players
WHERE LOWER(lastname) = 'suzuki'
   AND (LOWER(usename) = 'ichiro'
        OR LOWER(fullname) LIKE '%ichiro%'
        OR LOWER(altname) LIKE '%ichiro%')
ORDER BY id;

\qecho ''
\qecho '== Backup lookup if Retrosheet stored the name unconventionally =='
SELECT id, usename, lastname, fullname, altname
FROM retro.players
WHERE LOWER(fullname) LIKE '%ichiro%'
   OR LOWER(altname) LIKE '%ichiro%'
   OR LOWER(usename) = 'ichiro'
ORDER BY id;

\qecho ''
\qecho '== Ichiro 2004 hits aggregation (using suzui001 per user prompt; verify above first) =='
WITH targets(target_id, label, target_year, target_hits) AS (
    VALUES ('suzui001'::varchar, 'Ichiro Suzuki', 2004, 262)
)
SELECT
    t.label,
    t.target_id,
    t.target_year,
    COALESCE(SUM(b.b_h), 0) AS db_hits,
    t.target_hits,
    COALESCE(SUM(b.b_h), 0) - t.target_hits AS diff
FROM targets t
LEFT JOIN retro.batting b
       ON b.id = t.target_id
      AND b.stattype = 'value'
      AND b.gametype = 'regular'
      AND EXTRACT(YEAR FROM b.date) = t.target_year
GROUP BY t.label, t.target_id, t.target_year, t.target_hits;

\qecho ''
\qecho '== Per-gametype hits breakdown for transparency =='
SELECT
    b.id,
    b.gametype,
    SUM(b.b_h) AS hits,
    COUNT(DISTINCT b.gid) AS games,
    SUM(b.b_ab) AS at_bats
FROM retro.batting b
WHERE b.id = 'suzui001'
  AND EXTRACT(YEAR FROM b.date) = 2004
  AND b.stattype = 'value'
GROUP BY b.id, b.gametype
ORDER BY b.gametype;

\qecho ''
\qecho '== Cross-check via plays.single+double+triple+hr =='
SELECT
    p.batter AS id,
    SUM(COALESCE(p.single,0) + COALESCE(p.double,0)
        + COALESCE(p.triple,0) + COALESCE(p.hr,0)) AS hits_via_plays,
    SUM(COALESCE(p.ab,0)) AS at_bats
FROM retro.plays p
JOIN retro.games g ON p.gid = g.gid
WHERE p.batter = 'suzui001'
  AND EXTRACT(YEAR FROM g.date) = 2004
  AND g.gametype = 'regular'
GROUP BY p.batter;
