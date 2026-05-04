"""Spot-check Q4/Q6/Q8 responses in the fresh eval run."""
import json
from pathlib import Path

p = Path(r"C:\BaseballOracle\eval\results\2026-05-03_093717\raw.json")
data = json.loads(p.read_text(encoding="utf-8"))
for q in data["questions"]:
    if q["id"] in ("Q4_1998_cycles", "Q6_ruth_career_hrs", "Q8_bonds_2001_hrs"):
        print(f"========== {q['id']} ==========")
        print(q["response_text"])
        print()
