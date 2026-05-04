"""Agent tools.

Phase 3A: a single tool, `run_sql`, that exposes the read-only Postgres
connection from agent/db.py with the §2.3 guardrails (statement_timeout,
result-size cap). Other tools (lookup_player, lookup_team, ask_user)
are deferred to Phase 3A Step 4.
"""

import datetime
import decimal
from typing import Any

import psycopg

from agent.config import SQL_MAX_ROWS, SQL_STATEMENT_TIMEOUT_MS
from agent.db import connect


# Anthropic tool spec — what the model sees.
RUN_SQL_TOOL = {
    "name": "run_sql",
    "description": (
        "Execute a read-only SQL query against the retro schema (PostgreSQL 16, "
        "Retrosheet 1907-2023 corpus). The query runs as the baseball_oracle_agent "
        "role with SELECT-only privileges; INSERT/UPDATE/DELETE/DDL will return a "
        "permission error. Queries that take longer than 30 seconds time out. "
        f"Result sets larger than {SQL_MAX_ROWS} rows are truncated; if that happens "
        "you'll be told and should reformulate (narrower filter, aggregation, etc.). "
        "Returns rows as a list of dicts (column name -> value)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A single SQL SELECT statement against the retro schema.",
            }
        },
        "required": ["query"],
    },
}


def _to_json_safe(value: Any) -> Any:
    """Coerce psycopg row values into JSON-serializable Python types.

    Decimal -> float (precision is fine for baseball stats — height/weight are
    half-precision, counting stats are integers).
    date / datetime -> ISO 8601 string. Everything else passes through.
    """
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def run_sql(query: str) -> dict[str, Any]:
    """Execute `query` and return a structured result the agent can read.

    Result shape:
        {
            "ok": True,
            "row_count": <int>,
            "truncated": <bool>,
            "columns": [<col-name>, ...],
            "rows": [{<col>: <val>, ...}, ...],
        }
      or on failure:
        {
            "ok": False,
            "error_type": "<class name>",
            "error_message": "<str>",
        }
    """
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {SQL_STATEMENT_TIMEOUT_MS}")
                cur.execute(query)
                if cur.description is None:
                    return {"ok": True, "row_count": 0, "truncated": False,
                            "columns": [], "rows": []}
                columns = [d[0] for d in cur.description]
                rows = cur.fetchmany(SQL_MAX_ROWS + 1)
                truncated = len(rows) > SQL_MAX_ROWS
                if truncated:
                    rows = rows[:SQL_MAX_ROWS]
                row_dicts = [
                    {col: _to_json_safe(val) for col, val in zip(columns, r)}
                    for r in rows
                ]
        return {
            "ok": True,
            "row_count": len(row_dicts),
            "truncated": truncated,
            "columns": columns,
            "rows": row_dicts,
        }
    except psycopg.errors.QueryCanceled as e:
        return {
            "ok": False,
            "error_type": "QueryCanceled",
            "error_message": (
                f"Query exceeded the {SQL_STATEMENT_TIMEOUT_MS // 1000}s timeout. "
                f"Reformulate with a narrower filter or aggregation. ({e})"
            ),
        }
    except psycopg.Error as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "error_message": str(e),
        }


# ---------------------------------------------------------------------------
# lookup_player
# ---------------------------------------------------------------------------

LOOKUP_PLAYER_LIMIT = 50

LOOKUP_PLAYER_TOOL = {
    "name": "lookup_player",
    "description": (
        "Find players by name using case-insensitive substring match against "
        "usename (display first name), lastname, OR altname (nickname). Returns "
        "up to 50 matches with biographical metadata: RetroID (id), usename, "
        "lastname, fullname, altname, debut/last year as a player, bats, throws, "
        "HOF status. Use this BEFORE writing SQL that filters on a player's "
        "name — the wrong RetroID is a high-cost failure (silent wrong answer). "
        "Pass a single token where possible: 'Griffey', 'Aaron', 'Ichiro', "
        "'Suzuki', 'A-Rod'. For multi-word inputs ('Ken Griffey', 'Barry Bonds', "
        "'Ichiro Suzuki'), pass the most distinctive single token — usually the "
        "surname, but use the given name for mononyms or unusually distinctive "
        "given names ('Ichiro' over 'Suzuki', 'Sadaharu' over 'Oh'). The match "
        "is substring, so partial inputs work but may return many rows; apply "
        "the tiered disambiguation logic from your instructions when "
        "match_count > 1."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Single name token: surname, given name, or nickname. "
                    "Case-insensitive substring match."
                ),
            }
        },
        "required": ["name"],
    },
}


_LOOKUP_PLAYER_SQL = """
SELECT id, usename, lastname, fullname, altname,
       CASE WHEN debut_p ~ '^[0-9]{4}' THEN LEFT(debut_p, 4)::int END AS debut_year,
       CASE WHEN last_p  ~ '^[0-9]{4}' THEN LEFT(last_p,  4)::int END AS last_year,
       bats, throws, HOF
FROM retro.players
WHERE usename ILIKE %s OR lastname ILIKE %s OR altname ILIKE %s
ORDER BY lastname, usename
LIMIT %s
"""


