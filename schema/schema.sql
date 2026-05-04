-- =============================================================
-- Baseball Oracle schema  (PostgreSQL 16)
-- Source: Retrosheet CSV exports, 1901-2023 + cross-year reference files
-- =============================================================
--
-- Execution (via psql):
--   psql -U postgres -f schema.sql
--
-- The CREATE DATABASE line must be run while connected to some OTHER
-- database (e.g. 'postgres'), then the \c baseball_oracle reconnects and
-- the rest of the file runs against the new database.
--
-- DESIGN NOTES
-- ------------
-- 1. Column names match Retrosheet CSV headers verbatim so ingest can be a
--    direct COPY/insert without rename mapping, with two exceptions made
--    to avoid reserved-word adjacency for LLM-generated queries:
--      pitching.save  -> is_save
--      plays.count    -> pitch_count
--    Other names that shadow built-in type names or are keyword-adjacent
--    ('date', 'line', 'double', 'triple', games.save) are kept as-is;
--    they are safe unquoted as column references in PostgreSQL.
--
-- 2. stattype (on batting, pitching, fielding, teamstats) takes values
--    'value', 'official', 'lower', 'upper'. For canonical per-game stats
--    filter stattype = 'value'. We keep all four -- no CHECK constraint.
--
-- 3. Per-game counting stats are SMALLINT (2 bytes, fits comfortably).
--    p_ipouts, timeofgame, plays.pn use INTEGER for headroom.
--    games.attendance is VARCHAR(24) -- pre-modern Negro League games
--    include hedged values like 'hundreds', '<1000', '6000c.'.
--
-- 4. DATE vs VARCHAR(8) for Retrosheet dates:
--    - gameinfo.date, batting.date, pitching.date, fielding.date,
--      teamstats.date are always fully populated valid YYYYMMDD -> DATE.
--    - biofile0 birthdate/deathdate/debut_*/last_* can be partial
--      (e.g. '19010000' meaning "born in 1901, month/day unknown"), which
--      DATE cannot represent. Those columns are VARCHAR(8). Cast with
--      to_date(col, 'YYYYMMDD') when the value is fully known.
--    - ballparks.START/END use mixed M/D/YYYY formatting and are often
--      blank; stored as DATE, parsed at ingest.
--
-- 5. players.height and players.weight are both NUMERIC(4,1). Retrosheet
--    records some heights as half-inches (e.g. 71.5) and at least one
--    weight as a half-pound (daviw104 = 172.5).
--
-- 6. players.HOF is kept as VARCHAR (literal 'HOF' marker or NULL) rather
--    than BOOLEAN to preserve the source representation.
--
-- 7. Weather sentinels in pre-computer-era games: temp=0 and windspeed=-1
--    are used for "unknown" in old gameinfo rows. Left as-is -- consumers
--    should filter (e.g. temp > 0) when real weather values are needed.
--
-- 8. BOOLEAN is used where the CSV field is truly yes/no (dh, ph, pr,
--    pitching.wp/lp/is_save/p_gs/p_gf/p_cg, fielding.d_gs, games.usedh/
--    htbf/forfeit). Ingest must translate '1' -> TRUE, '' -> NULL,
--    'true'/'false' -> BOOLEAN. games.tiebreaker was BOOLEAN through the
--    phase2-2026-04-24 schema; widened to SMALLINT in phase2-2026-04-27
--    to accommodate the 2020+ runner-on-2B rule (value = base number).
--
-- 9. plays per-play flags (pa, ab, single, double, ..., sbh) stay as
--    SMALLINT because Retrosheet encodes them as 0/1 counts and some
--    (e.g. error-count columns e1..e9) can legitimately exceed 1.
--
-- 10. players_team_year gets a synthetic 'year' column populated during
--     ingest from the source folder name (1901..2023) -- it is not in
--     the CSV itself, but is required to make the row grain meaningful.
--
-- 11. Primary keys are added only where the natural grain is obvious
--     (players, players_team_year, relatives, teams, ballparks, games,
--     plays). The stats tables (batting, pitching, fielding, teamstats)
--     have complex grain due to stattype multiplicity and sequence
--     columns and are left PK-less; we will revisit after loading.
--
-- 12. No foreign keys and no indexes are created here. FKs complicate
--     load order; indexes depend on observed query patterns. Both come
--     after the data is in.
-- =============================================================

CREATE DATABASE baseball_oracle WITH ENCODING 'UTF8';

