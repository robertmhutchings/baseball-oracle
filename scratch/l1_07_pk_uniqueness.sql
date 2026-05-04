-- L1.7 — PK uniqueness sanity check.
--
-- The DB enforces these PKs at COPY time, but a sanity check is cheap and
-- confirms (a) the constraints actually exist, and (b) that no row sneaks
-- in via a bypass path.
--
-- PK-bearing tables of interest (per CLAUDE.md §3 PK uniqueness subsection):
--   retro.games(gid)
--   retro.players_team_year(id, team, year)
--   retro.plays(gid, pn)
--   retro.players(id)
--   retro.teams(team)
--   retro.ballparks(parkid)
--   retro.relatives(id1, relation, id2)

\pset format aligned
\pset border 2
\pset null '(null)'

\qecho '== PK uniqueness sanity (COUNT(*) should equal COUNT(DISTINCT key)) =='
SELECT 'games(gid)'                AS pk,
       COUNT(*)                    AS row_count,
       COUNT(DISTINCT gid)         AS distinct_keys,
       COUNT(*) - COUNT(DISTINCT gid) AS diff
FROM retro.games
UNION ALL
SELECT 'players_team_year(id,team,year)',
       COUNT(*),
       COUNT(DISTINCT (id, team, year)),
       COUNT(*) - COUNT(DISTINCT (id, team, year))
FROM retro.players_team_year
UNION ALL
SELECT 'plays(gid,pn)',
       COUNT(*),
       COUNT(DISTINCT (gid, pn)),
       COUNT(*) - COUNT(DISTINCT (gid, pn))
FROM retro.plays
UNION ALL
SELECT 'players(id)',
       COUNT(*),
       COUNT(DISTINCT id),
       COUNT(*) - COUNT(DISTINCT id)
FROM retro.players
UNION ALL
SELECT 'teams(team)',
       COUNT(*),
       COUNT(DISTINCT team),
       COUNT(*) - COUNT(DISTINCT team)
FROM retro.teams
UNION ALL
SELECT 'ballparks(parkid)',
       COUNT(*),
       COUNT(DISTINCT parkid),
       COUNT(*) - COUNT(DISTINCT parkid)
FROM retro.ballparks
UNION ALL
SELECT 'relatives(id1,relation,id2)',
       COUNT(*),
       COUNT(DISTINCT (id1, relation, id2)),
       COUNT(*) - COUNT(DISTINCT (id1, relation, id2))
FROM retro.relatives
ORDER BY pk;

\qecho ''
\qecho '== Constraint declarations actually present in the DB =='
SELECT
    n.nspname || '.' || c.relname  AS table_name,
    con.conname                    AS constraint_name,
    pg_get_constraintdef(con.oid)  AS def
FROM pg_constraint con
JOIN pg_class      c ON con.conrelid = c.oid
JOIN pg_namespace  n ON c.relnamespace = n.oid
WHERE n.nspname = 'retro' AND con.contype = 'p'
ORDER BY table_name;
