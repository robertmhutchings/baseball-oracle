"""Baseball Oracle — automated checks for the v1 eval framework.

Each check is a function `check_*(spec, response_text, trace) -> dict`
returning {"name", "status", "detail"} where status is "pass" | "fail" | "skip".

`evaluate(spec, response_text, trace)` runs the full set and aggregates.

v1 scope:
  - Structural: response is non-empty
  - Substring: must_contain, must_not_contain
  - Verifiable answer: expected_answer appears (case-insensitive)
  - Unverifiable behavior: response contains a decline-signal phrase
  - Trace: at least one DB-touching tool call (skipped for unverifiable)
  - Trace: no run_sql errors

Process checks (e.g. "did the agent apply stattype='value' on aggregations?")
are deferred to a later iteration per architecture doc §2.12.
"""

import re
from typing import Any

from agent.trace import Trace


# Phrases the agent might use to honestly decline an unverifiable question
# (e.g. "Retrosheet doesn't include WAR"). Extended with natural variants
# so prose-style phrasings like "WAR isn't part of the data" or "trade
# history is beyond what I can compute" are recognized.
DECLINE_PHRASES = [
    "doesn't include",
    "does not include",
    "isn't available",
    "is not available",
    "isn't in",
    "is not in",
    "not in the dataset",
    "outside the scope",
    "retrosheet doesn't",
    "can't compute",
    "can't directly compare",
    "i don't have",
    "not part of",
    "isn't part of",
    "doesn't track",
    "does not track",
    "outside what",
    "beyond what",
]

DB_TOOL_NAMES = {"run_sql", "lookup_player", "lookup_team"}

THRESHOLD_KEYWORDS = [
    "minimum",
    "min.",
    "at least",
    "cutoff",
    "for players with",
    "qualifying",
]
THRESHOLD_NUMERIC_UNIT = re.compile(
    r"\b\d+\+?\s*(PA|AB|IP|innings?|games?)\b",
    re.IGNORECASE,
)

# Unicode dash variants normalized to ASCII hyphen before substring matching.
# Discovered when eval/results/2026-05-03_105219/ Q5 returned a false-positive
# fail: agent wrote "**114–48**" with U+2013 en-dash and the hyphen-only
# expected_answer "114-48" failed to match. Score-notation, year-range, and
# date-range strings frequently use en-dash/em-dash/minus interchangeably.
# Scope is intentionally narrow — dashes only — to avoid silently equating
# other Unicode variants (fancy quotes, ellipsis, NBSP) that may carry
# semantic weight in some contexts. (PHASE3B_NOTES item 19.)
_DASH_NORMALIZE = str.maketrans({
    "–": "-",  # en-dash
    "—": "-",  # em-dash
    "−": "-",  # minus sign
})


def _normalize_dashes(s: str) -> str:
    return s.translate(_DASH_NORMALIZE)