\c baseball_oracle

CREATE SCHEMA IF NOT EXISTS retro;
SET search_path TO retro, public;


-- -------------------------------------------------------------
-- players
-- Biographical data (biofile0.csv). One row per person (player,
-- coach, manager, or umpire) known to Retrosheet. 'id' is the
-- 8-char RetroID used everywhere as a foreign-key-style reference.
-- -------------------------------------------------------------
CREATE TABLE retro.players (
    id              VARCHAR(8)   PRIMARY KEY,
    lastname        TEXT,
    usename         TEXT,          -- display first name
    fullname        TEXT,
    birthdate       VARCHAR(8),    -- YYYYMMDD; '00' placeholders for unknown mm/dd
    birthcity       TEXT,
    birthstate      TEXT,
    birthcountry    TEXT,
    deathdate       VARCHAR(8),
    deathcity       TEXT,
    deathstate      TEXT,
    deathcountry    TEXT,
    cemetery        TEXT,
    cem_city        TEXT,
    cem_state       TEXT,
    cem_ctry        TEXT,
    cem_note        TEXT,
    birthname       TEXT,
    altname         TEXT,
    debut_p         VARCHAR(8),    -- first game as player
    last_p          VARCHAR(8),    -- last game as player
    debut_c         VARCHAR(8),    -- first game as coach
    last_c          VARCHAR(8),
    debut_m         VARCHAR(8),    -- first game as manager
    last_m          VARCHAR(8),
    debut_u         VARCHAR(8),    -- first game as umpire
    last_u          VARCHAR(8),
    bats            VARCHAR(2),    -- L / R / B / ?
    throws          VARCHAR(2),
    height          NUMERIC(4,1),  -- inches; half-inch precision
    weight          NUMERIC(4,1),  -- pounds; half-pound precision
    HOF             VARCHAR(8)     -- 'HOF' marker or NULL
);


-- -------------------------------------------------------------
-- players_team_year
-- Per-season roster entries (YYYY/YYYYallplayers.csv). A player has
-- one row per team they appeared with in that season, including
-- all-star team codes like 'ALS'. The 'year' column is added during
-- ingest from the folder name and is not present in the CSV.
-- -------------------------------------------------------------
CREATE TABLE retro.players_team_year (
    id              VARCHAR(8)   NOT NULL,
    last            TEXT,
    first           TEXT,
    bat             VARCHAR(2),
    throw           VARCHAR(2),
    team            VARCHAR(3)   NOT NULL,
    pos             VARCHAR(3),    -- OF, 2B, P, DH, etc.; 'X' for all-star/unknown
    year            SMALLINT     NOT NULL,
    PRIMARY KEY (id, team, year)
);


-- -------------------------------------------------------------
-- relatives
-- Player-to-player family relationships (relatives.csv).
-- 'relation' observed values: Brother, Father, Uncle, Cousin,
-- Grandfather, Brother-in-Law, etc.
-- -------------------------------------------------------------
CREATE TABLE retro.relatives (
    id1             VARCHAR(8)   NOT NULL,
    relation        VARCHAR(30)  NOT NULL,
    id2             VARCHAR(8)   NOT NULL,
    PRIMARY KEY (id1, relation, id2)
);


-- -------------------------------------------------------------
-- teams
-- Franchise-era team codes (teams.csv). 'league' can be
-- semicolon-delimited when a franchise moved between leagues.
-- -------------------------------------------------------------
CREATE TABLE retro.teams (
    team            VARCHAR(3)   PRIMARY KEY,
    league          TEXT,          -- may be 'NNL;NAL' etc.
    city            TEXT,
    nickname        TEXT,
    first_year      SMALLINT,
    last_year       SMALLINT
);


-- -------------------------------------------------------------
-- ballparks
-- Park identifiers and metadata (ballparks.csv). START/END parsed
-- from mixed M/D/YYYY formatting at ingest; often NULL for older
-- parks.
-- -------------------------------------------------------------
CREATE TABLE retro.ballparks (
    parkid          VARCHAR(5)   PRIMARY KEY,
    name            TEXT,
    aka             TEXT,
    city            TEXT,
    state           TEXT,
    start_date      DATE,
    end_date        DATE,
    league          TEXT,
    notes           TEXT
);


