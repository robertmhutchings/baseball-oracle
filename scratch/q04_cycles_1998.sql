-- Query 4: Did anyone hit for the cycle in 1998?
--
-- Cycle = at least one single, one double, one triple, and one HR by the same
-- batter in the same game. Natural cycle = those four types occurred in
-- canonical order (1B first, then 2B, then 3B, then HR) by their FIRST
-- occurrence of each type (plays.pn ordering).
--
-- Notes:
--   - plays.pn is strictly monotonic within a game, so MIN(pn where type=1)
--     identifies the first occurrence of that type chronologically.
--   - hit_sequence displays the four hit types ordered by first-occurrence pn,
--     each annotated with its first-occurrence inning: e.g. "1B(i2), 2B(i4),
--     3B(i6), HR(i8)".

\qecho 'Cycles in 1998 — single + double + triple + HR by the same batter in the same game. natural_cycle=TRUE if the first of each type occurred in canonical order.'

WITH per_game AS (
    SELECT
        p.batter,
        p.gid,
        p.batteam,
        p.ballpark,
        SUM(p.single) AS singles,
        SUM(p.double) AS doubles,
        SUM(p.triple) AS triples,
        SUM(p.hr)     AS home_runs,
        MIN(CASE WHEN p.single = 1 THEN p.pn     END) AS first_1b_pn,
        MIN(CASE WHEN p.double = 1 THEN p.pn     END) AS first_2b_pn,
        MIN(CASE WHEN p.triple = 1 THEN p.pn     END) AS first_3b_pn,
        MIN(CASE WHEN p.hr     = 1 THEN p.pn     END) AS first_hr_pn,
        MIN(CASE WHEN p.single = 1 THEN p.inning END) AS first_1b_inning,
        MIN(CASE WHEN p.double = 1 THEN p.inning END) AS first_2b_inning,
        MIN(CASE WHEN p.triple = 1 THEN p.inning END) AS first_3b_inning,
        MIN(CASE WHEN p.hr     = 1 THEN p.inning END) AS first_hr_inning
    FROM retro.plays p
    JOIN retro.games g ON p.gid = g.gid
    WHERE EXTRACT(YEAR FROM g.date) = 1998
    GROUP BY p.batter, p.gid, p.batteam, p.ballpark
    HAVING SUM(p.single) >= 1
       AND SUM(p.double) >= 1
       AND SUM(p.triple) >= 1
       AND SUM(p.hr)     >= 1
)
SELECT
    pl.usename || ' ' || pl.lastname                                                AS player_name,
    g.date                                                                           AS game_date,
    CASE WHEN c.batteam = g.hometeam THEN g.visteam ELSE g.hometeam END              AS opposing_team,
    split_part(bp.name, ';', 1)                                                      AS ballpark_name,
    c.singles,
    c.doubles,
    c.triples,
    c.home_runs,
    (c.first_1b_pn < c.first_2b_pn
     AND c.first_2b_pn < c.first_3b_pn
     AND c.first_3b_pn < c.first_hr_pn)                                              AS natural_cycle,
    hit_seq.hit_sequence
FROM per_game         c
JOIN retro.games      g  ON c.gid      = g.gid
JOIN retro.players    pl ON c.batter   = pl.id
JOIN retro.ballparks  bp ON c.ballpark = bp.parkid
LEFT JOIN LATERAL (
    SELECT string_agg(t.label, ', ' ORDER BY t.pn_val) AS hit_sequence
    FROM unnest(
        ARRAY[c.first_1b_pn, c.first_2b_pn, c.first_3b_pn, c.first_hr_pn],
        ARRAY[
            '1B(i' || c.first_1b_inning || ')',
            '2B(i' || c.first_2b_inning || ')',
            '3B(i' || c.first_3b_inning || ')',
            'HR(i' || c.first_hr_inning || ')'
        ]
    ) AS t(pn_val, label)
) hit_seq ON TRUE
ORDER BY g.date;
