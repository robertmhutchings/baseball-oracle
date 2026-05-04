"""
Ingest Retrosheet data into the retro schema.

Phase 1 scope:
  - Cross-year reference tables: teams, ballparks, players, relatives
  - 1998-season-only tables: games, players_team_year, batting, pitching,
    fielding, teamstats, plays

Loads in 4 stages with verification after each. TRUNCATEs all target
tables at the start so re-runs give a clean state. Uses PostgreSQL COPY
via psycopg for bulk speed.

If anything goes wrong (per-row transform failure OR database error) the
script stops immediately and the transaction rolls back -- DB stays empty.
"""

import csv
import os
import sys
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_ROOT = Path(r"C:\BaseballOracle\data")
YEAR_DIR = DATA_ROOT / "1998"
ENV_PATH = Path(r"C:\BaseballOracle\.env")
TARGET_YEAR = 1998


# ---------------------------------------------------------------------------
# Value transforms
# CSV cells arrive as strings. These convert to typed Python values; None
# becomes NULL on the COPY stream.
# ---------------------------------------------------------------------------
def passthrough(v):
    return None if v == "" else v


def to_int(v):
    if v is None or v == "":
        return None
    return int(v)


def to_float(v):
    if v is None or v == "":
        return None
    return float(v)


def to_bool(v):
    """'1'/'true'/'t'/'y' -> True; '0'/'false'/'f'/'n' -> False; '' -> None."""
    if v is None or v == "":
        return None
    s = str(v).strip().lower()
    if s in ("1", "true", "t", "y", "yes"):
        return True
    if s in ("0", "false", "f", "n", "no"):
        return False
    raise ValueError(f"bad boolean value: {v!r}")


def to_date_yyyymmdd(v):
    """Retrosheet game-level dates are always full YYYYMMDD."""
    if v is None or v == "":
        return None
    if len(v) != 8:
        raise ValueError(f"bad YYYYMMDD date: {v!r}")
    yyyy, mm, dd = v[0:4], v[4:6], v[6:8]
    if mm == "00" or dd == "00":
        return None  # partial date — shouldn't occur in game-level data
    return date(int(yyyy), int(mm), int(dd))


def to_date_mdy(v):
    """Parse M/D/YYYY (used by ballparks.START and .END). Blank -> None."""
    if v is None or v == "":
        return None
    parts = v.split("/")
    if len(parts) != 3:
        raise ValueError(f"bad M/D/YYYY date: {v!r}")
    m, d, y = parts
    return date(int(y), int(m), int(d))


# ---------------------------------------------------------------------------
# Table specifications
# Each spec builds a list of (csv_header_lowercased, db_column, transform)
# tuples plus a list of extra (db_column, constant_value) pairs that are
# appended to every row (used for players_team_year.year).
# ---------------------------------------------------------------------------
def _build_fields(ordered, int_cols=(), bool_cols=(), date_yyyymmdd_cols=(),
                  date_mdy_cols=(), float_cols=(), rename_csv_to_db=None):
    """
    Build the fields list from ordered DB column names and type sets.
    rename_csv_to_db: for a DB column whose CSV header is different
      (pitching.is_save <- save; plays.pitch_count <- count).
    """
    rename_csv_to_db = rename_csv_to_db or {}
    # Reverse the rename so we can look up "given this db col, what's the csv header?"
    db_to_csv = {v: k for k, v in rename_csv_to_db.items()}

    int_cols = set(int_cols)
    bool_cols = set(bool_cols)
    date_yyyymmdd_cols = set(date_yyyymmdd_cols)
    date_mdy_cols = set(date_mdy_cols)
    float_cols = set(float_cols)

    fields = []
    for db_col in ordered:
        csv_header = db_to_csv.get(db_col, db_col)
        if db_col in int_cols:
            xform = to_int
        elif db_col in bool_cols:
            xform = to_bool
        elif db_col in date_yyyymmdd_cols:
            xform = to_date_yyyymmdd
        elif db_col in date_mdy_cols:
            xform = to_date_mdy
        elif db_col in float_cols:
            xform = to_float
        else:
            xform = passthrough
        fields.append((csv_header, db_col, xform))
    return fields


def spec_teams():
    ordered = ["team", "league", "city", "nickname", "first_year", "last_year"]
    return {
        "table": "retro.teams",
        "csv": DATA_ROOT / "teams.csv",
        "fields": _build_fields(
            ordered,
            int_cols=("first_year", "last_year"),
            rename_csv_to_db={"first": "first_year", "last": "last_year"},
        ),
        "extras": [],
    }