-- -------------------------------------------------------------
-- games
-- One row per game (YYYY/YYYYgameinfo.csv). gid is a composite of
-- home team + date + game number (e.g. 'ARI199803310'). Many
-- contextual columns (weather, umpires, attendance) are NULL for
-- older games.
-- -------------------------------------------------------------
CREATE TABLE retro.games (
    gid             VARCHAR(12)  PRIMARY KEY,
    visteam         VARCHAR(3),
    hometeam        VARCHAR(3),
    site            VARCHAR(5),    -- parkid
    date            DATE,
    number          SMALLINT,      -- 0 single game; 1/2/3 for doubleheaders
    starttime       VARCHAR(20),   -- mixed 'HH:MM' / 'H:MMPM' / '0.5833...' (fractional-day) formats
    daynight        VARCHAR(10),
    innings         SMALLINT,      -- scheduled innings; NULL = 9
    tiebreaker      SMALLINT,      -- base where extras-runner is placed (2020+ rule); NULL pre-2020 or where rule does not apply
    usedh           BOOLEAN,
    htbf            BOOLEAN,       -- home team bat first
    timeofgame      INTEGER,       -- minutes
    attendance      VARCHAR(24),  -- numeric in modern data; pre-modern Negro League games include hedged values ('hundreds', '<1000', '6000c.', etc.)
    fieldcond       VARCHAR(20),
    precip          VARCHAR(20),
    sky             VARCHAR(20),
    temp            SMALLINT,      -- deg F; 0 = unknown in older games
    winddir         VARCHAR(15),
    windspeed       SMALLINT,      -- mph; -1 = unknown in older games
    oscorer         TEXT,
    forfeit         VARCHAR(2),    -- Retrosheet code: V/H/T (per spec) or Y (forfeited, direction unspecified). NULL = no forfeit.
    umphome         VARCHAR(10),
    ump1b           VARCHAR(10),
    ump2b           VARCHAR(10),
    ump3b           VARCHAR(10),
    umplf           VARCHAR(10),
    umprf           VARCHAR(10),
    wp              VARCHAR(8),    -- winning pitcher id
    lp              VARCHAR(8),    -- losing pitcher id
    save            VARCHAR(8),    -- save pitcher id (NULL if no save)
    gametype        VARCHAR(20),
    vruns           SMALLINT,
    hruns           SMALLINT,
    wteam           VARCHAR(3),
    lteam           VARCHAR(3),
    line            VARCHAR(4),    -- 'y' if line score known
    batteries       VARCHAR(10),   -- 'p', 'both', or blank
    lineups         VARCHAR(4),
    box             VARCHAR(4),
    pbp             VARCHAR(4),    -- 'd' deduced / 'y' source
    season          SMALLINT
);


-- -------------------------------------------------------------
-- batting
-- Per-game per-player batting line (YYYY/YYYYbatting.csv). A player
-- can have multiple rows per game when they fill multiple lineup
-- slots (pinch hits, etc.) -- b_seq disambiguates. Pitchers who
-- never bat have NULL b_lp and b_seq.
-- stattype = 'value' for canonical per-game stats.
-- -------------------------------------------------------------
CREATE TABLE retro.batting (
    gid             VARCHAR(12)  NOT NULL,
    id              VARCHAR(8)   NOT NULL,
    team            VARCHAR(3)   NOT NULL,
    b_lp            SMALLINT,      -- lineup position 1-9; NULL for non-batters
    b_seq           SMALLINT,      -- order of appearance at lineup slot
    stattype        VARCHAR(10)  NOT NULL,
    b_pa            SMALLINT,
    b_ab            SMALLINT,
    b_r             SMALLINT,
    b_h             SMALLINT,
    b_d             SMALLINT,      -- doubles
    b_t             SMALLINT,      -- triples
    b_hr            SMALLINT,
    b_rbi           SMALLINT,
    b_sh            SMALLINT,
    b_sf            SMALLINT,
    b_hbp           SMALLINT,
    b_w             SMALLINT,
    b_iw            SMALLINT,
    b_k             SMALLINT,
    b_sb            SMALLINT,
    b_cs            SMALLINT,
    b_gdp           SMALLINT,
    b_xi            SMALLINT,
    b_roe           SMALLINT,
    dh              BOOLEAN,       -- DH'd in the game
    ph              BOOLEAN,       -- pinch hit
    pr              BOOLEAN,       -- pinch ran
    date            DATE,
    number          SMALLINT,
    site            VARCHAR(5),
    opp             VARCHAR(3),
    wl              CHAR(1),       -- 'w' / 'l' / NULL
    gametype        VARCHAR(20),
    box             VARCHAR(4)
);


