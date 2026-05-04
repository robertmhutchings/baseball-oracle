-- L2.1 — Games per year vs published schedule.
--
-- Cross-reference DB regular-season game count per year against historical
-- record. Critical: gametype='regular' filter, and we use COUNT(DISTINCT gid)
-- on retro.games (one row per game, gid PK — so COUNT(*) = COUNT(DISTINCT)
-- but DISTINCT is self-documenting).
--
-- Expected schedule shapes (per phase2_plan.md §5 layer 2):
--   1907–1903: ~140g/team (early era varies)
--   1904–1961: 154g/team schedule (AL); NL similar
--   1962–present: 162g/team schedule, with documented exceptions:
--     1972: strike-shortened (most teams 153–156)
--     1981: split-season strike (~105g)
--     1994: strike Aug+Sep (~112g)
--     1995: shortened to 144g (delayed start)
--     2020: COVID-shortened to 60g
--   Expansion: 1961 AL +2, 1962 NL +2, 1969 both +2, 1977 AL +2, 1993 NL +2,
--   1998 both +1.
--
-- Total games per league per year = (#teams × games_per_team) / 2
--   1904–60 AL: 8 teams × 154 / 2 = 616 games
--   1904–60 NL: 8 teams × 154 / 2 = 616 games  → ~1232 total
--   1961 AL: 10 × 162 / 2 = 810; NL still 8 × 154 / 2 = 616 → ~1426 total
--   1962+ both 10×162/2 = 810 each → ~1620 total
--   1969+ both 12×162/2 = 972 each → ~1944 total
--   1977+ AL 14×162/2 = 1134; NL still 12×162/2 = 972 → ~2106 total
--   1993+ NL 14×162/2 = 1134 → ~2268 total
--   1998+ both 15×162/2 = 1215; 14×162/2 = 1134 → ~2349 (or 2430 once both 15)

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== Per-year regular-season game count =='
SELECT
    EXTRACT(YEAR FROM date)::int AS yr,
    COUNT(DISTINCT gid)          AS regular_games
FROM retro.games
WHERE gametype = 'regular'
GROUP BY yr
ORDER BY yr;

\qecho ''
\qecho '== Distinct gametype values present (should include regular + postseason + exhibition) =='
SELECT gametype, COUNT(*) AS n
FROM retro.games
GROUP BY gametype
ORDER BY n DESC;

\qecho ''
\qecho '== Per-year breakdown by gametype (full enumeration) =='
SELECT
    EXTRACT(YEAR FROM date)::int AS yr,
    gametype,
    COUNT(DISTINCT gid)          AS gid_count
FROM retro.games
GROUP BY yr, gametype
ORDER BY yr, gametype;
