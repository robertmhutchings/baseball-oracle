"""
Phase 2 multi-year Retrosheet ingest into the retro schema.

Loads 1901-2023 CSV data with per-year transactions and a checkpoint
file so a multi-hour run can resume from a mid-stream failure.

  - Stage 1 (reference tables: teams, ballparks, players, relatives) loads
    once in a single transaction, idempotent on resume.
  - Stages 2-4 (games + per-game stats + plays) load per-year, atomically.
    A failure inside any year rolls back that year only; prior years stay
    committed.

Halt conditions: per-row transform failure; missing CSV column that maps to
a NOT NULL DB column; DB connection lost; disk full; stuck (no per-row
progress for STUCK_THRESHOLD_SECONDS); cumulative wall-clock cap exceeded;
checkpoint write failure; SIGINT (graceful) or second SIGINT (hard).

See ingest/phase2_step3_design.md for the full design rationale.
See ingest/phase2_plan.md for the broader Phase 2 strategy.
See ingest/ingest_1998.py for the Phase 1 single-year loader (preserved
as historical reference; not modified).

Usage examples:
    # Full real load (1901-2023). For unattended Claude-Code background
    # bash use, add --yes to suppress confirmation prompts.
    python ingest_full.py --yes

    # Dry-run (transforms only, no DB writes; uses .dryrun-suffixed files)
    python ingest_full.py --dry-run

    # Single year (idempotent: replaces existing rows for that year)
    python ingest_full.py --year-only 1925 --yes

    # Bounded range
    python ingest_full.py --from-year 1901 --to-year 1920 --yes

    # Force restart (TRUNCATE all 11 tables, clear checkpoint)
    python ingest_full.py --force-restart --yes

    # Reload only the 4 reference tables
    python ingest_full.py --reload-reference --yes

    # Verify already-loaded years against checkpoint before resuming
    python ingest_full.py --verify-existing --yes

CHUNK STATUS (skeleton in chunk 1, logic landed incrementally):
    chunk 1: this skeleton — imports, constants, function stubs, main() outline
    chunk 2: value transforms + parameterized spec functions
    chunk 3: Checkpoint class (read/write/atomic save)
    chunk 4: progress logging setup
    chunk 5: stop-condition machinery (heartbeat, runtime cap, SIGINT)
    chunk 6: load_table with lenient missing-column logic
    chunk 7: main() body wiring everything together
"""

import argparse
import csv
import json
import logging
import os
import shutil
import signal
import sys
import threading
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import psycopg
from dotenv import load_dotenv


# ============================================================================
# Constants
# ============================================================================
DATA_ROOT = Path(r"C:\BaseballOracle\data")
INGEST_DIR = Path(r"C:\BaseballOracle\ingest")
ENV_PATH = Path(r"C:\BaseballOracle\.env")

# Version management:
#   EXPECTED_SCHEMA_VERSION is compared at startup against the latest
#     retro.schema_version row; mismatch halts before any DB writes. Bump
#     only when a schema migration lands (and bump the matching INSERT in
#     schema/schema_version_migration.sql to record it in-DB).
#   SCRIPT_VERSION is informational — written to checkpoint metadata for
#     post-hoc traceability. Bump on substantive script changes.
EXPECTED_SCHEMA_VERSION = "phase2-2026-04-29"
SCRIPT_VERSION = "ingest_full.py@2026-04-29"

DEFAULT_FROM_YEAR = 1901
DEFAULT_TO_YEAR = 2023

MIN_FREE_GB = 10
DEFAULT_MAX_RUNTIME_HOURS = 8.0
STUCK_THRESHOLD_SECONDS = 600
HEARTBEAT_INTERVAL_SECONDS = 30
ROW_PROGRESS_BATCH = 10000

REFERENCE_TABLES = [
    "retro.relatives",
    "retro.players",
    "retro.ballparks",
    "retro.teams",
]
YEAR_TABLES = [
    "retro.plays",
    "retro.teamstats",
    "retro.fielding",
    "retro.pitching",
    "retro.batting",
    "retro.players_team_year",
    "retro.games",
]
ALL_DATA_TABLES = YEAR_TABLES + REFERENCE_TABLES  # children-first for TRUNCATE

# NOT NULL DB columns per table (audit 2026-04-25). load_table uses this to
# decide between NULL-fill (lenient) and halt-loud when a CSV column is missing.
NOT_NULL_COLS = {
    "retro.players":           {"id"},
    "retro.players_team_year": {"id", "team", "year"},
    "retro.relatives":         {"id1", "relation", "id2"},
    "retro.teams":             {"team"},
    "retro.ballparks":         {"parkid"},
    "retro.games":             {"gid"},
    "retro.batting":           {"gid", "id", "team", "stattype"},
    "retro.pitching":          {"gid", "id", "team", "stattype"},
    "retro.fielding":          {"gid", "id", "team", "stattype"},
    "retro.teamstats":         {"gid", "team", "stattype"},
    "retro.plays":             {"gid", "pn"},
}


# Per CLAUDE.md §4a Item 27: gids whose plays.csv rows are excluded from
# load due to data integrity issues that prevent clean ingest of the plays
# while leaving gameinfo / teamstats intact. Filter applies in load_table
# only when table == 'retro.plays'. Other tables for these gids load normally.
SKIP_PLAYS_GIDS = frozenset({
    'BLG194905152',  # 1949 doubleheader game 2: 134 plays for this gid contain
                     # play sequences from another mis-merged game (BLG194905151
                     # is missing from gameinfo but its plays appear here).
                     # See CLAUDE.md §4a Item 27.
})


# ============================================================================
# Value transforms
# CSV cells arrive as strings (already .strip()'d by load_table per the
# universal-strip convention). These convert to typed Python values; None
# becomes NULL on the COPY stream.
# ============================================================================
def passthrough(v):
    return None if v == "" else v


# Retrosheet uncertainty markers that should map to NULL in any halt-prone
# transform. Documented in CLAUDE.md §4 items 19-20:
#   '?'        — generic value-unknown marker (Negro League fielding.d_pos
#                in 1937-38; teamstats numeric columns in 1945-46)
#   'x' / 'X'  — "team did not bat in this inning" (teamstats inn5..inn9
#                across 1937-49)
#   'unknown'  — older weather-data marker for games.temp/windspeed
#                (1950, 1969-70). Distinct from item 8's numeric sentinels
#                (temp=0, windspeed=-1). Case-insensitive.
_NULL_SENTINELS_LOWER = frozenset({"?", "x", "unknown"})


def _is_null_sentinel(v: str) -> bool:
    """True if v is a Retrosheet uncertainty marker that should map to NULL."""
    return v.lower() in _NULL_SENTINELS_LOWER


def to_int(v):
    if v is None or v == "":
        return None
    if _is_null_sentinel(v):
        return None
    return int(v)


def to_float(v):
    if v is None or v == "":
        return None
    if _is_null_sentinel(v):
        return None
    return float(v)