-- -------------------------------------------------------------
-- pitching
-- Per-game per-pitcher line (YYYY/YYYYpitching.csv). p_seq orders
-- pitchers by appearance (1 = starter).
-- -------------------------------------------------------------
CREATE TABLE retro.pitching (
    gid             VARCHAR(12)  NOT NULL,
    id              VARCHAR(8)   NOT NULL,
    team            VARCHAR(3)   NOT NULL,
    p_seq           SMALLINT,
    stattype        VARCHAR(10)  NOT NULL,
    p_ipouts        INTEGER,       -- outs recorded (IP * 3)
    p_noout         SMALLINT,
    p_bfp           SMALLINT,
    p_h             SMALLINT,
    p_d             SMALLINT,
    p_t             SMALLINT,
    p_hr            SMALLINT,
    p_r             SMALLINT,
    p_er            SMALLINT,
    p_w             SMALLINT,
    p_iw            SMALLINT,
    p_k             SMALLINT,
    p_hbp           SMALLINT,
    p_wp            SMALLINT,
    p_bk            SMALLINT,
    p_sh            SMALLINT,
    p_sf            SMALLINT,
    p_sb            SMALLINT,
    p_cs            SMALLINT,
    p_pb            SMALLINT,
    wp              BOOLEAN,       -- won the game
    lp              BOOLEAN,       -- lost the game
    is_save         BOOLEAN,       -- earned a save
    p_gs            BOOLEAN,       -- game started
    p_gf            BOOLEAN,       -- game finished (in relief)
    p_cg            BOOLEAN,       -- complete game
    date            DATE,
    number          SMALLINT,
    site            VARCHAR(5),
    opp             VARCHAR(3),
    wl              CHAR(1),
    gametype        VARCHAR(20),
    box             VARCHAR(4)
);


-- -------------------------------------------------------------
-- fielding
-- Per-game per-player per-position line (YYYY/YYYYfielding.csv). A
-- player who played multiple positions in one game has multiple
-- rows -- d_seq orders them. d_pb/d_wp/d_sb/d_cs are populated
-- only when d_pos = 2 (catcher).
-- -------------------------------------------------------------
CREATE TABLE retro.fielding (
    gid             VARCHAR(12)  NOT NULL,
    id              VARCHAR(8)   NOT NULL,
    team            VARCHAR(3)   NOT NULL,
    d_seq           SMALLINT,
    d_pos           SMALLINT,      -- 1 pitcher ... 9 RF, 10 DH
    stattype        VARCHAR(10)  NOT NULL,
    d_ifouts        SMALLINT,
    d_po            SMALLINT,
    d_a             SMALLINT,
    d_e             SMALLINT,
    d_dp            SMALLINT,
    d_tp            SMALLINT,
    d_pb            SMALLINT,      -- catcher only
    d_wp            SMALLINT,      -- catcher only
    d_sb            SMALLINT,      -- catcher only
    d_cs            SMALLINT,      -- catcher only
    d_gs            BOOLEAN,       -- started at this position
    date            DATE,
    number          SMALLINT,
    site            VARCHAR(5),
    opp             VARCHAR(3),
    wl              CHAR(1),
    gametype        VARCHAR(20),
    box             VARCHAR(4)
);


