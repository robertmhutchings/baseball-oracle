-- Query 3: Top left-handed batters vs left-handed pitchers in 1998.
--
-- Definitions:
--   - Left-handed batter = players.bats = 'L' (true LH batter; switch-hitters
--     excluded). Using players.bats instead of plays.bathand because
--     plays.bathand = 'B' on ~16% of 1998 plays represents switch-hitter PAs
--     where the event string did not encode which side they batted that PA,
--     not a separate category of batter.
--   - LHP = plays.pithand = 'L'.
--   - Hit = single + double + triple + hr (each a 0/1 per-play flag).
--   - At-bat = p.ab (0/1 per-play flag; walks, HBP, SF, SH are p.ab = 0).
--   - Min 150 ABs vs LHP.  (Per Section 8 "dynamism philosophy": threshold
--     is surfaced in the output header, not hidden in the query.)
-- Ordering: BA desc, tiebreak by AB volume desc.

\qecho 'Top LH batters vs LHP in 1998 — minimum 150 at-bats. (Use the 50-AB version to see smaller samples.)'

SELECT
    pl.usename || ' ' || pl.lastname                                              AS player_name,
    SUM(p.ab)                                                                      AS at_bats_vs_lhp,
    SUM(COALESCE(p.single,0) + COALESCE(p.double,0)
        + COALESCE(p.triple,0) + COALESCE(p.hr,0))                                 AS hits_vs_lhp,
    ROUND(
        SUM(COALESCE(p.single,0) + COALESCE(p.double,0)
            + COALESCE(p.triple,0) + COALESCE(p.hr,0))::numeric
        / NULLIF(SUM(p.ab), 0),
        4)                                                                         AS batting_avg_vs_lhp,
    SUM(COALESCE(p.hr,   0))                                                       AS home_runs_vs_lhp,
    SUM(COALESCE(p.k,    0))                                                       AS strikeouts_vs_lhp,
    SUM(COALESCE(p.walk, 0))                                                       AS walks_vs_lhp
FROM retro.plays   p
JOIN retro.games   g  ON p.gid    = g.gid
JOIN retro.players pl ON p.batter = pl.id
WHERE EXTRACT(YEAR FROM g.date) = 1998
  AND p.pithand = 'L'
  AND pl.bats   = 'L'
GROUP BY pl.id, pl.usename, pl.lastname
HAVING SUM(p.ab) >= 150
ORDER BY batting_avg_vs_lhp DESC, at_bats_vs_lhp DESC
LIMIT 10;