def spec_ballparks():
    ordered = ["parkid", "name", "aka", "city", "state",
               "start_date", "end_date", "league", "notes"]
    return {
        "table": "retro.ballparks",
        "csv": DATA_ROOT / "ballparks.csv",
        "fields": _build_fields(
            ordered,
            date_mdy_cols=("start_date", "end_date"),
            rename_csv_to_db={"start": "start_date", "end": "end_date"},
        ),
        "extras": [],
    }


def spec_players():
    ordered = [
        "id", "lastname", "usename", "fullname",
        "birthdate", "birthcity", "birthstate", "birthcountry",
        "deathdate", "deathcity", "deathstate", "deathcountry",
        "cemetery", "cem_city", "cem_state", "cem_ctry", "cem_note",
        "birthname", "altname",
        "debut_p", "last_p", "debut_c", "last_c",
        "debut_m", "last_m", "debut_u", "last_u",
        "bats", "throws", "height", "weight", "hof",
    ]
    return {
        "table": "retro.players",
        "csv": DATA_ROOT / "biofile0.csv",
        "fields": _build_fields(
            ordered,
            float_cols=("height", "weight"),
        ),
        "extras": [],
    }


def spec_relatives():
    ordered = ["id1", "relation", "id2"]
    return {
        "table": "retro.relatives",
        "csv": DATA_ROOT / "relatives.csv",
        "fields": _build_fields(ordered),
        "extras": [],
    }


def spec_games():
    ordered = [
        "gid", "visteam", "hometeam", "site", "date", "number",
        "starttime", "daynight", "innings",
        "tiebreaker", "usedh", "htbf",
        "timeofgame", "attendance",
        "fieldcond", "precip", "sky", "temp",
        "winddir", "windspeed",
        "oscorer", "forfeit",
        "umphome", "ump1b", "ump2b", "ump3b", "umplf", "umprf",
        "wp", "lp", "save",
        "gametype", "vruns", "hruns", "wteam", "lteam",
        "line", "batteries", "lineups", "box", "pbp", "season",
    ]
    return {
        "table": "retro.games",
        "csv": YEAR_DIR / "1998gameinfo.csv",
        "fields": _build_fields(
            ordered,
            int_cols=("number", "innings", "timeofgame", "attendance",
                      "temp", "windspeed", "vruns", "hruns", "season"),
            bool_cols=("tiebreaker", "usedh", "htbf", "forfeit"),
            date_yyyymmdd_cols=("date",),
        ),
        "extras": [],
    }


def spec_players_team_year():
    ordered = ["id", "last", "first", "bat", "throw", "team", "pos"]
    return {
        "table": "retro.players_team_year",
        "csv": YEAR_DIR / "1998allplayers.csv",
        "fields": _build_fields(ordered),
        "extras": [("year", TARGET_YEAR)],
    }


def spec_batting():
    ordered = [
        "gid", "id", "team", "b_lp", "b_seq", "stattype",
        "b_pa", "b_ab", "b_r", "b_h", "b_d", "b_t", "b_hr", "b_rbi",
        "b_sh", "b_sf", "b_hbp", "b_w", "b_iw", "b_k",
        "b_sb", "b_cs", "b_gdp", "b_xi", "b_roe",
        "dh", "ph", "pr",
        "date", "number", "site", "opp", "wl", "gametype", "box",
    ]
    int_cols = {"b_lp", "b_seq", "number",
                "b_pa", "b_ab", "b_r", "b_h", "b_d", "b_t", "b_hr", "b_rbi",
                "b_sh", "b_sf", "b_hbp", "b_w", "b_iw", "b_k",
                "b_sb", "b_cs", "b_gdp", "b_xi", "b_roe"}
    return {
        "table": "retro.batting",
        "csv": YEAR_DIR / "1998batting.csv",
        "fields": _build_fields(
            ordered,
            int_cols=int_cols,
            bool_cols=("dh", "ph", "pr"),
            date_yyyymmdd_cols=("date",),
        ),
        "extras": [],
    }


