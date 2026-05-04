"""Replay historical eval runs through current checks.

Reads raw.json from each eval/results/<timestamp>/ directory and rebuilds the
(spec, response_text, trace) triple for each question. Then either:
  - runs one or more named checks in isolation (--check), or
  - runs the full evaluate() pipeline (default).

Reports unexpected verdicts: questions that FAIL when not in --expected-fail,
or questions in --expected-fail that don't FAIL.

Useful for:
  - validating a newly-added check against historical data (item 11 pattern)
  - validating must_not_contain additions catch their target hallucinations
    without creating new false positives (item 12 pattern)
  - regression-testing existing checks after refactors

Usage:
  python scratch/replay_historical_evals.py
  python scratch/replay_historical_evals.py --check check_sql_scalar_matches_answer \\
      --expected-fail 2026-05-02_075131:Q6_ruth_career_hrs
  python scratch/replay_historical_evals.py \\
      --expected-fail 2026-05-02_075131:Q4_1998_cycles \\
      --expected-fail 2026-05-02_083226:Q4_1998_cycles
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.trace import Trace, ToolCall
from eval import checks as checks_module
from eval.benchmarks import BENCHMARKS
from eval.checks import CHECKS, evaluate

CURRENT_SPECS = {b["id"]: b for b in BENCHMARKS}

RESULTS_ROOT = Path(__file__).parent.parent / "eval" / "results"


def reconstruct_trace(trace_json: list[dict]) -> Trace:
    t = Trace()
    for c in trace_json:
        t.calls.append(ToolCall(
            tool_name=c["tool_name"],
            tool_input=c.get("tool_input") or {},
            tool_output=c.get("tool_output"),
        ))
    return t


def parse_expected_fail(s: str) -> tuple[str, str]:
    if ":" not in s:
        raise argparse.ArgumentTypeError(
            f"--expected-fail must be RUN:QID, got {s!r}"
        )
    run, qid = s.split(":", 1)
    return run.strip(), qid.strip()


def resolve_checks(names: list[str] | None):
    if not names:
        return None
    by_name = {fn.__name__: fn for fn in CHECKS}
    resolved = []
    for n in names:
        if n not in by_name:
            available = ", ".join(sorted(by_name))
            raise SystemExit(f"Unknown check {n!r}. Available: {available}")
        resolved.append(by_name[n])
    return resolved


def list_runs(run_filter: list[str] | None) -> list[Path]:
    all_runs = sorted(d for d in RESULTS_ROOT.iterdir() if (d / "raw.json").exists())
    if run_filter:
        return [d for d in all_runs if d.name in run_filter]
    return all_runs


def run_question(
    spec: dict,
    response_text: str,
    trace: Trace,
    selected_checks,
) -> list[tuple[str, str, str]]:
    """Return list of (label, status, detail) tuples for one question."""
    if selected_checks is None:
        ev = evaluate(spec, response_text, trace)
        return [("evaluate", ev["overall"], _summarize_evaluate(ev))]
    out = []
    for fn in selected_checks:
        result = fn(spec, response_text, trace)
        out.append((fn.__name__, result["status"], result["detail"]))
    return out


def _summarize_evaluate(ev: dict) -> str:
    fails = [c for c in ev["checks"] if c["status"] == "fail"]
    if fails:
        names = ", ".join(c["name"] for c in fails)
        return f"failing checks: {names}"
    if ev["manual_review_required"]:
        return "all automated checks pass; manual review required"
    return "all checks pass"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="append",
        default=[],
        help="Name of a check function to run in isolation (repeatable). "
             "If omitted, runs full evaluate() and reports overall verdict.",
    )
    parser.add_argument(
        "--expected-fail",
        action="append",
        type=parse_expected_fail,
        default=[],
        help="RUN:QID pair expected to FAIL (repeatable).",
    )
    parser.add_argument(
        "--runs",
        action="append",
        default=[],
        help="Limit replay to these run timestamps (repeatable). "
             "Default: all runs.",
    )
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    selected_checks = resolve_checks(args.check)
    expected_fails = set(args.expected_fail)
    expected_unfired = set(expected_fails)

    runs = list_runs(args.runs)
    if not runs:
        print("No matching runs found.", file=sys.stderr)
        return 1

    mode = "evaluate" if selected_checks is None else f"checks={','.join(args.check)}"
    print(f"Mode: {mode}")
    print(f"Runs: {len(runs)}")
    print(f"Expected fails: {len(expected_fails)}")
    print()

    unexpected = 0
    for run_dir in runs:
        print(f"========== {run_dir.name} ==========")
        data = json.loads((run_dir / "raw.json").read_text(encoding="utf-8"))
        for q in data["questions"]:
            qid = q["id"]
            spec = CURRENT_SPECS.get(qid)
            if spec is None:
                print(f"   {qid:30s} -> SKIP (no current spec — question removed from benchmarks.py)")
                continue
            response_text = q.get("response_text") or ""
            trace = reconstruct_trace(q.get("trace") or [])
            verdicts = run_question(spec, response_text, trace, selected_checks)
            key = (run_dir.name, qid)
            for label, status, detail in verdicts:
                tag = "  "
                if status == "fail":
                    if key in expected_fails:
                        tag = "OK"
                        expected_unfired.discard(key)
                    else:
                        tag = "!!"
                        unexpected += 1
                if len(verdicts) == 1:
                    print(f"{tag} {qid:30s} -> {status:5s} | {detail}")
                else:
                    print(f"{tag} {qid:30s} [{label:35s}] -> {status:5s} | {detail}")

    print()
    if expected_unfired:
        for run, qid in sorted(expected_unfired):
            print(f"!! EXPECTED FAIL did not fire: {run}:{qid}")
        unexpected += len(expected_unfired)

    if unexpected == 0:
        print(f"VALIDATION OK: {len(expected_fails)} expected fail(s), 0 unexpected.")
        return 0
    print(f"VALIDATION FAILED: {unexpected} unexpected verdict(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
