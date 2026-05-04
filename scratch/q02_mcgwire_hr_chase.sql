WITH mcgwire AS (
    SELECT id FROM retro.players WHERE usename = 'Mark' AND lastname = 'McGwire'
)
SELECT
    ROW_NUMBER() OVER (ORDER BY g.date, p.inning, p.pn)           AS hr_number,
    g.date                                                         AS game_date,
    CASE WHEN p.batteam = g.hometeam THEN g.visteam
         ELSE g.hometeam END                                       AS opposing_team,
    bp.name                                                        AS ballpark_name,
    p.inning,
    pl.usename || ' ' || pl.lastname                               AS pitcher_name,
    p.pitch_count                                                  AS ball_strike,
    CASE
        (CASE WHEN p.br1_pre IS NOT NULL THEN 1 ELSE 0 END
       + CASE WHEN p.br2_pre IS NOT NULL THEN 1 ELSE 0 END
       + CASE WHEN p.br3_pre IS NOT NULL THEN 1 ELSE 0 END)
        WHEN 0 THEN 'solo'
        WHEN 1 THEN '2-run'
        WHEN 2 THEN '3-run'
        WHEN 3 THEN 'grand slam'
    END                                                            AS runners_on
FROM retro.plays    p
JOIN retro.games    g  ON p.gid      = g.gid
JOIN retro.ballparks bp ON p.ballpark = bp.parkid
JOIN retro.players  pl ON p.pitcher  = pl.id
WHERE p.batter = (SELECT id FROM mcgwire)
  AND p.hr = 1
  AND EXTRACT(YEAR FROM g.date) = 1998
ORDER BY g.date, p.inning, p.pn;