def to_bool(v):
    """'1'/'true'/'t'/'y' -> True; '0'/'false'/'f'/'n' -> False; '' -> None.
    Recognized null sentinels (per CLAUDE.md §4 items 19-20) also map to None."""
    if v is None or v == "":
        return None
    if _is_null_sentinel(v):
        return None
    s = str(v).strip().lower()
    if s in ("1", "true", "t", "y", "yes"):
        return True
    if s in ("0", "false", "f", "n", "no"):
        return False
    raise ValueError(f"bad boolean value: {v!r}")


def to_date_yyyymmdd(v):
    """Retrosheet game-level dates are always full YYYYMMDD (per CLAUDE.md
    §4 item 9). Partial dates ('00' month/day) return None — they shouldn't
    occur at game grain; if they do, the dry-run will surface them."""
    if v is None or v == "":
        return None
    if len(v) != 8:
        raise ValueError(f"bad YYYYMMDD date: {v!r}")
    yyyy, mm, dd = v[0:4], v[4:6], v[6:8]
    if mm == "00" or dd == "00":
        return None
    return date(int(yyyy), int(mm), int(dd))


def to_date_mdy(v):
    """Parse M/D/YYYY (used by ballparks.start/end). Blank -> None."""
    if v is None or v == "":
        return None
    parts = v.split("/")
    if len(parts) != 3:
        raise ValueError(f"bad M/D/YYYY date: {v!r}")
    m, d, y = parts
    return date(int(y), int(m), int(d))


# ============================================================================
# Field builder
# ============================================================================
def _build_fields(ordered, int_cols=(), bool_cols=(), date_yyyymmdd_cols=(),
                  date_mdy_cols=(), float_cols=(), rename_csv_to_db=None):
    """
    Build (csv_header_lower, db_column, transform) tuples.
    rename_csv_to_db: for a DB column whose CSV header is different
      (pitching.is_save <- 'save'; plays.pitch_count <- 'count').
    """
    rename_csv_to_db = rename_csv_to_db or {}
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


# ============================================================================
# Per-table specs
# Reference specs (teams, ballparks, players, relatives) take no year and
# read from data/ root. Year specs take a year and compute the per-year
# CSV path.
# ============================================================================
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
        "fields": _build_fields(ordered, float_cols=("height", "weight")),
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


def spec_games(year):
    year_dir = DATA_ROOT / str(year)
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
        "csv": year_dir / f"{year}gameinfo.csv",
        "fields": _build_fields(
            ordered,
            int_cols=("number", "innings", "timeofgame",
                      "temp", "windspeed", "vruns", "hruns", "season",
                      "tiebreaker"),
            bool_cols=("usedh", "htbf"),
            date_yyyymmdd_cols=("date",),
        ),
        "extras": [],
    }


def spec_players_team_year(year):
    """The 'year' column is synthetic (per CLAUDE.md §3 design note 10):
    not in the CSV, supplied via extras from the folder name."""
    year_dir = DATA_ROOT / str(year)
    ordered = ["id", "last", "first", "bat", "throw", "team", "pos"]
    return {
        "table": "retro.players_team_year",
        "csv": year_dir / f"{year}allplayers.csv",
        "fields": _build_fields(ordered),
        "extras": [("year", year)],
    }


def spec_batting(year):
    year_dir = DATA_ROOT / str(year)
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
        "csv": year_dir / f"{year}batting.csv",
        "fields": _build_fields(
            ordered,
            int_cols=int_cols,
            bool_cols=("dh", "ph", "pr"),
            date_yyyymmdd_cols=("date",),
        ),
        "extras": [],
    }


def spec_pitching(year):
    """CSV header is 'save'; DB column is 'is_save' (renamed in schema for
    LLM-safety; reserved-word adjacency)."""
    year_dir = DATA_ROOT / str(year)
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
        "csv": year_dir / f"{year}pitching.csv",
        "fields": _build_fields(
            ordered,
            int_cols=int_cols,
            bool_cols=("wp", "lp", "is_save", "p_gs", "p_gf", "p_cg"),
            date_yyyymmdd_cols=("date",),
            rename_csv_to_db={"save": "is_save"},
        ),
        "extras": [],
    }


def spec_fielding(year):
    year_dir = DATA_ROOT / str(year)
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
        "csv": year_dir / f"{year}fielding.csv",
        "fields": _build_fields(
            ordered,
            int_cols=int_cols,
            bool_cols=("d_gs",),
            date_yyyymmdd_cols=("date",),
        ),
        "extras": [],
    }


def spec_teamstats(year):
    year_dir = DATA_ROOT / str(year)
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
        "csv": year_dir / f"{year}teamstats.csv",
        "fields": _build_fields(
            ordered,
            int_cols=int_cols,
            date_yyyymmdd_cols=("date",),
        ),
        "extras": [],
    }


def spec_plays(year):
    """CSV header is 'count'; DB column is 'pitch_count' (renamed in schema
    for LLM-safety; reserved-word adjacency)."""
    year_dir = DATA_ROOT / str(year)
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
        "csv": year_dir / f"{year}plays.csv",
        "fields": _build_fields(
            ordered,
            int_cols=int_cols,
            rename_csv_to_db={"count": "pitch_count"},
        ),
        "extras": [],
    }


# Stage groupings. Year specs are loaded in this order inside one transaction.
REFERENCE_SPEC_FNS = [spec_teams, spec_ballparks, spec_players, spec_relatives]
YEAR_SPEC_FNS = [
    spec_games,
    spec_players_team_year,
    spec_batting,
    spec_pitching,
    spec_fielding,
    spec_teamstats,
    spec_plays,
]


