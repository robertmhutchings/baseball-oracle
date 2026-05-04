"""Inspect trace structure across all benchmarks in two runs."""
import json
from pathlib import Path

PATHS = {
    "FAIL_BASELINE": r"C:\BaseballOracle\eval\results\2026-05-02_075131\raw.json",
    "PASS_CURRENT": r"C:\BaseballOracle\eval\results\2026-05-03_064708\raw.json",
}

for label, path in PATHS.items():
    print(f"\n========== {label} ==========")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for q in data["questions"]:
        print(f"\n--- {q['id']} ---")
        print(f"Response (first 500 chars): {q['response_text'][:500]!r}")
        for i, c in enumerate(q["trace"]):
            if c["tool_name"] != "run_sql":
                continue
            out = c.get("tool_output")
            if isinstance(out, dict) and out.get("ok"):
                rc = out.get("row_count", 0)
                cols = out.get("columns", [])
                rows = out.get("rows", [])
                summary = f"  [{i}] {rc} row(s), cols={cols}"
                if rc <= 3:
                    summary += f", rows={rows}"
                else:
                    summary += f", first_row={rows[0] if rows else None}"
                print(summary)