def _result(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def check_response_nonempty(spec: dict, response_text: str, trace: Trace) -> dict:
    if response_text and response_text.strip():
        return _result("response_nonempty", "pass", f"response is {len(response_text)} chars")
    return _result("response_nonempty", "fail", "response is empty or whitespace-only")


def check_must_contain(spec: dict, response_text: str, trace: Trace) -> dict:
    required = spec.get("must_contain") or []
    if not required:
        return _result("must_contain", "skip", "no must_contain specified")
    text_lower = _normalize_dashes(response_text.lower())
    missing = [s for s in required if _normalize_dashes(s.lower()) not in text_lower]
    if not missing:
        return _result("must_contain", "pass", f"all {len(required)} substrings present")
    return _result(
        "must_contain", "fail",
        f"missing substring(s): {missing}",
    )


def check_must_not_contain(spec: dict, response_text: str, trace: Trace) -> dict:
    forbidden = spec.get("must_not_contain") or []
    if not forbidden:
        return _result("must_not_contain", "skip", "no must_not_contain specified")
    text_lower = response_text.lower()
    hits = [s for s in forbidden if s.lower() in text_lower]
    if not hits:
        return _result("must_not_contain", "pass", f"none of {len(forbidden)} red-flag substrings present")
    return _result(
        "must_not_contain", "fail",
        f"red-flag substring(s) found: {hits}",
    )


def check_expected_answer(spec: dict, response_text: str, trace: Trace) -> dict:
    expected = spec.get("expected_answer")
    if not expected:
        return _result("expected_answer", "skip", "no expected_answer specified")
    if _normalize_dashes(expected.lower()) in _normalize_dashes(response_text.lower()):
        return _result("expected_answer", "pass", f"expected answer {expected!r} present")
    return _result(
        "expected_answer", "fail",
        f"expected answer {expected!r} not found in response",
    )


def check_decline_signal(spec: dict, response_text: str, trace: Trace) -> dict:
    if spec.get("category") != "unverifiable":
        return _result("decline_signal", "skip", "only applicable to unverifiable questions")
    text_lower = response_text.lower()
    matches = [p for p in DECLINE_PHRASES if p in text_lower]
    if matches:
        return _result(
            "decline_signal", "pass",
            f"decline-signal phrase(s) present: {matches}",
        )
    snippet = response_text[:200].replace("\n", " ")
    return _result(
        "decline_signal", "fail",
        f"no decline-signal phrase found. First 200 chars of response: {snippet}...",
    )


def check_trace_has_db_call(spec: dict, response_text: str, trace: Trace) -> dict:
    # Unverifiable questions can be answered with no DB hits (honest decline).
    if spec.get("category") == "unverifiable":
        return _result("trace_has_db_call", "skip", "DB calls optional for unverifiable")
    db_calls = [c for c in trace.calls if c.tool_name in DB_TOOL_NAMES]
    if db_calls:
        return _result(
            "trace_has_db_call", "pass",
            f"{len(db_calls)} DB-touching tool call(s) recorded",
        )
    return _result(
        "trace_has_db_call", "fail",
        "no DB-touching tool calls in trace; agent answered without consulting data",
    )


def check_trace_no_errors(spec: dict, response_text: str, trace: Trace) -> dict:
    errors = []
    for c in trace.calls:
        if c.tool_name == "run_sql" and isinstance(c.tool_output, dict):
            if not c.tool_output.get("ok", True):
                errors.append({
                    "type": c.tool_output.get("error_type"),
                    "message": c.tool_output.get("error_message"),
                })
    if not errors:
        return _result("trace_no_errors", "pass", "no run_sql errors recorded")
    return _result(
        "trace_no_errors", "fail",
        f"{len(errors)} run_sql error(s): {errors}",
    )


def check_sql_scalar_matches_answer(spec: dict, response_text: str, trace: Trace) -> dict:
    """Catch internal contradiction: agent ran SQL returning scalar X but
    cites a different number as the headline answer (PHASE3B_NOTES item 11).

    v1 scope: inspects the last run_sql call returning a single-row, single-
    column, integer-valued scalar. Compares against the first markdown-bolded
    chunk (**...**) containing a digit. Skips conservatively (multi-row/col
    results, non-integer scalars, responses with no bolded number) rather
    than risking false positives.
    """
    # Look at the LAST run_sql call only. If the agent's final query is a
    # multi-row decomposition (e.g. Ruth HR by gametype), don't fall back to
    # an earlier intermediate scalar — that produces false positives when
    # the headline number comes from the decomposition rather than from the
    # earlier unfiltered total.
    last_sql = next(
        (c for c in reversed(trace.calls) if c.tool_name == "run_sql"),
        None,
    )
    if last_sql is None:
        return _result(
            "sql_scalar_matches_answer", "skip",
            "no run_sql calls in trace",
        )

    out = last_sql.tool_output
    if not isinstance(out, dict) or not out.get("ok"):
        return _result(
            "sql_scalar_matches_answer", "skip",
            "last run_sql call did not succeed",
        )
    cols = out.get("columns") or []
    rows = out.get("rows") or []
    if out.get("row_count") != 1 or len(cols) != 1 or len(rows) != 1:
        return _result(
            "sql_scalar_matches_answer", "skip",
            f"last run_sql returned {out.get('row_count')} row(s) x {len(cols)} col(s); "
            "not a single-scalar shape",
        )
    row = rows[0]
    if not isinstance(row, dict):
        return _result(
            "sql_scalar_matches_answer", "skip",
            "last run_sql row not in expected dict shape",
        )
    val = row.get(cols[0])
    if val is None or isinstance(val, bool):
        return _result(
            "sql_scalar_matches_answer", "skip",
            f"last run_sql scalar value is {val!r}; not a numeric integer",
        )
    try:
        f = float(val)
    except (TypeError, ValueError):
        return _result(
            "sql_scalar_matches_answer", "skip",
            f"last run_sql scalar value {val!r} is not numeric",
        )
    if f != int(f):
        return _result(
            "sql_scalar_matches_answer", "skip",
            f"last run_sql scalar value {val} is non-integer (e.g. batting avg); skipping",
        )
    scalar = int(f)

    bolded_with_digits = re.findall(r"\*\*([^*]*?\d[^*]*?)\*\*", response_text)
    if not bolded_with_digits:
        return _result(
            "sql_scalar_matches_answer", "skip",
            f"SQL scalar={scalar} but response has no bolded number to anchor headline check",
        )
    headline_chunk = bolded_with_digits[0]

    scalar_str = str(scalar)
    pattern = rf"(?<!\d){re.escape(scalar_str)}(?!\d)"
    headline_normalized = headline_chunk.replace(",", "")
    response_normalized = response_text.replace(",", "")

    if re.search(pattern, headline_normalized):
        return _result(
            "sql_scalar_matches_answer", "pass",
            f"headline bolded chunk '**{headline_chunk}**' contains SQL scalar {scalar}",
        )

    elsewhere = bool(re.search(pattern, response_normalized))
    elsewhere_phrase = (
        "SQL value also appears elsewhere in response"
        if elsewhere
        else "SQL value also absent from full response"
    )
    return _result(
        "sql_scalar_matches_answer", "fail",
        f"{spec.get('id', '?')}: SQL scalar {scalar} not found in headline chunk "
        f"'**{headline_chunk}**'. {elsewhere_phrase}.",
    )


def check_threshold_surfaced(spec: dict, response_text: str, trace: Trace) -> dict:
    """For process_check questions where dynamism principle 1 (CLAUDE.md §8 —
    surface the threshold) applies, verify the response surfaces a threshold/
    cutoff in prose rather than burying it implicitly in the data
    (PHASE3B_NOTES item 13).

    Recognition heuristic (case-insensitive), PASS if any of:
      - threshold keyword: minimum, min., at least, cutoff, for players with, qualifying
      - numeric-with-unit: \\d+\\+?\\s*(PA|AB|IP|innings?|games?)

    SKIPs unless expected_behavior == "surface_threshold_and_list_leaders".
    """
    if spec.get("expected_behavior") != "surface_threshold_and_list_leaders":
        return _result(
            "threshold_surfaced", "skip",
            "only applicable to questions with "
            "expected_behavior='surface_threshold_and_list_leaders'",
        )
    text_lower = response_text.lower()
    keyword_hits = [k for k in THRESHOLD_KEYWORDS if k in text_lower]
    if keyword_hits:
        return _result(
            "threshold_surfaced", "pass",
            f"threshold keyword(s) present: {keyword_hits}",
        )
    numeric_match = THRESHOLD_NUMERIC_UNIT.search(response_text)
    if numeric_match:
        return _result(
            "threshold_surfaced", "pass",
            f"numeric-with-unit threshold present: {numeric_match.group(0)!r}",
        )
    snippet = response_text[:200].replace("\n", " ")
    return _result(
        "threshold_surfaced", "fail",
        f"no threshold/cutoff indicator found. First 200 chars: {snippet}...",
    )


CHECKS = [
    check_response_nonempty,
    check_must_contain,
    check_must_not_contain,
    check_expected_answer,
    check_decline_signal,
    check_trace_has_db_call,
    check_trace_no_errors,
    check_sql_scalar_matches_answer,
    check_threshold_surfaced,
]


def evaluate(spec: dict, response_text: str, trace: Trace) -> dict[str, Any]:
    """Run all checks against one (spec, response, trace) triple.

    Returns:
        {
          "id": ...,
          "category": ...,
          "checks": [list of check result dicts],
          "automated_status": "pass" | "fail",
          "manual_review_required": bool,
          "overall": "pass" | "fail" | "review_needed",
        }
    """
    results = [check(spec, response_text, trace) for check in CHECKS]

    any_fail = any(r["status"] == "fail" for r in results)
    automated_status = "fail" if any_fail else "pass"

    manual = bool(spec.get("manual_review_required"))
    if any_fail:
        overall = "fail"
    elif manual:
        overall = "review_needed"
    else:
        overall = "pass"

    return {
        "id": spec["id"],
        "category": spec.get("category"),
        "checks": results,
        "automated_status": automated_status,
        "manual_review_required": manual,
        "overall": overall,
    }
