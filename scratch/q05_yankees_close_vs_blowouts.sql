-- Query 5: 1998 Yankees in close games vs. blowouts.
--
-- Definitions (per prompt; do not substitute conventional versions):
--   Close game   : margin ≤ 2 runs at any point from end of 7th through end of 9th.
--                  Extra-inning games tied at end of 9 ⇒ margin 0 ⇒ automatically close.
--   Blowout      : margin ≥ 7 runs at end of the 6th inning (end-of-6 state only).
--   Comeback     : blowout at end of 6 AND close by end of 9 (the overlap).
--
-- End-of-inning state drawn from retro.teamstats inn1..inn9 cumulative sums.
-- stattype='value' filter included per CLAUDE.md §4 item 4 (mandatory once
-- pre-1920 data lands; no-op against 1998, which is all 'value').
-- gametype='regular' to match the 162-game/114-48 historical record.
--
-- Staging: session-scoped TEMP TABLE tmp_yg_1998 holds one row per Yankees
-- game with both teams' end-of-N cumulative scores and the final. Three
-- sections read from it.

DROP TABLE IF EXISTS tmp_yg_1998;

CREATE TEMPORARY TABLE tmp_yg_1998 AS
WITH cum AS (
    SELECT
        ts.gid,
        ts.team,
        COALESCE(ts.inn1,0)+COALESCE(ts.inn2,0)+COALESCE(ts.inn3,0)
          +COALESCE(ts.inn4,0)+COALESCE(ts.inn5,0)+COALESCE(ts.inn6,0)                       AS r6,
        COALESCE(ts.inn1,0)+COALESCE(ts.inn2,0)+COALESCE(ts.inn3,0)
          +COALESCE(ts.inn4,0)+COALESCE(ts.inn5,0)+COALESCE(ts.inn6,0)
          +COALESCE(ts.inn7,0)                                                               AS r7,
        COALESCE(ts.inn1,0)+COALESCE(ts.inn2,0)+COALESCE(ts.inn3,0)
          +COALESCE(ts.inn4,0)+COALESCE(ts.inn5,0)+COALESCE(ts.inn6,0)
          +COALESCE(ts.inn7,0)+COALESCE(ts.inn8,0)                                           AS r8,
        COALESCE(ts.inn1,0)+COALESCE(ts.inn2,0)+COALESCE(ts.inn3,0)
          +COALESCE(ts.inn4,0)+COALESCE(ts.inn5,0)+COALESCE(ts.inn6,0)
          +COALESCE(ts.inn7,0)+COALESCE(ts.inn8,0)+COALESCE(ts.inn9,0)                       AS r9
    FROM retro.teamstats ts
    WHERE ts.stattype = 'value'
)
SELECT
    g.gid,
    g.date,
    g.wteam,
    CASE WHEN g.hometeam='NYA' THEN g.visteam ELSE g.hometeam END                             AS opp,
    CASE WHEN g.hometeam='NYA' THEN g.hruns   ELSE g.vruns   END                              AS y_final,
    CASE WHEN g.hometeam='NYA' THEN g.vruns   ELSE g.hruns   END                              AS o_final,
    y.r6 AS y_r6, y.r7 AS y_r7, y.r8 AS y_r8, y.r9 AS y_r9,
    o.r6 AS o_r6, o.r7 AS o_r7, o.r8 AS o_r8, o.r9 AS o_r9
FROM retro.games g
JOIN cum y ON g.gid = y.gid AND y.team  = 'NYA'
JOIN cum o ON g.gid = o.gid AND o.team <> 'NYA'
WHERE EXTRACT(YEAR FROM g.date) = 1998
  AND g.gametype = 'regular'
  AND (g.hometeam = 'NYA' OR g.visteam = 'NYA');


-- ---------- Sanity check ----------
\qecho ''
\qecho '=== Sanity check: 1998 Yankees regular-season record ==='
\qecho '(Expected: 162 games, 114-48-0 per historical record)'