# ============================================================================
# Checkpoint
#
# Path-agnostic by design — caller (main) chooses:
#   real run  → ingest/.ingest_progress.json
#   dry-run   → ingest/.ingest_progress.json.dryrun
# Defense in depth: each checkpoint also carries a "mode" tag ("real" or
# "dryrun") set at initialize() and verified at load(). A cross-mode load
# (e.g. real-run pointed at the dryrun file) raises immediately, so even
# if someone manually swapped paths or copied files, the run halts before
# touching the DB.
#
# Atomic write contract (every save):
#   1. write to <path>.tmp
#   2. flush Python buffer
#   3. os.fsync — flush OS buffer to disk
#   4. os.replace(tmp, path) — atomic rename on Windows + POSIX
# A crash at any step leaves either the prior checkpoint intact (steps 1-3)
# or the new checkpoint complete (step 4); never a torn file.
# ============================================================================
class Checkpoint:
    def __init__(self, path: Path, dry_run: bool):
        self.path = path
        self.dry_run = dry_run
        self._mode_str = "dryrun" if dry_run else "real"
        # In-memory only; stamped into per_year entries by upsert_year().
        # One Checkpoint instance ↔ one invocation ↔ one current_run_id.
        self.current_run_id = str(uuid.uuid4())
        self.state: Optional[dict] = self._load()

    def _load(self) -> Optional[dict]:
        if not self.path.exists():
            return None
        with self.path.open("r", encoding="utf-8") as f:
            state = json.load(f)
        loaded_mode = state.get("mode")
        if loaded_mode is None:
            raise RuntimeError(
                f"Checkpoint {self.path} has no 'mode' tag; cannot determine "
                f"real vs dry-run. Inspect manually."
            )
        if loaded_mode != self._mode_str:
            raise RuntimeError(
                f"Checkpoint mode mismatch: file '{self.path.name}' is "
                f"'{loaded_mode}', runtime expects '{self._mode_str}'. "
                f"Refusing to proceed."
            )
        return state

    def exists(self) -> bool:
        return self.state is not None

    def is_reference_loaded(self) -> bool:
        return (self.state is not None and
                self.state.get("reference_tables_loaded", {}).get("loaded", False))

    def last_completed_year(self) -> Optional[int]:
        if self.state is None:
            return None
        return self.state.get("last_completed_year")

    def initialize(self):
        """Build a fresh state dict. Caller must save() to persist."""
        now = datetime.now(timezone.utc).isoformat()
        self.state = {
            "mode": self._mode_str,
            "schema_version": EXPECTED_SCHEMA_VERSION,
            "script_version": SCRIPT_VERSION,
            "started_at": now,
            "last_updated_at": now,
            "reference_tables_loaded": {"loaded": False},
            "last_completed_year": None,
            "skipped_years": [],
            "row_counts_cumulative": {
                t.split(".")[1]: 0 for t in YEAR_TABLES
            },
            "per_year": [],
        }

    def begin_run(self):
        """Mark the start of THIS invocation: bump top-level started_at to NOW
        and persist. Called once per main() startup (after load/initialize).
        Top-level started_at tracks the current run; per-year entries carry
        their own started_at + run_id from the run that loaded them, so the
        audit trail stays historically accurate across resumes."""
        self.state["started_at"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def mark_reference_loaded(self, row_counts: dict):
        self.state["reference_tables_loaded"] = {
            "loaded": True,
            "loaded_at": datetime.now(timezone.utc).isoformat(),
            "row_counts": row_counts,
        }
        self.save()

    def upsert_year(self, year: int, started_at: datetime,
                     row_counts: dict, missing_columns: list,
                     duration_s: float):
        """Atomic remove-then-add for a single year. If `year` is already
        in per_year, its row_counts are decremented from the cumulatives
        and the entry is removed before the new one is appended. One
        in-memory mutation, one save(). Use this on every successful year
        commit (first-time load or re-load) so the checkpoint mutation
        happens exactly once after the DB transaction commits."""
        existing = [e for e in self.state["per_year"] if e["year"] == year]
        if existing:
            self.state["per_year"] = [
                e for e in self.state["per_year"] if e["year"] != year
            ]
            for entry in existing:
                for tbl, cnt in entry["row_counts"].items():
                    self.state["row_counts_cumulative"][tbl] = (
                        self.state["row_counts_cumulative"].get(tbl, 0) - cnt
                    )
        self.state["per_year"].append({
            "year": year,
            "run_id": self.current_run_id,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration_s, 2),
            "row_counts": row_counts,
            "missing_columns": missing_columns,
        })
        self.state["last_completed_year"] = max(
            (e["year"] for e in self.state["per_year"]), default=None
        )
        for tbl, cnt in row_counts.items():
            self.state["row_counts_cumulative"][tbl] = (
                self.state["row_counts_cumulative"].get(tbl, 0) + cnt
            )
        self.save()

    def record_skipped(self, year: int, reason: str):
        """Idempotent: only the first reason for a given year is recorded."""
        if any(e["year"] == year for e in self.state["skipped_years"]):
            return
        self.state["skipped_years"].append({"year": year, "reason": reason})
        self.save()

    def save(self):
        """Atomic write: tmp + fsync + os.replace. Always updates last_updated_at."""
        self.state["last_updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp = self.path.parent / (self.path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def delete(self):
        if self.path.exists():
            self.path.unlink()
        self.state = None


# ============================================================================
# Logging setup
# Two handlers: stdout (live monitoring) + file (post-hoc review).
# File path mirrors the checkpoint convention:
#   real run → ingest/.ingest_progress.log
#   dry-run  → ingest/.ingest_progress.log.dryrun
# Prior log is rotated to a timestamped backup so per-invocation history
# is preserved without unbounded append.
# ============================================================================
def configure_logging(dry_run: bool, verbose: bool) -> Path:
    suffix = ".dryrun" if dry_run else ""
    log_path = INGEST_DIR / f".ingest_progress.log{suffix}"

    if log_path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        rotated = log_path.parent / (log_path.name + f".{ts}")
        log_path.rename(rotated)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()  # clean re-config (defensive)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    return log_path


# ============================================================================
# Stop-condition machinery
#
# HeartbeatMonitor: Windows-safe — pure threading.Event + time.monotonic, no
#   signal-based timers. Background daemon thread watches per-row progress.
#
# SIGINT handler: first Ctrl-C → graceful (set event, main loop halts after
#   current row + writes halt reason). Second Ctrl-C → os._exit(2). os._exit
#   (not sys.exit) is intentional: sys.exit raises SystemExit which still
#   runs `finally` clauses; if the user is hitting Ctrl-C twice they're
#   impatient and want OUT, not another round of cleanup.
#
# write_halt_reason: plain key:value text (per design §7), cheaper to scan
#   at 6am than JSON. Post-hoc tools can still parse line-by-line.
#
# check_disk_space: shutil.disk_usage on the data partition; halt if
#   free < MIN_FREE_GB. Called at startup AND between years so a slowly
#   filling disk is caught before COPY corrupts mid-flight.
# ============================================================================
class HeartbeatMonitor:
    """
    Main loop calls update() every ROW_PROGRESS_BATCH rows. The monitor
    wakes every interval_seconds via Event.wait (which is also how stop()
    cancels the wait) and checks elapsed since last update. If elapsed
    exceeds stuck_seconds, sets stuck_flag (a threading.Event) and exits;
    main loop polls stuck_flag between rows and raises HaltSignal.
    """
    def __init__(self, stuck_seconds=STUCK_THRESHOLD_SECONDS,
                 interval_seconds=HEARTBEAT_INTERVAL_SECONDS):
        self._lock = threading.Lock()
        self._last_progress = time.monotonic()
        self._context = "(idle)"
        self._stuck_seconds = stuck_seconds
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.stuck_flag = threading.Event()

    def start(self):
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="HeartbeatMonitor"
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def update(self):
        """Called by the main loop on each row-batch boundary."""
        with self._lock:
            self._last_progress = time.monotonic()

    def set_context(self, ctx: str):
        """Called when starting a new CSV — also resets the progress clock,
        so per-CSV setup time isn't counted against this CSV's stuck budget."""
        with self._lock:
            self._context = ctx
            self._last_progress = time.monotonic()

    def _run(self):
        # Event.wait(timeout) returns True if stop is set, False on timeout.
        # Using wait() rather than time.sleep() lets stop() unblock instantly.
        while not self._stop.wait(self._interval):
            with self._lock:
                elapsed = time.monotonic() - self._last_progress
                ctx = self._context
            if elapsed > self._stuck_seconds:
                logging.error(
                    f"STUCK: no progress for {elapsed:.0f}s in {ctx}"
                )
                self.stuck_flag.set()
                return
            logging.debug(
                f"  [heartbeat] {ctx}: last progress {elapsed:.0f}s ago"
            )


# graceful_shutdown is module-level so the SIGINT handler (a closure-free
# function) and the main loop both see the same Event instance.
graceful_shutdown = threading.Event()
_sigint_count = [0]  # list wrap so handler can mutate without 'nonlocal'


def install_sigint_handler():
    def handler(signum, frame):
        _sigint_count[0] += 1
        if _sigint_count[0] >= 2:
            logging.error("Second Ctrl-C — hard exit")
            os._exit(2)
        logging.warning(
            "SIGINT — graceful shutdown after current row "
            "(press Ctrl-C again for hard exit)"
        )
        graceful_shutdown.set()
    signal.signal(signal.SIGINT, handler)


def write_halt_reason(*, reason: str, year: Optional[int],
                       stage: Optional[str], csv_path: Optional[str],
                       error_class: str, message: str,
                       last_completed_year: Optional[int],
                       partial_state: str):
    path = INGEST_DIR / ".ingest_halt_reason.txt"
    with path.open("w", encoding="utf-8") as f:
        f.write(f"timestamp: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"year: {year if year is not None else '(n/a)'}\n")
        f.write(f"stage: {stage or '(n/a)'}\n")
        f.write(f"csv: {csv_path or '(n/a)'}\n")
        f.write(f"condition: {reason}\n")
        f.write(f"error_class: {error_class}\n")
        f.write(f"message: {message}\n")
        f.write(
            f"last_completed_year: "
            f"{last_completed_year if last_completed_year is not None else '(n/a)'}\n"
        )
        f.write(f"partial_state: {partial_state}\n")
    logging.error(f"Halt reason written to {path}")


def check_disk_space(path: Path):
    free_bytes = shutil.disk_usage(path).free
    free_gb = free_bytes / (1024 ** 3)
    if free_gb < MIN_FREE_GB:
        raise RuntimeError(
            f"Disk space low at {path}: {free_gb:.1f}GB free, "
            f"need >= {MIN_FREE_GB}GB"
        )


class HaltSignal(Exception):
    """Clean halt — caught by main, triggers halt-reason write and exit."""


# ============================================================================
# load_table + supporting helpers
#
# load_table is the heart of the script: read one CSV, run transforms, write
# via COPY (real run) or discard (dry-run). The chunk-6 delta vs
# ingest_1998.py is the lenient-missing-column branch — see design §8.
# ============================================================================
def get_db_schema_version(conn) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT version FROM retro.schema_version "
            "ORDER BY applied_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("retro.schema_version is empty")
        return row[0]


def apply_pg_tuning(conn):
    """Session-level SET (NOT SET LOCAL).

    Why session-level: the connection lives for the whole script, and we
    want both settings to apply to every per-year transaction without
    re-issuing them inside each `with conn.transaction()` block. With
    autocommit=True (chunk 7), SET runs as a standalone statement and
    persists for the connection's lifetime.

    SET LOCAL would only apply to the current transaction and revert at
    commit — wrong shape for our per-year-tx model.

    Settings:
      synchronous_commit=OFF  — small-but-real speedup on COPY commits.
        Crash window: a recently-committed year may roll back. Acceptable
        because the checkpoint is written *after* commit; on restart we
        replay any year not in checkpoint.
      maintenance_work_mem=1GB — helps if anything triggers VACUUM or
        index work mid-run; harmless to plain COPY."""
    with conn.cursor() as cur:
        cur.execute("SET synchronous_commit = OFF")
        cur.execute("SET maintenance_work_mem = '1GB'")
    logging.info("Applied session PG tuning: "
                 "synchronous_commit=OFF, maintenance_work_mem=1GB")


def _missing_log_path(dry_run: bool) -> Path:
    suffix = ".dryrun" if dry_run else ""
    return INGEST_DIR / f".missing_columns.log{suffix}"


def log_missing_columns(year, table: str,
                         missing_csv_headers: list, dry_run: bool):
    """Append one line per (year, table). Format:
       <iso8601> year=<N|ref> table=retro.X missing=[col1,col2,...]"""
    path = _missing_log_path(dry_run)
    ts = datetime.now(timezone.utc).isoformat()
    yr = year if year is not None else "(ref)"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{ts} year={yr} table={table} "
                f"missing=[{','.join(missing_csv_headers)}]\n")


def log_unexpected_columns(year, table: str,
                            unexpected_headers: list, dry_run: bool):
    """Same file as missing; direction='unexpected'. Useful for spotting
    fields Retrosheet added that we don't yet ingest."""
    path = _missing_log_path(dry_run)
    ts = datetime.now(timezone.utc).isoformat()
    yr = year if year is not None else "(ref)"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{ts} year={yr} table={table} "
                f"unexpected=[{','.join(unexpected_headers)}]\n")