def spec_pitching():
    ordered = [
        "gid", "id", "team", "p_seq", "stattype",
        "p_ipouts", "p_noout", "p_bfp",
        "p_h", "p_d", "p_t", "p_hr", "p_r", "p_er",
        "p_w", "p_iw", "p_k", "p_hbp", "p_wp", "p_bk",
        "p_sh", "p_sf", "p_sb", "p_cs", "p_pb",
        "wp", "lp", "is_save", "p_gs", "p_gf", "p_cg",
        "date", "number", "site", "opp", "wl", "gametype", "box",
    ]
    int_cols = {"p_seq", "number",
                "p_ipouts", "p_noout", "p_bfp",
                "p_h", "p_d", "p_t", "p_hr", "p_r", "p_er",
                "p_w", "p_iw", "p_k", "p_hbp", "p_wp", "p_bk",
                "p_sh", "p_sf", "p_sb", "p_cs", "p_pb"}
    return {
        "table": "retro.pitching",
        "csv": YEAR_DIR / "1998pitching.csv",
        "fields": _build_fields(
            ordered,
            int_cols=int_cols,
            bool_cols=("wp", "lp", "is_save", "p_gs", "p_gf", "p_cg"),
            date_yyyymmdd_cols=("date",),
            # CSV header has 'save'; DB column is 'is_save'
            rename_csv_to_db={"save": "is_save"},
        ),
        "extras": [],
    }


def spec_fielding():
    ordered = [
        "gid", "id", "team", "d_seq", "d_pos", "stattype",
        "d_ifouts", "d_po", "d_a", "d_e", "d_dp", "d_tp",
        "d_pb", "d_wp", "d_sb", "d_cs", "d_gs",
        "date", "number", "site", "opp", "wl", "gametype", "box",
    ]
    int_cols = {"d_seq", "d_pos", "number",
                "d_ifouts", "d_po", "d_a", "d_e", "d_dp", "d_tp",
                "d_pb", "d_wp", "d_sb", "d_cs"}
    return {
        "table": "retro.fielding",
        "csv": YEAR_DIR / "1998fielding.csv",
        "fields": _build_fields(
            ordered,
            int_cols=int_cols,
            bool_cols=("d_gs",),
            date_yyyymmdd_cols=("date",),
        ),
        "extras": [],
    }


def spec_teamstats():
    innings = [f"inn{i}" for i in range(1, 29)]
    starts_l = [f"start_l{i}" for i in range(1, 10)]
    starts_f = [f"start_f{i}" for i in range(1, 11)]
    ordered = (
        ["gid", "team"]
        + innings
        + ["lob", "mgr", "stattype"]
        + ["b_pa", "b_ab", "b_r", "b_h", "b_d", "b_t", "b_hr", "b_rbi",
           "b_sh", "b_sf", "b_hbp", "b_w", "b_iw", "b_k",
           "b_sb", "b_cs", "b_gdp", "b_xi", "b_roe"]
        + ["p_ipouts", "p_noout", "p_bfp",
           "p_h", "p_d", "p_t", "p_hr", "p_r", "p_er",
           "p_w", "p_iw", "p_k", "p_hbp", "p_wp", "p_bk",
           "p_sh", "p_sf", "p_sb", "p_cs", "p_pb"]
        + ["d_po", "d_a", "d_e", "d_dp", "d_tp",
           "d_pb", "d_wp", "d_sb", "d_cs"]
        + starts_l + starts_f
        + ["date", "number", "site", "opp", "wl", "gametype", "box"]
    )
    int_cols = set(innings) | {"lob", "number"} | {
        "b_pa", "b_ab", "b_r", "b_h", "b_d", "b_t", "b_hr", "b_rbi",
        "b_sh", "b_sf", "b_hbp", "b_w", "b_iw", "b_k",
        "b_sb", "b_cs", "b_gdp", "b_xi", "b_roe",
        "p_ipouts", "p_noout", "p_bfp",
        "p_h", "p_d", "p_t", "p_hr", "p_r", "p_er",
        "p_w", "p_iw", "p_k", "p_hbp", "p_wp", "p_bk",
        "p_sh", "p_sf", "p_sb", "p_cs", "p_pb",
        "d_po", "d_a", "d_e", "d_dp", "d_tp",
        "d_pb", "d_wp", "d_sb", "d_cs",
    }
    return {
        "table": "retro.teamstats",
        "csv": YEAR_DIR / "1998teamstats.csv",
        "fields": _build_fields(
            ordered,
            int_cols=int_cols,
            date_yyyymmdd_cols=("date",),
        ),
        "extras": [],
    }


