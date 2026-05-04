"""Dump every response across all historical eval runs for hallucination triage.

Output: scratch/all_responses.txt — one block per (run, question) for human read.
"""
import json
from pathlib import Path

ROOT = Path(r"C:\BaseballOracle\eval\results")
OUT = Path(r"C:\BaseballOracle\scratch\all_responses.txt")

lines: list[str] = []
for run_dir in sorted(ROOT.iterdir()):
    raw = run_dir / "raw.json"
    if not raw.exists():
        continue
    data = json.loads(raw.read_text(encoding="utf-8"))
    for q in data["questions"]:
        lines.append("=" * 80)
        lines.append(f"RUN: {run_dir.name}    Q: {q['id']}")
        lines.append("=" * 80)
        lines.append(q.get("response_text") or "(empty)")
        lines.append("")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {OUT} ({len(lines)} lines)")
