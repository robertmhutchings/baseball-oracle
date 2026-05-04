"""Baseball Oracle — eval runner.

Loads the benchmark question specs, runs each through the agent, applies
automated checks, and writes a per-run report under eval/results/<timestamp>/.

Usage:
    C:\\BaseballOracle\\.venv\\Scripts\\python.exe -m eval.runner

Each run produces:
  - eval/results/<timestamp>/report.md   — human-readable
  - eval/results/<timestamp>/raw.json    — full machine-readable

v1 limitations:
  - If the agent calls `ask_user` during a benchmark, the runner blocks on
    stdin (since `agent.main.answer_question` reads input() in that path).
    The current benchmark set is concrete enough that ask_user shouldn't
    fire; if a future question triggers it we'll need a programmatic
    ask_user handler injected into answer_question.
  - Process checks (e.g. "did the agent apply stattype='value'?") are not
    inspected — see checks.py.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic

from agent.config import MODEL, get_anthropic_api_key
from agent.main import answer_question
from agent.trace import Trace
from eval.benchmarks import BENCHMARKS
from eval.checks import evaluate


RESULTS_ROOT = Path(__file__).parent / "results"


def _trace_to_jsonable(trace: Trace) -> list[dict]:
    """Convert Trace's dataclass calls into plain dicts for JSON output."""
    return [
        {
            "tool_name": c.tool_name,
            "tool_input": c.tool_input,
            "tool_output": c.tool_output,
        }
        for c in trace.calls
    ]


def _trace_summary(trace: Trace) -> str:
    """One-line summary string for the report table."""
    if not trace.calls:
        return "0 tool calls"
    by_tool: dict[str, int] = {}
    for c in trace.calls:
        by_tool[c.tool_name] = by_tool.get(c.tool_name, 0) + 1
    parts = [f"{n} {name}" for name, n in by_tool.items()]
    return ", ".join(parts)


def run_one(client: anthropic.Anthropic, spec: dict) -> dict:
    """Run one benchmark question. Returns a result dict."""
    print(f"  -> {spec['id']}: {spec['question']}")
    started = time.monotonic()
    error = None
    response_text = ""
    trace = Trace()
    try:
        response_text, trace = answer_question(client, spec["question"])
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        print(f"     ERROR: {error}")
    duration = time.monotonic() - started

    if error:
        # Synthesize a fail evaluation when the agent crashed.
        evaluation = {
            "id": spec["id"],
            "category": spec.get("category"),
            "checks": [{
                "name": "agent_runtime",
                "status": "fail",
                "detail": f"answer_question raised: {error}",
            }],
            "automated_status": "fail",
            "manual_review_required": bool(spec.get("manual_review_required")),
            "overall": "fail",
        }
    else:
        evaluation = evaluate(spec, response_text, trace)

    print(f"     [{duration:.1f}s] overall={evaluation['overall']}")

    return {
        "id": spec["id"],
        "spec": spec,
        "response_text": response_text,
        "trace": _trace_to_jsonable(trace),
        "trace_summary": _trace_summary(trace),
        "duration_seconds": round(duration, 2),
        "evaluation": evaluation,
        "error": error,
    }


def build_report_md(run_metadata: dict, summary: dict, results: list[dict]) -> str:
    lines: list[str] = []
    lines.append(f"# Eval run — {run_metadata['timestamp']}")
    lines.append("")
    lines.append(
        f"{run_metadata['n_questions']} questions, "
        f"{summary['pass']} pass, {summary['fail']} fail, "
        f"{summary['review_needed']} review_needed "
        f"({run_metadata['duration_seconds']}s total, model {run_metadata['model']})"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| ID | Category | Overall | Automated | Manual review |")
    lines.append("|----|----------|---------|-----------|---------------|")
    for r in results:
        ev = r["evaluation"]
        lines.append(
            f"| {r['id']} | {ev['category']} | {ev['overall']} | "
            f"{ev['automated_status']} | {ev['manual_review_required']} |"
        )
    lines.append("")
    lines.append("## Per-question detail")
    lines.append("")
    for r in results:
        spec = r["spec"]
        ev = r["evaluation"]
        lines.append(f"### {r['id']} — {ev['overall']}")
        lines.append("")
        lines.append(f"**Question:** {spec['question']}")
        lines.append(f"**Category:** {ev['category']}")
        if spec.get("expected_answer"):
            lines.append(f"**Expected answer:** `{spec['expected_answer']}`")
        if spec.get("expected_behavior"):
            lines.append(f"**Expected behavior:** `{spec['expected_behavior']}`")
        lines.append(f"**Manual review required:** {ev['manual_review_required']}")
        lines.append(f"**Duration:** {r['duration_seconds']}s")
        lines.append(f"**Tool calls:** {r['trace_summary']}")
        lines.append("")
        lines.append("**Response:**")
        lines.append("")
        lines.append("```")
        lines.append(r["response_text"] or "(empty)")
        lines.append("```")
        lines.append("")
        lines.append("**Checks:**")
        lines.append("")
        for c in ev["checks"]:
            lines.append(f"- `{c['name']}` — **{c['status']}** — {c['detail']}")
        if r.get("error"):
            lines.append("")
            lines.append(f"**Error:** {r['error']}")
        if spec.get("notes"):
            lines.append("")
            lines.append(f"**Notes:** {spec['notes']}")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    try:
        api_key = get_anthropic_api_key()
    except RuntimeError as e:
        print(f"Startup error: {e}", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_dir = RESULTS_ROOT / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Eval run starting — {len(BENCHMARKS)} questions, model={MODEL}")
    print(f"Output: {out_dir}")
    print()

    started = time.monotonic()
    results = [run_one(client, spec) for spec in BENCHMARKS]
    duration = time.monotonic() - started

    summary = {"pass": 0, "fail": 0, "review_needed": 0}
    for r in results:
        summary[r["evaluation"]["overall"]] += 1

    run_metadata = {
        "timestamp": timestamp,
        "model": MODEL,
        "n_questions": len(BENCHMARKS),
        "duration_seconds": round(duration, 2),
    }

    raw = {
        "run_metadata": run_metadata,
        "summary": summary,
        "questions": results,
    }

    raw_path = out_dir / "raw.json"
    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, default=str)

    report_md = build_report_md(run_metadata, summary, results)
    report_path = out_dir / "report.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write(report_md)

    print()
    print(
        f"Done. {summary['pass']} pass / {summary['fail']} fail / "
        f"{summary['review_needed']} review_needed in {duration:.1f}s"
    )
    print(f"Report: {report_path}")
    print(f"Raw:    {raw_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