def spec_plays():
    ordered = [
        "gid", "pn", "event",
        "inning", "top_bot", "vis_home",
        "ballpark", "batteam", "pitteam",
        "batter", "pitcher", "lp", "bat_f",
        "bathand", "pithand", "pitch_count", "pitches",
        "pa", "ab",
        "single", "double", "triple", "hr",
        "sh", "sf", "hbp", "walk", "iw", "k", "xi",
        "oth", "othout", "noout",
        "bip", "bunt", "ground", "fly", "line",
        "gdp", "othdp", "tp",
        "wp", "pb", "bk", "oa", "di",
        "sb2", "sb3", "sbh",
        "cs2", "cs3", "csh",
        "pko1", "pko2", "pko3",
        "k_safe",
        "e1", "e2", "e3", "e4", "e5", "e6", "e7", "e8", "e9",
        "outs_pre", "outs_post",
        "br1_pre", "br2_pre", "br3_pre",
        "br1_post", "br2_post", "br3_post",
        "run_b", "run1", "run2", "run3",
        "prun1", "prun2", "prun3",
        "runs", "rbi", "er", "tur",
        "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9",
        "po0", "po1", "po2", "po3", "po4", "po5", "po6", "po7", "po8", "po9",
        "a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9",
        "batout1", "batout2", "batout3",
        "brout_b", "brout1", "brout2", "brout3",
        "firstf", "loc", "hittype", "dpopp", "pivot",
    ]
    int_cols = {
        "pn", "inning", "top_bot", "vis_home", "lp", "bat_f",
        "pa", "ab",
        "single", "double", "triple", "hr",
        "sh", "sf", "hbp", "walk", "iw", "k", "xi",
        "oth", "othout", "noout",
        "bip", "bunt", "ground", "fly", "line",
        "gdp", "othdp", "tp",
        "wp", "pb", "bk", "oa", "di",
        "sb2", "sb3", "sbh", "cs2", "cs3", "csh",
        "pko1", "pko2", "pko3", "k_safe",
        "e1", "e2", "e3", "e4", "e5", "e6", "e7", "e8", "e9",
        "outs_pre", "outs_post",
        "runs", "rbi", "er", "tur",
        "po0", "po1", "po2", "po3", "po4", "po5", "po6", "po7", "po8", "po9",
        "a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9",
        "batout1", "batout2", "batout3",
        "brout_b", "brout1", "brout2", "brout3",
        "firstf", "dpopp", "pivot",
    }
    return {
        "table": "retro.plays",
        "csv": YEAR_DIR / "1998plays.csv",
        "fields": _build_fields(
            ordered,
            int_cols=int_cols,
            # CSV header has 'count'; DB column is 'pitch_count'
            rename_csv_to_db={"count": "pitch_count"},
        ),
        "extras": [],
    }


