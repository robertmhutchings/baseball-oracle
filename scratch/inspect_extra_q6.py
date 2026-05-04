"""Inspect Q6 in the two intermediate runs that flagged."""
import json
from pathlib import Path

for run in ("2026-05-02_081224", "2026-05-02_090331"):
    p = Path(rf"C:\BaseballOracle\eval\results\{run}\raw.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    for q in data["questions"]:
        if q["id"] != "Q6_ruth_career_hrs":
            continue
        print(f"========== {run} Q6 ==========")
        print("Response:")
        print(q["response_text"])
        print()
        print("Trace (run_sql only):")
        for i, c in enumerate(q["trace"]):
            if c["tool_name"] != "run_sql":
                continue
            print(f"[{i}] query: {(c.get('tool_input') or {}).get('query', '').strip()}")
            out = c.get("tool_output")
            if isinstance(out, dict) and out.get("ok"):
                print(f"     -> {out.get('row_count')} row(s), cols={out.get('columns')}, rows={out.get('rows')}")
        print()