SELECT
    COUNT(*)                                                                                  AS total_games,
    SUM(CASE WHEN wteam='NYA'                           THEN 1 ELSE 0 END)                    AS wins,
    SUM(CASE WHEN wteam IS NOT NULL AND wteam <> 'NYA'  THEN 1 ELSE 0 END)                    AS losses,
    SUM(CASE WHEN wteam IS NULL                         THEN 1 ELSE 0 END)                    AS ties,
    ROUND(
        SUM(CASE WHEN wteam='NYA' THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*),0),
        3)                                                                                    AS wpct
FROM tmp_yg_1998;


-- ---------- Section A: close games ----------
\qecho ''
\qecho '=== Section A: Yankees in close games, 1998 ==='
\qecho 'Close = margin ≤ 2 runs at any point from end of 7th through end of 9th (extras qualify automatically).'

SELECT
    COUNT(*)                                                                                  AS close_games,
    SUM(CASE WHEN wteam='NYA'                           THEN 1 ELSE 0 END)                    AS close_wins,
    SUM(CASE WHEN wteam IS NOT NULL AND wteam <> 'NYA'  THEN 1 ELSE 0 END)                    AS close_losses,
    ROUND(
        SUM(CASE WHEN wteam='NYA' THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*),0),
        3)                                                                                    AS close_wpct
FROM tmp_yg_1998
WHERE ABS(y_r7 - o_r7) <= 2
   OR ABS(y_r8 - o_r8) <= 2
   OR ABS(y_r9 - o_r9) <= 2;


-- ---------- Section B: blowouts ----------
\qecho ''
\qecho '=== Section B: Yankees in blowouts, 1998 ==='
\qecho 'Blowout = margin ≥ 7 runs at end of the 6th inning. Split by who led at end of 6.'

SELECT
    CASE WHEN y_r6 > o_r6 THEN 'Yankees led at end of 6'
                          ELSE 'Opponent led at end of 6' END                                 AS situation,
    COUNT(*)                                                                                  AS games,
    SUM(CASE WHEN wteam='NYA'                           THEN 1 ELSE 0 END)                    AS yankees_wins,
    SUM(CASE WHEN wteam IS NOT NULL AND wteam <> 'NYA'  THEN 1 ELSE 0 END)                    AS yankees_losses,
    ROUND(AVG(ABS(y_r6    - o_r6   ))::numeric, 2)                                            AS avg_margin_end_of_6,
    ROUND(AVG(ABS(y_final - o_final))::numeric, 2)                                            AS avg_final_margin,
    MIN(ABS(y_final - o_final))                                                               AS min_final_margin,
    MAX(ABS(y_final - o_final))                                                               AS max_final_margin
FROM tmp_yg_1998
WHERE ABS(y_r6 - o_r6) >= 7
GROUP BY situation
ORDER BY situation;


-- ---------- Section C: comeback overlap ----------
\qecho ''
\qecho '=== Section C: Comeback games (blowout at end of 6 AND close by end of 9) ==='

SELECT
    date                                                                                      AS game_date,
    opp                                                                                       AS opponent,
    y_r6    || '-' || o_r6                                                                    AS end_of_6_Y_vs_O,
    y_r9    || '-' || o_r9                                                                    AS end_of_9_Y_vs_O,
    y_final || '-' || o_final                                                                 AS final_Y_vs_O,
    CASE WHEN wteam = 'NYA' THEN 'Yankees'
         WHEN wteam IS NULL THEN 'tie'
         ELSE wteam END                                                                       AS winner,
    CASE WHEN y_r6 > o_r6 AND wteam <> 'NYA' THEN 'Opponent came back to win'
         WHEN o_r6 > y_r6 AND wteam =  'NYA' THEN 'Yankees came back to win'
         WHEN y_r6 > o_r6 AND wteam =  'NYA' THEN 'Yankees held lead to win'
         WHEN o_r6 > y_r6 AND wteam <> 'NYA' THEN 'Opponent held lead to win'
         ELSE 'other' END                                                                     AS narrative
FROM tmp_yg_1998
WHERE ABS(y_r6 - o_r6) >= 7
  AND (ABS(y_r7 - o_r7) <= 2
    OR ABS(y_r8 - o_r8) <= 2
    OR ABS(y_r9 - o_r9) <= 2)
ORDER BY date;

DROP TABLE IF EXISTS tmp_yg_1998;