-- -------------------------------------------------------------
-- teamstats
-- Per-game per-team aggregate (YYYY/YYYYteamstats.csv): inning
-- scores, batting/pitching/fielding totals, and starting lineup.
-- inn10..inn28 are NULL for games that did not reach that inning.
-- start_l1..l9 = lineup positions; start_f1..f10 = fielding positions.
-- -------------------------------------------------------------
CREATE TABLE retro.teamstats (
    gid             VARCHAR(12)  NOT NULL,
    team            VARCHAR(3)   NOT NULL,
    inn1            SMALLINT,
    inn2            SMALLINT,
    inn3            SMALLINT,
    inn4            SMALLINT,
    inn5            SMALLINT,
    inn6            SMALLINT,
    inn7            SMALLINT,
    inn8            SMALLINT,
    inn9            SMALLINT,
    inn10           SMALLINT,
    inn11           SMALLINT,
    inn12           SMALLINT,
    inn13           SMALLINT,
    inn14           SMALLINT,
    inn15           SMALLINT,
    inn16           SMALLINT,
    inn17           SMALLINT,
    inn18           SMALLINT,
    inn19           SMALLINT,
    inn20           SMALLINT,
    inn21           SMALLINT,
    inn22           SMALLINT,
    inn23           SMALLINT,
    inn24           SMALLINT,
    inn25           SMALLINT,
    inn26           SMALLINT,
    inn27           SMALLINT,
    inn28           SMALLINT,
    lob             SMALLINT,
    mgr             VARCHAR(8),    -- manager id
    stattype        VARCHAR(10)  NOT NULL,
    b_pa            SMALLINT,
    b_ab            SMALLINT,
    b_r             SMALLINT,
    b_h             SMALLINT,
    b_d             SMALLINT,
    b_t             SMALLINT,
    b_hr            SMALLINT,
    b_rbi           SMALLINT,
    b_sh            SMALLINT,
    b_sf            SMALLINT,
    b_hbp           SMALLINT,
    b_w             SMALLINT,
    b_iw            SMALLINT,
    b_k             SMALLINT,
    b_sb            SMALLINT,
    b_cs            SMALLINT,
    b_gdp           SMALLINT,
    b_xi            SMALLINT,
    b_roe           SMALLINT,
    p_ipouts        INTEGER,
    p_noout         SMALLINT,
    p_bfp           SMALLINT,
    p_h             SMALLINT,
    p_d             SMALLINT,
    p_t             SMALLINT,
    p_hr            SMALLINT,
    p_r             SMALLINT,
    p_er            SMALLINT,
    p_w             SMALLINT,
    p_iw            SMALLINT,
    p_k             SMALLINT,
    p_hbp           SMALLINT,
    p_wp            SMALLINT,
    p_bk            SMALLINT,
    p_sh            SMALLINT,
    p_sf            SMALLINT,
    p_sb            SMALLINT,
    p_cs            SMALLINT,
    p_pb            SMALLINT,
    d_po            SMALLINT,
    d_a             SMALLINT,
    d_e             SMALLINT,
    d_dp            SMALLINT,
    d_tp            SMALLINT,
    d_pb            SMALLINT,
    d_wp            SMALLINT,
    d_sb            SMALLINT,
    d_cs            SMALLINT,
    start_l1        VARCHAR(10),
    start_l2        VARCHAR(10),
    start_l3        VARCHAR(10),
    start_l4        VARCHAR(10),
    start_l5        VARCHAR(10),
    start_l6        VARCHAR(10),
    start_l7        VARCHAR(10),
    start_l8        VARCHAR(10),
    start_l9        VARCHAR(10),
    start_f1        VARCHAR(10),   -- pitcher
    start_f2        VARCHAR(10),   -- catcher
    start_f3        VARCHAR(10),   -- 1B
    start_f4        VARCHAR(10),   -- 2B
    start_f5        VARCHAR(10),   -- 3B
    start_f6        VARCHAR(10),   -- SS
    start_f7        VARCHAR(10),   -- LF
    start_f8        VARCHAR(10),   -- CF
    start_f9        VARCHAR(10),   -- RF
    start_f10       VARCHAR(10),   -- DH
    date            DATE,
    number          SMALLINT,
    site            VARCHAR(5),
    opp             VARCHAR(3),
    wl              CHAR(1),
    gametype        VARCHAR(20),
    box             VARCHAR(4)
);