# ---------------------------------------------------------------------------
# Generic table loader (COPY-based)
# ---------------------------------------------------------------------------
def load_table(conn, spec):
    table = spec["table"]
    csv_path = spec["csv"]
    fields = spec["fields"]          # list[(csv_header, db_col, transform)]
    extras = spec["extras"]          # list[(db_col, constant_value)]

    # DB column order for COPY target list
    db_cols = [f[1] for f in fields] + [e[0] for e in extras]
    extra_values = [e[1] for e in extras]

    # Index into the output tuple for each CSV header we care about
    csv_header_to_outpos = {f[0]: i for i, f in enumerate(fields)}
    csv_header_to_xform = {f[0]: f[2] for f in fields}
    expected_csv_headers = set(csv_header_to_outpos.keys())

    copy_sql = f"COPY {table} ({', '.join(db_cols)}) FROM STDIN"

    loaded = 0
    failed = []  # list[(lineno, error_msg, row)]

    with open(csv_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        try:
            raw_header = next(reader)
        except StopIteration:
            raise RuntimeError(f"{csv_path}: empty CSV")

        csv_headers = [h.lower() for h in raw_header]
        missing = expected_csv_headers - set(csv_headers)
        if missing:
            raise RuntimeError(
                f"{csv_path.name}: expected CSV headers not found: "
                f"{sorted(missing)}"
            )

        # Per-row plan: list of (csv_index, output_index, transform)
        # Unknown CSV columns are silently skipped.
        plan = []
        for csv_i, h in enumerate(csv_headers):
            if h in csv_header_to_outpos:
                plan.append((csv_i, csv_header_to_outpos[h], csv_header_to_xform[h]))

        with conn.cursor() as cur:
            with cur.copy(copy_sql) as cpy:
                for lineno, row in enumerate(reader, start=2):
                    try:
                        out = [None] * len(fields)
                        for csv_i, out_i, xform in plan:
                            raw_val = row[csv_i] if csv_i < len(row) else ""
                            # Phase 2 defensive boundary strip: Retrosheet
                            # CSVs occasionally contain whitespace-padded
                            # values (e.g. allplayers.team 'VMA ' in 1946).
                            # Stripping universally is safer than per-column
                            # whitelisting; no Retrosheet field uses leading
                            # or trailing whitespace as meaningful content.
                            raw_val = raw_val.strip()
                            out[out_i] = xform(raw_val)
                        full_row = out + list(extra_values)
                    except Exception as e:
                        failed.append(
                            (lineno, f"{type(e).__name__}: {e}", list(row)[:8])
                        )
                        continue
                    cpy.write_row(full_row)
                    loaded += 1

    return loaded, failed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
ALL_TABLES = [
    # Truncate order (children before parents; not strictly required w/o FKs)
    "retro.plays",
    "retro.teamstats",
    "retro.fielding",
    "retro.pitching",
    "retro.batting",
    "retro.players_team_year",
    "retro.games",
    "retro.relatives",
    "retro.players",
    "retro.ballparks",
    "retro.teams",
]

STAGES = [
    ("STAGE 1 -- reference data",
        [spec_teams, spec_ballparks, spec_players, spec_relatives]),
    ("STAGE 2 -- 1998 games",
        [spec_games]),
    ("STAGE 3 -- 1998 per-game stats",
        [spec_players_team_year, spec_batting, spec_pitching,
         spec_fielding, spec_teamstats]),
    ("STAGE 4 -- 1998 plays",
        [spec_plays]),
]

STATTYPE_TABLES = {
    "retro.batting", "retro.pitching", "retro.fielding", "retro.teamstats",
}


def main():
    if not ENV_PATH.exists():
        print(f"ERROR: .env not found at {ENV_PATH}", file=sys.stderr)
        sys.exit(1)
    load_dotenv(ENV_PATH)

    dsn = {
        "host":     os.environ["PG_HOST"],
        "port":     os.environ["PG_PORT"],
        "user":     os.environ["PG_USER"],
        "password": os.environ["PG_PASSWORD"],
        "dbname":   os.environ["PG_DATABASE"],
    }

    print(f"Connecting to {dsn['dbname']}@{dsn['host']}:{dsn['port']} "
          f"as {dsn['user']}")

    with psycopg.connect(**dsn) as conn:
        # TRUNCATE
        print()
        print("!" * 64)
        print("WARNING: about to TRUNCATE all 11 retro tables.")
        print("Any existing data in those tables will be wiped.")
        print("!" * 64)
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE {', '.join(ALL_TABLES)}")
        print("TRUNCATE complete.")

        # Load stages
        for stage_name, spec_fns in STAGES:
            print()
            print("=" * 64)
            print(stage_name)
            print("=" * 64)

            stage_results = []
            for spec_fn in spec_fns:
                spec = spec_fn()
                print(f"  {spec['csv'].name} -> {spec['table']} ...",
                      end=" ", flush=True)
                loaded, failed = load_table(conn, spec)
                print(f"{loaded} rows loaded, {len(failed)} failures")
                stage_results.append((spec["table"], loaded, failed))

                if failed:
                    print(f"    !! FAILURES in {spec['table']} "
                          f"({len(failed)} total, showing up to 5):")
                    for lineno, err, row_snip in failed[:5]:
                        print(f"      line {lineno}: {err}")
                        print(f"         row[:8]: {row_snip}")
                    raise RuntimeError(
                        f"Per-row transform failures in {spec['table']} -- "
                        "stopping per 'STOP on failure' policy."
                    )

            # Verification
            print()
            print("  Verification:")
            with conn.cursor() as cur:
                for table, loaded, _ in stage_results:
                    cur.execute(f"SELECT count(*) FROM {table}")
                    db_count = cur.fetchone()[0]
                    tag = "ok " if db_count == loaded else "MISMATCH"
                    print(f"    [{tag}] {table:30s} {db_count:>10} rows "
                          f"(loaded {loaded})")
                    if table in STATTYPE_TABLES:
                        cur.execute(
                            f"SELECT stattype, count(*) FROM {table} "
                            "GROUP BY stattype ORDER BY stattype"
                        )
                        for stattype, cnt in cur.fetchall():
                            print(f"           stattype={stattype!r:12s} "
                                  f"{cnt:>10}")

        print()
        print("=" * 64)
        print("ALL STAGES COMPLETE.")
        print("=" * 64)


if __name__ == "__main__":
    main()
