"""Read-only database connection helper for the Baseball Oracle agent.

Used by the agent's run_sql tool. Connects with the baseball_oracle_agent
role, which has SELECT-only access to the retro schema (no INSERT/UPDATE/
DELETE/DDL).

Run directly to self-test the connection:
    C:\\BaseballOracle\\.venv\\Scripts\\python.exe agent\\db.py
"""

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def connect():
    """Open a read-only psycopg connection as baseball_oracle_agent."""
    return psycopg.connect(
        host=os.environ["PG_HOST"],
        port=os.environ["PG_PORT"],
        dbname=os.environ["PG_DATABASE"],
        user=os.environ["BASEBALL_ORACLE_DB_USER"],
        password=os.environ["BASEBALL_ORACLE_DB_PASSWORD"],
    )


def _self_test():
    results = []

    # Check 1: connect + simple SELECT
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM retro.players")
            (n,) = cur.fetchone()
        results.append(("SELECT retro.players count", "PASS", f"{n:,} rows"))
    except Exception as e:
        results.append(("SELECT retro.players count", "FAIL", repr(e)))

    # Check 2: confirm current_user is the agent role
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT current_user")
            (who,) = cur.fetchone()
        expected = "baseball_oracle_agent"
        status = "PASS" if who == expected else "FAIL"
        results.append(("current_user check", status, f"got {who!r}, expected {expected!r}"))
    except Exception as e:
        results.append(("current_user check", "FAIL", repr(e)))

    # Check 3: write attempt MUST fail with permission denied.
    # 'ZZZZZZZZ' is an obvious sentinel — alphabetically beyond any plausible
    # 8-char RetroID, so a UNIQUE violation can't masquerade as a privilege error.
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO retro.players (id) VALUES ('ZZZZZZZZ')")
        results.append(("INSERT blocked", "FAIL", "insert succeeded — role has too much privilege"))
    except psycopg.errors.InsufficientPrivilege as e:
        results.append(("INSERT blocked", "PASS", f"correctly rejected: {e.diag.message_primary}"))
    except Exception as e:
        results.append(("INSERT blocked", "FAIL", f"unexpected error: {e!r}"))

    # Print summary
    print(f"{'Check':<32} {'Status':<6} Detail")
    print("-" * 80)
    for name, status, detail in results:
        print(f"{name:<32} {status:<6} {detail}")
    print()
    overall = "PASS" if all(r[1] == "PASS" for r in results) else "FAIL"
    print(f"OVERALL: {overall}")
    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    _self_test()
