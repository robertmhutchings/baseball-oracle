-- L1.3 — stattype distribution per year for batting/pitching/fielding/teamstats.
--
-- Expected: 'value' dominant everywhere. Non-'value' rows (official/lower/upper)
-- cluster pre-1920 and Negro League years (per CLAUDE.md §4 item 4).
-- Any year >5% non-value AFTER 1925 in a non-Negro-League team-context is a
-- potential ingest artifact worth flagging.

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== Global stattype distribution (all years, all 4 tables combined) =='
WITH all_st AS (
    SELECT stattype FROM retro.batting
    UNION ALL SELECT stattype FROM retro.pitching
    UNION ALL SELECT stattype FROM retro.fielding
    UNION ALL SELECT stattype FROM retro.teamstats
)
SELECT stattype, COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS pct
FROM all_st
GROUP BY stattype
ORDER BY n DESC;

\qecho ''
\qecho '== Per-table stattype distribution =='
SELECT 'batting'   AS tbl, stattype, COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY 'batting'), 4) AS pct
FROM retro.batting GROUP BY stattype
UNION ALL
SELECT 'pitching',  stattype, COUNT(*),
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY 'pitching'), 4)
FROM retro.pitching GROUP BY stattype
UNION ALL
SELECT 'fielding',  stattype, COUNT(*),
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY 'fielding'), 4)
FROM retro.fielding GROUP BY stattype
UNION ALL
SELECT 'teamstats', stattype, COUNT(*),
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY 'teamstats'), 4)
FROM retro.teamstats GROUP BY stattype
ORDER BY tbl, n DESC;

\qecho ''
\qecho '== Per-year non-value rate (batting) — surface only years with any non-value rows =='
WITH per_year AS (
    SELECT EXTRACT(YEAR FROM date)::int AS yr,
           COUNT(*) FILTER (WHERE stattype <> 'value') AS non_value_n,
           COUNT(*) AS total_n
    FROM retro.batting GROUP BY 1
)
SELECT yr,
       non_value_n,
       total_n,
       ROUND(100.0 * non_value_n / total_n, 4) AS non_value_pct
FROM per_year
WHERE non_value_n > 0
ORDER BY yr;

\qecho ''
\qecho '== Per-year non-value rate (pitching) =='
WITH per_year AS (
    SELECT EXTRACT(YEAR FROM date)::int AS yr,
           COUNT(*) FILTER (WHERE stattype <> 'value') AS non_value_n,
           COUNT(*) AS total_n
    FROM retro.pitching GROUP BY 1
)
SELECT yr, non_value_n, total_n,
       ROUND(100.0 * non_value_n / total_n, 4) AS non_value_pct
FROM per_year WHERE non_value_n > 0 ORDER BY yr;

\qecho ''
\qecho '== Per-year non-value rate (fielding) =='
WITH per_year AS (
    SELECT EXTRACT(YEAR FROM date)::int AS yr,
           COUNT(*) FILTER (WHERE stattype <> 'value') AS non_value_n,
           COUNT(*) AS total_n
    FROM retro.fielding GROUP BY 1
)
SELECT yr, non_value_n, total_n,
       ROUND(100.0 * non_value_n / total_n, 4) AS non_value_pct
FROM per_year WHERE non_value_n > 0 ORDER BY yr;

\qecho ''
\qecho '== Per-year non-value rate (teamstats) =='
WITH per_year AS (
    SELECT EXTRACT(YEAR FROM date)::int AS yr,
           COUNT(*) FILTER (WHERE stattype <> 'value') AS non_value_n,
           COUNT(*) AS total_n
    FROM retro.teamstats GROUP BY 1
)
SELECT yr, non_value_n, total_n,
       ROUND(100.0 * non_value_n / total_n, 4) AS non_value_pct
FROM per_year WHERE non_value_n > 0 ORDER BY yr;

\qecho ''
\qecho '== Modern-era (>=1960) non-value spotcheck — RED FLAG if any year >0.1% =='
WITH all_modern AS (
    SELECT EXTRACT(YEAR FROM date)::int AS yr, stattype FROM retro.batting   WHERE EXTRACT(YEAR FROM date) >= 1960
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, stattype FROM retro.pitching  WHERE EXTRACT(YEAR FROM date) >= 1960
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, stattype FROM retro.fielding  WHERE EXTRACT(YEAR FROM date) >= 1960
    UNION ALL SELECT EXTRACT(YEAR FROM date)::int, stattype FROM retro.teamstats WHERE EXTRACT(YEAR FROM date) >= 1960
)
SELECT yr,
       COUNT(*) FILTER (WHERE stattype <> 'value') AS non_value_n,
       COUNT(*) AS total_n,
       ROUND(100.0 * COUNT(*) FILTER (WHERE stattype <> 'value') / COUNT(*), 6) AS non_value_pct
FROM all_modern
GROUP BY yr
HAVING COUNT(*) FILTER (WHERE stattype <> 'value') > 0
ORDER BY yr;