-- -------------------------------------------------------------
-- plays
-- One row per play event (YYYY/YYYYplays.csv). pn is the
-- within-game play number (1, 2, ...). PK is (gid, pn).
-- Most per-event flags (pa, single, double, hr, walk, k, etc.)
-- are SMALLINT 0/1 counts. The e1..e9 columns can exceed 1
-- (multiple errors on one play by the same fielder position).
-- batout*/brout*/firstf/pivot hold fielding positions (1-10).
-- -------------------------------------------------------------
CREATE TABLE retro.plays (
    gid             VARCHAR(12)  NOT NULL,
    pn              INTEGER      NOT NULL,
    event           TEXT,                     -- Retrosheet event string
    inning          SMALLINT,
    top_bot         SMALLINT,                  -- 0 top, 1 bottom
    vis_home        SMALLINT,                  -- 0 visitors bat, 1 home bat
    ballpark        VARCHAR(5),
    batteam         VARCHAR(3),
    pitteam         VARCHAR(3),
    batter          VARCHAR(8),
    pitcher         VARCHAR(8),
    lp              SMALLINT,                  -- batter's lineup position
    bat_f           SMALLINT,                  -- batter's fielding position
    bathand         CHAR(1),                   -- B L R
    pithand         CHAR(1),
    pitch_count     VARCHAR(8),                -- 2-char ball-strike ('22') or '??' in modern data; up to 7 chars with pitch-sequence leakage in 1950s data
    pitches         TEXT,                      -- pitch sequence (may be empty)
    pa              SMALLINT,
    ab              SMALLINT,
    single          SMALLINT,
    double          SMALLINT,
    triple          SMALLINT,
    hr              SMALLINT,
    sh              SMALLINT,
    sf              SMALLINT,
    hbp             SMALLINT,
    walk            SMALLINT,
    iw              SMALLINT,
    k               SMALLINT,
    xi              SMALLINT,
    oth             SMALLINT,
    othout          SMALLINT,
    noout           SMALLINT,
    bip             SMALLINT,
    bunt            SMALLINT,
    ground          SMALLINT,
    fly             SMALLINT,
    line            SMALLINT,                  -- line drive (not line score)
    gdp             SMALLINT,
    othdp           SMALLINT,
    tp              SMALLINT,
    wp              SMALLINT,                  -- wild pitch on this play
    pb              SMALLINT,
    bk              SMALLINT,
    oa              SMALLINT,
    di              SMALLINT,
    sb2             SMALLINT,
    sb3             SMALLINT,
    sbh             SMALLINT,
    cs2             SMALLINT,
    cs3             SMALLINT,
    csh             SMALLINT,
    pko1            SMALLINT,
    pko2            SMALLINT,
    pko3            SMALLINT,
    k_safe          SMALLINT,
    e1              SMALLINT,
    e2              SMALLINT,
    e3              SMALLINT,
    e4              SMALLINT,
    e5              SMALLINT,
    e6              SMALLINT,
    e7              SMALLINT,
    e8              SMALLINT,
    e9              SMALLINT,
    outs_pre        SMALLINT,
    outs_post       SMALLINT,
    br1_pre         VARCHAR(8),
    br2_pre         VARCHAR(8),
    br3_pre         VARCHAR(8),
    br1_post        VARCHAR(8),
    br2_post        VARCHAR(8),
    br3_post        VARCHAR(8),
    run_b           VARCHAR(8),
    run1            VARCHAR(8),
    run2            VARCHAR(8),
    run3            VARCHAR(8),
    prun1           VARCHAR(8),                -- pitcher charged for run1
    prun2           VARCHAR(8),
    prun3           VARCHAR(8),
    runs            SMALLINT,
    rbi             SMALLINT,
    er              SMALLINT,
    tur             SMALLINT,                  -- team unearned runs
    f2              VARCHAR(8),                -- catcher on play
    f3              VARCHAR(8),                -- 1B
    f4              VARCHAR(8),                -- 2B
    f5              VARCHAR(8),                -- 3B
    f6              VARCHAR(8),                -- SS
    f7              VARCHAR(8),                -- LF
    f8              VARCHAR(8),                -- CF
    f9              VARCHAR(8),                -- RF
    po0             SMALLINT,                  -- putout by unidentified fielder (99)
    po1             SMALLINT,
    po2             SMALLINT,
    po3             SMALLINT,
    po4             SMALLINT,
    po5             SMALLINT,
    po6             SMALLINT,
    po7             SMALLINT,
    po8             SMALLINT,
    po9             SMALLINT,
    a1              SMALLINT,
    a2              SMALLINT,
    a3              SMALLINT,
    a4              SMALLINT,
    a5              SMALLINT,
    a6              SMALLINT,
    a7              SMALLINT,
    a8              SMALLINT,
    a9              SMALLINT,
    batout1         SMALLINT,                  -- fielding pos of batting-out initiator
    batout2         SMALLINT,
    batout3         SMALLINT,
    brout_b         SMALLINT,
    brout1          SMALLINT,
    brout2          SMALLINT,
    brout3          SMALLINT,
    firstf          SMALLINT,                  -- first fielder to touch BIP
    loc             VARCHAR(10),               -- location code e.g. '89XD'
    hittype         VARCHAR(4),                -- B/G/P/F/L or BG/BP combos
    dpopp           SMALLINT,                  -- 1 if DP opportunity
    pivot           SMALLINT,                  -- pivot man on DP
    PRIMARY KEY (gid, pn)
);