def lookup_player(name: str) -> dict[str, Any]:
    """Find players by surname/given-name/nickname substring (case-insensitive)."""
    pattern = f"%{name}%"
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {SQL_STATEMENT_TIMEOUT_MS}")
                cur.execute(
                    _LOOKUP_PLAYER_SQL,
                    (pattern, pattern, pattern, LOOKUP_PLAYER_LIMIT + 1),
                )
                columns = [d[0] for d in cur.description]
                rows = cur.fetchall()
                truncated = len(rows) > LOOKUP_PLAYER_LIMIT
                if truncated:
                    rows = rows[:LOOKUP_PLAYER_LIMIT]
                matches = [
                    {col: _to_json_safe(val) for col, val in zip(columns, r)}
                    for r in rows
                ]
        return {
            "ok": True,
            "match_count": len(matches),
            "truncated": truncated,
            "matches": matches,
        }
    except psycopg.Error as e:
        return {"ok": False, "error_type": type(e).__name__, "error_message": str(e)}


# ---------------------------------------------------------------------------
# lookup_team
# ---------------------------------------------------------------------------

LOOKUP_TEAM_LIMIT = 50

LOOKUP_TEAM_TOOL = {
    "name": "lookup_team",
    "description": (
        "Find teams by code, city, nickname, or 'city + nickname' combined "
        "string. Case-insensitive substring match across all four fields. "
        "Returns up to 50 matches with metadata: team code (3-char), league, "
        "city, nickname, first_year, last_year. Use this when a user mentions "
        "a team by name to identify which 3-char code (or codes) to use in "
        "subsequent SQL — wrong team codes silently return wrong stats. "
        "Common names like 'Washington' or 'New York' map to multiple "
        "franchises across eras; first_year/last_year let you disambiguate "
        "by era. Pass either: a 3-char team code ('NYA'), a city "
        "('Washington'), a nickname ('Senators'), or both combined "
        "('Washington Senators'). Apply the tiered disambiguation logic from "
        "your instructions when match_count > 1."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Team code, city, nickname, or 'city nickname' combined. "
                    "Case-insensitive substring match across all four fields."
                ),
            }
        },
        "required": ["query"],
    },
}


_LOOKUP_TEAM_SQL = """
SELECT team, league, city, nickname, first_year, last_year
FROM retro.teams
WHERE team     ILIKE %s
   OR city     ILIKE %s
   OR nickname ILIKE %s
   OR (city || ' ' || nickname) ILIKE %s
ORDER BY first_year, team
LIMIT %s
"""


def lookup_team(query: str) -> dict[str, Any]:
    """Find teams by code, city, nickname, or combined 'city nickname' string."""
    pattern = f"%{query}%"
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {SQL_STATEMENT_TIMEOUT_MS}")
                cur.execute(
                    _LOOKUP_TEAM_SQL,
                    (pattern, pattern, pattern, pattern, LOOKUP_TEAM_LIMIT + 1),
                )
                columns = [d[0] for d in cur.description]
                rows = cur.fetchall()
                truncated = len(rows) > LOOKUP_TEAM_LIMIT
                if truncated:
                    rows = rows[:LOOKUP_TEAM_LIMIT]
                matches = [
                    {col: _to_json_safe(val) for col, val in zip(columns, r)}
                    for r in rows
                ]
        return {
            "ok": True,
            "match_count": len(matches),
            "truncated": truncated,
            "matches": matches,
        }
    except psycopg.Error as e:
        return {"ok": False, "error_type": type(e).__name__, "error_message": str(e)}


# ---------------------------------------------------------------------------
# ask_user
# ---------------------------------------------------------------------------
# No Python implementation — this tool pauses the agent loop and routes to
# the user. main.py special-cases the "ask_user" tool_use name before
# TOOL_IMPLS dispatch; the user's REPL response becomes the tool_result.

ASK_USER_TOOL = {
    "name": "ask_user",
    "description": (
        "Pause and ask the user a question. The user's free-text response "
        "becomes the tool result you continue from. Use this sparingly — only "
        "when proceeding without user input would meaningfully risk a wrong "
        "or unhelpful answer.\n\n"
        "USE ask_user when:\n"
        "(a) Player or team disambiguation can't be resolved from context — "
        "e.g. lookup_player returned 6+ matches and you have no era/team hint "
        "to narrow with, or 2-5 matches for a narrative question where you "
        "need to know which person the user means.\n"
        "(b) The question is conceptually ambiguous in a way that materially "
        "changes the answer — e.g. 'best clutch hitter' (by what metric? "
        "AVG with RISP, late-and-close OPS, postseason record?).\n"
        "(c) A required input is missing — e.g. 'how did the home opener go' "
        "with no team or year specified.\n\n"
        "DO NOT use ask_user when:\n"
        "(a) One interpretation is obvious and others are minor variants — "
        "answer the obvious one, surface alternatives proactively in your "
        "response.\n"
        "(b) You can pick a reasonable default and name your assumption — "
        "e.g. 'I'm using 150+ AB as the cutoff; tell me if you want a "
        "different threshold.'\n"
        "(c) You'd just be re-running queries with different filters — run "
        "them and present multiple results in one response.\n\n"
        "Phrase your question concisely. One sentence is usually enough."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "The question to ask the user. Concise, focused on the "
                    "specific ambiguity you can't resolve."
                ),
            }
        },
        "required": ["question"],
    },
}


TOOL_IMPLS = {
    "run_sql": run_sql,
    "lookup_player": lookup_player,
    "lookup_team": lookup_team,
    # ask_user is intentionally absent — main.py special-cases it before
    # this dispatch table (it routes to user input, not a Python function).
}

TOOL_SPECS = [RUN_SQL_TOOL, LOOKUP_PLAYER_TOOL, LOOKUP_TEAM_TOOL, ASK_USER_TOOL]
