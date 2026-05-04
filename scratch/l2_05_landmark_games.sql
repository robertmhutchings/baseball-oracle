-- L2.5 — Landmark games spot-check.
--
-- Four era-spanning games. For each, surface gameinfo + per-team teamstats
-- runs/hits and a key-play row, then cross-check vs Baseball-Reference.
--
-- Targets:
--   1923-04-18 Yankee Stadium opener: NYA 4 BOS 1 (Ruth 3-run HR)
--   1956-10-08 Larsen perfect game (WS G5): NYA 2 BRO 0 (no hits/walks for BRO)
--   1974-04-08 Aaron 715: ATL 7 LAN 4 (HR off Al Downing in 4th)
--   2001-11-04 WS G7: ARI 3 NYA 2 (Luis Gonzalez walk-off vs Mariano Rivera)
--
-- We look up games by date+matchup rather than guessing gids — gid format
-- can vary (game-number suffix). All 4 games are home-team-hosted regular
-- naming so gid prefix follows the canonical TTT+YYYYMMDD+N pattern.

\pset format aligned
\pset border 2
\pset null '(null)'

-- =====================================================================
\qecho '== GAME 1: 1923-04-18 NYA vs BOS — Yankee Stadium opener =='
-- =====================================================================
SELECT g.gid, g.date, g.hometeam, g.visteam, g.site, g.vruns, g.hruns,
       g.attendance, g.gametype
FROM retro.games g
WHERE g.date = '1923-04-18' AND g.hometeam = 'NYA' AND g.visteam = 'BOS';

\qecho '-- Per-team box for that gid:'
SELECT ts.gid, ts.team, ts.b_h AS hits, ts.b_r AS runs,
       ts.b_hr AS hr, ts.d_e AS errors_allowed, ts.lob
FROM retro.teamstats ts
WHERE ts.gid IN (SELECT gid FROM retro.games WHERE date='1923-04-18' AND hometeam='NYA' AND visteam='BOS')
  AND ts.stattype = 'value'
ORDER BY ts.team;

\qecho '-- Key play: Ruth 3-run HR (look up via plays):'
SELECT p.gid, p.inning, p.top_bot, p.batter, pl.usename || ' ' || pl.lastname AS batter_name,
       p.pitcher, p.hr, p.runs AS runs_on_play
FROM retro.plays p
JOIN retro.players pl ON p.batter = pl.id
WHERE p.gid IN (SELECT gid FROM retro.games WHERE date='1923-04-18' AND hometeam='NYA' AND visteam='BOS')
  AND p.batter = 'ruthb101'
  AND p.hr = 1
ORDER BY p.pn;

-- =====================================================================
\qecho ''
\qecho '== GAME 2: 1956-10-08 NYA vs BRO — Larsen perfect game (WS G5) =='
-- =====================================================================
SELECT g.gid, g.date, g.hometeam, g.visteam, g.site, g.vruns, g.hruns,
       g.attendance, g.gametype
FROM retro.games g
WHERE g.date = '1956-10-08' AND g.hometeam = 'NYA' AND g.visteam = 'BRO';

\qecho '-- Per-team line — BRO should show 0 hits, 0 walks, 27 batters faced:'
SELECT ts.gid, ts.team, ts.b_pa AS pa, ts.b_ab AS ab, ts.b_h AS hits,
       ts.b_w AS walks, ts.b_hbp AS hbp, ts.b_r AS runs,
       ts.lob
FROM retro.teamstats ts
WHERE ts.gid IN (SELECT gid FROM retro.games WHERE date='1956-10-08' AND hometeam='NYA' AND visteam='BRO')
  AND ts.stattype = 'value'
ORDER BY ts.team;

\qecho '-- Larsen pitching line — expect 27 outs, 0 H, 0 BB, 1 game complete:'
SELECT pi.id, pl.usename || ' ' || pl.lastname AS pitcher_name,
       pi.p_ipouts, pi.p_h, pi.p_w, pi.p_k, pi.p_cg, pi.wp
FROM retro.pitching pi
JOIN retro.players pl ON pi.id = pl.id
WHERE pi.gid IN (SELECT gid FROM retro.games WHERE date='1956-10-08' AND hometeam='NYA' AND visteam='BRO')
  AND pi.team = 'NYA'
  AND pi.stattype = 'value';

-- =====================================================================
\qecho ''
\qecho '== GAME 3: 1974-04-08 ATL vs LAN — Aaron 715th HR =='
-- =====================================================================
SELECT g.gid, g.date, g.hometeam, g.visteam, g.site, g.vruns, g.hruns,
       g.attendance, g.gametype
FROM retro.games g
WHERE g.date = '1974-04-08' AND g.hometeam = 'ATL' AND g.visteam = 'LAN';

\qecho '-- Per-team line:'
SELECT ts.gid, ts.team, ts.b_h AS hits, ts.b_r AS runs, ts.b_hr AS hr
FROM retro.teamstats ts
WHERE ts.gid IN (SELECT gid FROM retro.games WHERE date='1974-04-08' AND hometeam='ATL' AND visteam='LAN')
  AND ts.stattype = 'value'
ORDER BY ts.team;

\qecho '-- Aarons HR(s) in this game — expect 1 in inning 4 off Al Downing (downa101):'
SELECT p.gid, p.inning, p.top_bot, p.batter, pl_b.usename || ' ' || pl_b.lastname AS batter,
       p.pitcher, pl_p.usename || ' ' || pl_p.lastname AS pitcher,
       p.hr, p.runs AS runs_on_play
FROM retro.plays p
JOIN retro.players pl_b ON p.batter  = pl_b.id
JOIN retro.players pl_p ON p.pitcher = pl_p.id
WHERE p.gid IN (SELECT gid FROM retro.games WHERE date='1974-04-08' AND hometeam='ATL' AND visteam='LAN')
  AND p.batter = 'aaroh101'
  AND p.hr = 1
ORDER BY p.pn;

-- =====================================================================
\qecho ''
\qecho '== GAME 4: 2001-11-04 ARI vs NYA — World Series Game 7 =='
-- =====================================================================
SELECT g.gid, g.date, g.hometeam, g.visteam, g.site, g.vruns, g.hruns,
       g.attendance, g.gametype
FROM retro.games g
WHERE g.date = '2001-11-04' AND g.hometeam = 'ARI' AND g.visteam = 'NYA';

\qecho '-- Per-team line — expect ARI 3 NYA 2:'
SELECT ts.gid, ts.team, ts.b_h AS hits, ts.b_r AS runs, ts.lob
FROM retro.teamstats ts
WHERE ts.gid IN (SELECT gid FROM retro.games WHERE date='2001-11-04' AND hometeam='ARI' AND visteam='NYA')
  AND ts.stattype = 'value'
ORDER BY ts.team;

\qecho '-- Final inning context — bottom 9 plays, expect Gonzalez walk-off off Rivera:'
SELECT p.gid, p.inning, p.top_bot, p.outs_pre, p.outs_post,
       pl_b.usename || ' ' || pl_b.lastname AS batter,
       pl_p.usename || ' ' || pl_p.lastname AS pitcher,
       p.event, p.runs AS runs_on_play
FROM retro.plays p
JOIN retro.players pl_b ON p.batter  = pl_b.id
JOIN retro.players pl_p ON p.pitcher = pl_p.id
WHERE p.gid IN (SELECT gid FROM retro.games WHERE date='2001-11-04' AND hometeam='ARI' AND visteam='NYA')
  AND p.inning = 9
  AND p.top_bot = 1   -- bottom of the inning
ORDER BY p.pn;