def _check_halt_signals(heartbeat: HeartbeatMonitor):
    """Polled between rows. Raise HaltSignal if either flag is set."""
    if heartbeat.stuck_flag.is_set():
        raise HaltSignal("stuck-no-progress")
    if graceful_shutdown.is_set():
        raise HaltSignal("sigint-graceful")


def load_table(conn, spec, *, year: Optional[int], dry_run: bool,
                heartbeat: HeartbeatMonitor, verbose: bool) -> tuple:
    """
    Load one table from one CSV. Returns (rows_loaded, missing_csv_headers).

    Lenient missing-column branch (the chunk-6 delta vs ingest_1998.py):
      - missing column ∈ NOT_NULL_COLS[table]  → halt loud (RuntimeError)
      - missing column nullable                → omit from COPY col list,
                                                  Postgres fills NULL by default
      - extra CSV column not in spec           → silently skip (logged)

    Raises:
      RuntimeError on per-row transform failure or NOT NULL CSV col missing.
      HaltSignal on stuck or SIGINT (caught by main, halt reason written).
      FileNotFoundError if the CSV is missing — caller is responsible for
        per-year CSV pre-flight before calling this.
    """
    table = spec["table"]
    csv_path = spec["csv"]
    fields = spec["fields"]
    extras = spec["extras"]

    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))

    heartbeat.set_context(f"{year}/{table.split('.')[-1]}/{csv_path.name}")
    logging.info(f"  [{table}] {csv_path.name}: starting")

    with open(csv_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        try:
            raw_header = next(reader)
        except StopIteration:
            raise RuntimeError(f"{csv_path}: empty CSV")

        actual_headers = [h.lower() for h in raw_header]
        actual_set = set(actual_headers)

        covered_fields = [(ch, dc, x) for (ch, dc, x) in fields if ch in actual_set]
        missing_fields = [(ch, dc, x) for (ch, dc, x) in fields if ch not in actual_set]

        # Lenient missing-column with NOT NULL halt branch (design §8).
        not_null_for_table = NOT_NULL_COLS.get(table, set())
        missing_db_cols = {dc for (_, dc, _) in missing_fields}
        problematic = missing_db_cols & not_null_for_table
        if problematic:
            raise RuntimeError(
                f"{csv_path.name}: NOT NULL DB columns missing in CSV: "
                f"{sorted(problematic)} — halting per design §8 NOT NULL guard"
            )

        if missing_fields:
            log_missing_columns(
                year, table,
                sorted(ch for (ch, _, _) in missing_fields),
                dry_run,
            )
            logging.info(
                f"  [{table}] NULL-filling missing columns: "
                f"{sorted(ch for (ch, _, _) in missing_fields)}"
            )

        expected_set = {ch for (ch, _, _) in fields}
        unexpected = sorted(actual_set - expected_set)
        if unexpected:
            log_unexpected_columns(year, table, unexpected, dry_run)
            logging.info(
                f"  [{table}] silently skipping unexpected CSV columns: "
                f"{unexpected}"
            )

        # COPY column list = covered DB cols + extras (e.g., synthetic year).
        # Missing nullable columns are NOT in this list, so Postgres fills
        # them with NULL (the default for a nullable column with no DEFAULT).
        copy_db_cols = [dc for (_, dc, _) in covered_fields] + [e[0] for e in extras]
        extra_values = [e[1] for e in extras]
        csv_index_for = {h: i for i, h in enumerate(actual_headers)}

        # Skip-filter setup (per SKIP_PLAYS_GIDS / CLAUDE.md §4a Item 27).
        # Pre-compute gid column index so the row-loop check is O(1). Only
        # retro.plays uses this filter; for all other tables gid_skip_idx is
        # None and the row-loop check is skipped.
        gid_skip_idx = (csv_index_for.get('gid')
                        if table == 'retro.plays' and SKIP_PLAYS_GIDS
                        else None)

        plan = [
            (csv_index_for[ch], out_i, xform)
            for out_i, (ch, _, xform) in enumerate(covered_fields)
        ]
        copy_sql = f"COPY {table} ({', '.join(copy_db_cols)}) FROM STDIN"
        out_size = len(covered_fields)

        def transform_row(lineno, row):
            """Per-row transform. Universal .strip() at the CSV read boundary
            per CLAUDE.md §5 (handles whitespace artifacts like 'VMA ' in
            1946 allplayers.csv); then per-column xform."""
            try:
                out = [None] * out_size
                for csv_i, out_i, xform in plan:
                    raw_val = row[csv_i] if csv_i < len(row) else ""
                    out[out_i] = xform(raw_val.strip())
                return out + list(extra_values)
            except Exception as e:
                raise RuntimeError(
                    f"{csv_path.name} line {lineno}: "
                    f"{type(e).__name__}: {e}; row[:8]={row[:8]}"
                )

        loaded = 0
        skipped = 0
        if dry_run:
            for lineno, row in enumerate(reader, start=2):
                _check_halt_signals(heartbeat)
                if (gid_skip_idx is not None
                        and gid_skip_idx < len(row)
                        and row[gid_skip_idx].strip() in SKIP_PLAYS_GIDS):
                    skipped += 1
                    continue
                transform_row(lineno, row)  # result discarded; we just want errors to surface
                loaded += 1
                if loaded % ROW_PROGRESS_BATCH == 0:
                    heartbeat.update()
                    if verbose:
                        logging.debug(
                            f"  [{table}] {csv_path.name}: {loaded} rows (dry-run)"
                        )
        else:
            with conn.cursor() as cur:
                with cur.copy(copy_sql) as cpy:
                    for lineno, row in enumerate(reader, start=2):
                        _check_halt_signals(heartbeat)
                        if (gid_skip_idx is not None
                                and gid_skip_idx < len(row)
                                and row[gid_skip_idx].strip() in SKIP_PLAYS_GIDS):
                            skipped += 1
                            continue
                        full_row = transform_row(lineno, row)
                        cpy.write_row(full_row)
                        loaded += 1
                        if loaded % ROW_PROGRESS_BATCH == 0:
                            heartbeat.update()
                            if verbose:
                                logging.debug(
                                    f"  [{table}] {csv_path.name}: {loaded} rows"
                                )

        if skipped > 0:
            logging.info(
                f"  [{table}] {csv_path.name}: skipped {skipped} rows "
                f"matching SKIP_PLAYS_GIDS"
            )
        logging.info(f"  [{table}] {csv_path.name}: {loaded} rows loaded")
        return loaded, sorted(ch for (ch, _, _) in missing_fields), skipped


def load_reference_tables(conn, *, dry_run: bool,
                            heartbeat: HeartbeatMonitor,
                            verbose: bool) -> dict:
    """Stage 1. One transaction (real run). TRUNCATE the four reference
    tables children-first, then COPY each. Returns row counts keyed by
    short table name."""
    logging.info("=" * 64)
    logging.info("STAGE 1 — reference tables")
    logging.info("=" * 64)
    counts: dict = {}

    if dry_run:
        for fn in REFERENCE_SPEC_FNS:
            spec = fn()
            n, _, _ = load_table(conn, spec, year=None, dry_run=True,
                              heartbeat=heartbeat, verbose=verbose)
            counts[spec["table"].split(".")[1]] = n
        logging.info("  (dry-run: no DB writes)")
        return counts

    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE {', '.join(REFERENCE_TABLES)}")
        for fn in REFERENCE_SPEC_FNS:
            spec = fn()
            n, _, _ = load_table(conn, spec, year=None, dry_run=False,
                              heartbeat=heartbeat, verbose=verbose)
            counts[spec["table"].split(".")[1]] = n
    return counts


def load_year(conn, year: int, *, replace_existing: bool, dry_run: bool,
               heartbeat: HeartbeatMonitor, verbose: bool):
    """Stages 2-4 atomically: ONE transaction per year covering an
    optional pre-load DELETE (when reloading an already-loaded year)
    plus games + per-game stats + plays. A failure inside this
    transaction rolls back the entire year — including the DELETE —
    leaving prior committed state intact.

    Caller (main) is responsible for the per-year CSV pre-flight (skip
    the year and record_skipped if any expected CSV is missing) and for
    deciding whether `replace_existing=True` (year already in checkpoint).
    Inside this function, all CSVs are assumed present.

    Returns (row_counts, missing_summary, skipped_total)."""
    logging.info("=" * 64)
    logging.info(f"YEAR {year}")
    logging.info("=" * 64)

    counts: dict = {}
    missing_summary: list = []
    skipped_total = 0  # sum of plays rows skipped per SKIP_PLAYS_GIDS

    def _do_load():
        nonlocal skipped_total
        for fn in YEAR_SPEC_FNS:
            spec = fn(year)
            n, missing_cols, n_skipped = load_table(
                conn, spec, year=year, dry_run=dry_run,
                heartbeat=heartbeat, verbose=verbose,
            )
            counts[spec["table"].split(".")[1]] = n
            skipped_total += n_skipped
            if missing_cols:
                missing_summary.append({
                    "table": spec["table"], "columns": missing_cols
                })

    if dry_run:
        _do_load()
    else:
        with conn.transaction():
            if replace_existing:
                _delete_year_rows_in_txn(conn, year)
            _do_load()

    return counts, missing_summary, skipped_total


# ============================================================================
# Orchestration helpers + main()
# ============================================================================
def parse_args():
    p = argparse.ArgumentParser(
        description="Phase 2 multi-year Retrosheet ingest."
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Run transforms; do not write to DB.")
    p.add_argument("--data-root", type=str, default=None,
                   help="Override DATA_ROOT (for testing with a scratch data "
                        "directory). Default: C:\\BaseballOracle\\data")
    p.add_argument("--database", type=str, default=None,
                   help="Override target database. "
                        "Default: PG_DATABASE env var or .env value.")
    p.add_argument("--from-year", type=int, default=DEFAULT_FROM_YEAR)
    p.add_argument("--to-year", type=int, default=DEFAULT_TO_YEAR)
    p.add_argument("--year-only", type=int, default=None,
                   help="Single year. Mutually exclusive with from/to-year. "
                        "Idempotent: if year is already in checkpoint, deletes "
                        "existing rows for that year before reloading.")
    p.add_argument("--force-restart", action="store_true",
                   help="TRUNCATE all 11 tables and clear checkpoint.")
    p.add_argument("--reload-reference", action="store_true",
                   help="TRUNCATE only the 4 reference tables and reload.")
    p.add_argument("--verify-existing", action="store_true",
                   help="Re-count loaded years against checkpoint on resume.")
    p.add_argument("--verbose", action="store_true",
                   help="Per-N-row CSV progress in log file.")
    p.add_argument("--max-runtime-hours", type=float,
                   default=DEFAULT_MAX_RUNTIME_HOURS,
                   help=f"Wall-clock cap (default {DEFAULT_MAX_RUNTIME_HOURS}h).")
    p.add_argument("--no-pg-tuning", action="store_true",
                   help="Skip session-level synchronous_commit/work_mem SETs.")
    p.add_argument("--yes", action="store_true",
                   help="Suppress confirmation prompts (required for "
                        "unattended/background runs).")
    args = p.parse_args()

    if args.year_only is not None:
        if (args.from_year != DEFAULT_FROM_YEAR
                or args.to_year != DEFAULT_TO_YEAR):
            p.error("--year-only is mutually exclusive with --from-year/--to-year")
        args.from_year = args.year_only
        args.to_year = args.year_only

    if args.from_year > args.to_year:
        p.error("--from-year must be <= --to-year")

    return args


def confirm(prompt: str, yes: bool) -> bool:
    """Interactive y/N prompt. Auto-confirms with --yes (required for
    unattended/background runs). EOFError → treat as N (no TTY)."""
    if yes:
        logging.info(f"AUTO-CONFIRM (--yes): {prompt}")
        return True
    logging.warning(prompt + " [y/N]")
    try:
        ans = input().strip().lower()
    except EOFError:
        logging.warning("No TTY for confirmation; treat as N")
        return False
    return ans in ("y", "yes")


def inventory_years(from_year: int, to_year: int) -> tuple:
    """Return (present_years, missing_year_dirs) for the inclusive range."""
    present, missing = [], []
    for y in range(from_year, to_year + 1):
        if (DATA_ROOT / str(y)).exists():
            present.append(y)
        else:
            missing.append(y)
    return present, missing


def missing_csvs_for_year(year: int) -> list:
    """Names of expected CSVs missing for `year`. Per phase2_plan.md §1,
    if any of the 7 expected CSVs is missing the whole year is skipped."""
    missing = []
    for fn in YEAR_SPEC_FNS:
        csv_path = fn(year)["csv"]
        if not csv_path.exists():
            missing.append(csv_path.name)
    return missing


def _delete_year_rows_in_txn(conn, year: int):
    """Delete rows for `year` from all year-bearing tables. Runs inside
    the caller's open transaction — does NOT open its own. Caller must
    ensure DELETE + LOAD are wrapped in a single conn.transaction() so
    that a load failure rolls back the DELETE too (per design §5
    atomic-year guarantee).

    Order: plays first (uses a games join to identify the year, so games
    rows must still be present). Then the date-bearing year tables. Then
    players_team_year (uses synthetic year column). Then games last."""
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM retro.plays
            WHERE gid IN (
                SELECT gid FROM retro.games
                WHERE EXTRACT(year FROM date) = %s
            )
        """, (year,))
        for tbl in ("retro.teamstats", "retro.batting",
                    "retro.pitching", "retro.fielding"):
            cur.execute(
                f"DELETE FROM {tbl} WHERE EXTRACT(year FROM date) = %s",
                (year,),
            )
        cur.execute(
            "DELETE FROM retro.players_team_year WHERE year = %s",
            (year,),
        )
        cur.execute(
            "DELETE FROM retro.games WHERE EXTRACT(year FROM date) = %s",
            (year,),
        )
    logging.info(f"Deleted existing rows for year {year} from all year tables.")


def verify_existing(conn, checkpoint: Checkpoint):
    """Compare cumulative row counts in checkpoint vs live DB. Halt on mismatch.
    Per design §4, this is gated by --verify-existing (default: trust checkpoint).
    """
    logging.info("Verifying loaded years against checkpoint…")
    cumulative = checkpoint.state.get("row_counts_cumulative", {})
    mismatches = []
    with conn.cursor() as cur:
        for tbl_short, claimed in cumulative.items():
            full = f"retro.{tbl_short}"
            cur.execute(f"SELECT count(*) FROM {full}")
            actual = cur.fetchone()[0]
            if actual != claimed:
                mismatches.append((full, claimed, actual))
                logging.error(f"  MISMATCH: {full} checkpoint={claimed} db={actual}")
            else:
                logging.info(f"  ok: {full} = {actual:,}")
    if mismatches:
        raise RuntimeError(
            f"--verify-existing found {len(mismatches)} table mismatch(es); "
            "refusing to resume"
        )


def write_summary(checkpoint: Checkpoint, total_runtime_s: float,
                   run_total_skipped_plays: int = 0,
                   run_years_with_skips: Optional[list] = None):
    """End-of-run report: per-table cumulative counts, skipped years,
    rolled-up missing-column patterns across years, and run-local
    SKIP_PLAYS_GIDS rollup."""
    state = checkpoint.state
    if state is None:
        return
    logging.info("=" * 64)
    logging.info("RUN SUMMARY")
    logging.info("=" * 64)
    logging.info(f"  current run started_at: {state['started_at']}")
    logging.info(f"  total_runtime: {total_runtime_s/60:.1f}m")
    logging.info(f"  years completed (cumulative): {len(state.get('per_year', []))}")
    logging.info(f"  years skipped: {len(state.get('skipped_years', []))}")
    if state.get("skipped_years"):
        for s in state["skipped_years"]:
            logging.info(f"    - {s['year']}: {s['reason']}")
    logging.info("  cumulative row counts:")
    for tbl, cnt in state.get("row_counts_cumulative", {}).items():
        logging.info(f"    retro.{tbl}: {cnt:>12,}")

    # Missing columns rolled up across years
    missing_by_col: dict = {}
    for entry in state.get("per_year", []):
        for table_entry in entry.get("missing_columns", []):
            for col in table_entry.get("columns", []):
                key = f"{table_entry['table']}.{col}"
                missing_by_col.setdefault(key, []).append(entry["year"])
    if missing_by_col:
        logging.info("  missing CSV columns (rolled up):")
        for key, years in sorted(missing_by_col.items()):
            yrs = sorted(set(years))
            yr_str = (f"{yrs[0]}-{yrs[-1]} ({len(yrs)} years)"
                      if len(yrs) > 5 else str(yrs))
            logging.info(f"    {key}: {yr_str}")

    # Plays-skip rollup for this run (per SKIP_PLAYS_GIDS / CLAUDE.md §4a Item 27)
    if run_total_skipped_plays > 0:
        logging.info(
            f"  plays rows skipped this run "
            f"(SKIP_PLAYS_GIDS={sorted(SKIP_PLAYS_GIDS)}): "
            f"{run_total_skipped_plays:,} rows across years "
            f"{run_years_with_skips or []}"
        )


def main():
    """Orchestration. See chunk-1 docstring for the high-level flow."""
    args = parse_args()
    log_path = configure_logging(args.dry_run, args.verbose)
    install_sigint_handler()

    # Apply --data-root override before any path consumers run.
    # global declaration is required because spec functions read the
    # module-level DATA_ROOT at call time and we mutate it here.
    global DATA_ROOT
    if args.data_root is not None:
        DATA_ROOT = Path(args.data_root)
    logging.info(f"DATA_ROOT: {DATA_ROOT}")

    logging.info("=" * 64)
    logging.info(
        f"ingest_full.py START "
        f"(script={SCRIPT_VERSION}, expected_schema={EXPECTED_SCHEMA_VERSION})"
    )
    logging.info(f"args: {vars(args)}")
    logging.info(f"log: {log_path}")
    logging.info("=" * 64)

    if not ENV_PATH.exists():
        logging.error(f"ENV not found at {ENV_PATH}")
        sys.exit(1)
    load_dotenv(ENV_PATH)

    dsn = {
        "host":     os.environ["PG_HOST"],
        "port":     os.environ["PG_PORT"],
        "user":     os.environ["PG_USER"],
        "password": os.environ["PG_PASSWORD"],
        "dbname":   os.environ["PG_DATABASE"],
    }
    if args.database is not None:
        dsn["dbname"] = args.database

    # Disk precheck (before any heavy work)
    try:
        check_disk_space(DATA_ROOT)
    except RuntimeError as e:
        write_halt_reason(
            reason="disk-space-low", year=None, stage=None, csv_path=None,
            error_class=type(e).__name__, message=str(e),
            last_completed_year=None,
            partial_state="(no transactions started)",
        )
        sys.exit(1)
    free_gb = shutil.disk_usage(DATA_ROOT).free / (1024 ** 3)
    logging.info(f"Disk OK: {free_gb:.1f}GB free at {DATA_ROOT}")

    # Year inventory (filesystem-only, no DB)
    present_years, missing_year_dirs = inventory_years(args.from_year, args.to_year)
    logging.info(
        f"Year folders in [{args.from_year}, {args.to_year}]: "
        f"{len(present_years)} present, {len(missing_year_dirs)} missing"
    )
    if missing_year_dirs:
        logging.warning(f"Missing year folders: {missing_year_dirs}")

    # Checkpoint path (real vs dry-run separation)
    cp_path = INGEST_DIR / (
        ".ingest_progress.json.dryrun" if args.dry_run
        else ".ingest_progress.json"
    )

    heartbeat = HeartbeatMonitor()
    heartbeat.start()

    overall_start = time.monotonic()
    last_completed_year_for_halt: Optional[int] = None
    current_year_for_halt: Optional[int] = None
    checkpoint: Optional[Checkpoint] = None
    # Run-local accumulators for SKIP_PLAYS_GIDS rollup at end-of-run.
    run_total_skipped_plays = 0
    run_years_with_skips: list = []

    logging.info(f"Connecting to database: {dsn['dbname']} on {dsn['host']}:{dsn['port']}")
    try:
        with psycopg.connect(autocommit=True, **dsn) as conn:
            logging.info(f"Connected to database: {dsn['dbname']}")
            # --- DB schema version match ---
            db_version = get_db_schema_version(conn)
            if db_version != EXPECTED_SCHEMA_VERSION:
                raise RuntimeError(
                    f"DB schema version mismatch: db={db_version} "
                    f"script-expects={EXPECTED_SCHEMA_VERSION}"
                )
            logging.info(f"Schema version OK: {db_version}")

            # --- PG tuning ---
            if not args.dry_run and not args.no_pg_tuning:
                apply_pg_tuning(conn)

            # --- Force-restart cleanup BEFORE Checkpoint construction
            # so a corrupt checkpoint file can still be wiped. ---
            if args.force_restart:
                if not confirm(
                    f"--force-restart will TRUNCATE all 11 retro tables and "
                    f"delete checkpoint at {cp_path}. Proceed?",
                    args.yes,
                ):
                    logging.info("Aborted by user.")
                    return
                if not args.dry_run:
                    with conn.cursor() as cur:
                        cur.execute(f"TRUNCATE {', '.join(ALL_DATA_TABLES)}")
                if cp_path.exists():
                    cp_path.unlink()
                logging.info("--force-restart: tables truncated, checkpoint cleared.")

            # --- Construct Checkpoint (mode-tag verification on load) ---
            checkpoint = Checkpoint(cp_path, args.dry_run)

            # --- Initialize if absent, with sanity guard for stale DB ---
            if not checkpoint.exists():
                if not args.dry_run:
                    with conn.cursor() as cur:
                        cur.execute("SELECT count(*) FROM retro.players")
                        np = cur.fetchone()[0]
                        cur.execute("SELECT count(*) FROM retro.games")
                        ng = cur.fetchone()[0]
                        if np > 0 or ng > 0:
                            raise RuntimeError(
                                f"No checkpoint but DB has data "
                                f"(players={np}, games={ng}). "
                                f"Use --force-restart to wipe and start fresh, "
                                f"or restore the checkpoint file."
                            )
                checkpoint.initialize()
                checkpoint.save()

            # --- Mark this invocation's start ---
            checkpoint.begin_run()

            # --- Checkpoint schema version match ---
            ck_version = checkpoint.state.get("schema_version")
            if ck_version != EXPECTED_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Checkpoint schema mismatch: checkpoint={ck_version} "
                    f"script-expects={EXPECTED_SCHEMA_VERSION}. "
                    f"Use --force-restart to start over."
                )

            # --- --verify-existing ---
            if args.verify_existing and not args.dry_run:
                verify_existing(conn, checkpoint)

            # --- Sanity: checkpoint says reference loaded but DB is empty ---
            if (checkpoint.is_reference_loaded() and not args.dry_run
                    and not args.reload_reference):
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM retro.players")
                    if cur.fetchone()[0] == 0:
                        raise RuntimeError(
                            "Checkpoint says reference loaded but retro.players "
                            "is empty. State is corrupt; use --force-restart "
                            "or --reload-reference."
                        )

            # --- Reference handling ---
            if args.reload_reference:
                if not confirm(
                    "--reload-reference will TRUNCATE the 4 reference tables. Proceed?",
                    args.yes,
                ):
                    logging.info("Aborted by user.")
                    return
                ref_counts = load_reference_tables(
                    conn, dry_run=args.dry_run,
                    heartbeat=heartbeat, verbose=args.verbose,
                )
                checkpoint.mark_reference_loaded(ref_counts)
            elif not checkpoint.is_reference_loaded():
                ref_counts = load_reference_tables(
                    conn, dry_run=args.dry_run,
                    heartbeat=heartbeat, verbose=args.verbose,
                )
                checkpoint.mark_reference_loaded(ref_counts)
            else:
                logging.info("Reference tables already loaded (per checkpoint); skipping.")

            # --- --year-only confirmation (when re-loading) ---
            already_done = {pe["year"] for pe in checkpoint.state.get("per_year", [])}
            if args.year_only is not None and args.year_only in already_done:
                if not confirm(
                    f"--year-only {args.year_only}: already in checkpoint. "
                    f"DELETE existing rows for that year and reload?",
                    args.yes,
                ):
                    logging.info("Aborted by user.")
                    return

            # --- Resume guard (skipped for --year-only) ---
            if args.year_only is None:
                last_completed = checkpoint.last_completed_year()
                if (last_completed is not None
                        and args.from_year <= last_completed
                        and not args.force_restart):
                    raise RuntimeError(
                        f"--from-year={args.from_year} would re-load year(s) "
                        f"<= {last_completed} already completed. Use "
                        f"--force-restart, --year-only N for a single-year "
                        f"reload, or --from-year > {last_completed}."
                    )

            # --- Per-year loop ---
            for year in range(args.from_year, args.to_year + 1):
                is_replace = year in already_done
                if is_replace and args.year_only is None:
                    # Resume case: skip years already done in a multi-year
                    # run. (--year-only deliberately re-loads via
                    # replace_existing.)
                    logging.info(f"[{year}] already loaded; skipping.")
                    continue

                # Wall-clock cap (clean halt before starting next year)
                elapsed_h = (time.monotonic() - overall_start) / 3600
                if elapsed_h >= args.max_runtime_hours:
                    logging.warning(
                        f"Wall-clock cap reached ({elapsed_h:.2f}h "
                        f">= {args.max_runtime_hours}h); halting before year {year}"
                    )
                    raise HaltSignal("wall-clock-cap")

                check_disk_space(DATA_ROOT)

                if not (DATA_ROOT / str(year)).exists():
                    checkpoint.record_skipped(year, "year folder missing")
                    logging.warning(f"[{year}] year folder missing; skipping.")
                    continue

                missing_csvs = missing_csvs_for_year(year)
                if missing_csvs:
                    reason = f"missing CSV(s): {missing_csvs}"
                    checkpoint.record_skipped(year, reason)
                    logging.warning(f"[{year}] {reason}; skipping year.")
                    continue

                current_year_for_halt = year
                year_started = datetime.now(timezone.utc)
                year_t0 = time.monotonic()

                counts, missing_summary, skipped_n = load_year(
                    conn, year, replace_existing=is_replace,
                    dry_run=args.dry_run,
                    heartbeat=heartbeat, verbose=args.verbose,
                )
                duration = time.monotonic() - year_t0

                if skipped_n > 0:
                    run_total_skipped_plays += skipped_n
                    run_years_with_skips.append(year)

                checkpoint.upsert_year(
                    year, year_started, counts, missing_summary, duration,
                )
                last_completed_year_for_halt = year
                current_year_for_halt = None

                logging.info(
                    f"[{year}] year complete: "
                    f"rows={sum(counts.values()):,} "
                    f"duration={duration:.1f}s "
                    f"cumulative={(time.monotonic()-overall_start)/60:.1f}m"
                )

            total_runtime = time.monotonic() - overall_start
            logging.info("=" * 64)
            logging.info(
                f"ALL YEARS COMPLETE "
                f"({args.from_year}-{args.to_year}, {total_runtime/60:.1f}m)"
            )
            logging.info("=" * 64)
            write_summary(checkpoint, total_runtime,
                          run_total_skipped_plays=run_total_skipped_plays,
                          run_years_with_skips=run_years_with_skips)

    except HaltSignal as e:
        write_halt_reason(
            reason=str(e), year=current_year_for_halt, stage=None, csv_path=None,
            error_class="HaltSignal", message=str(e),
            last_completed_year=last_completed_year_for_halt,
            partial_state="rolled back" if not args.dry_run else "n/a",
        )
        sys.exit(2)
    except KeyboardInterrupt:
        write_halt_reason(
            reason="keyboard-interrupt",
            year=current_year_for_halt, stage=None, csv_path=None,
            error_class="KeyboardInterrupt",
            message="user pressed Ctrl-C",
            last_completed_year=last_completed_year_for_halt,
            partial_state="rolled back" if not args.dry_run else "n/a",
        )
        sys.exit(2)
    except Exception as e:
        logging.exception("Halt due to unhandled exception")
        write_halt_reason(
            reason="exception",
            year=current_year_for_halt, stage=None, csv_path=None,
            error_class=type(e).__name__, message=str(e),
            last_completed_year=last_completed_year_for_halt,
            partial_state="rolled back" if not args.dry_run else "n/a",
        )
        sys.exit(1)
    finally:
        heartbeat.stop()


if __name__ == "__main__":
    main()
