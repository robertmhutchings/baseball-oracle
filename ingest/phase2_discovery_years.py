"""
Phase 2 discovery -- year-folder inventory.

Reports: which year folders exist under data/, which are missing vs.
1901-2023 expected range, and which present years have incomplete CSV
sets. Read-only.
"""

import re
from pathlib import Path

DATA_ROOT = Path(r"C:\BaseballOracle\data")
EXPECTED_RANGE = range(1901, 2024)
EXPECTED_CSVS = [
    "gameinfo", "allplayers", "batting", "pitching",
    "fielding", "teamstats", "plays",
]


def main():
    year_pat = re.compile(r"^\d{4}$")
    present_years = []
    non_year_entries = []
    for entry in sorted(DATA_ROOT.iterdir()):
        if not entry.is_dir():
            if entry.name.lower().endswith(".csv"):
                continue  # cross-year reference files are expected
            non_year_entries.append(entry.name)
            continue
        if year_pat.match(entry.name):
            present_years.append(int(entry.name))
        else:
            non_year_entries.append(entry.name + "/")

    present_set = set(present_years)
    expected_set = set(EXPECTED_RANGE)
    missing = sorted(expected_set - present_set)
    extra = sorted(present_set - expected_set)

    print("=" * 64)
    print("PHASE 2 DISCOVERY - YEAR INVENTORY")
    print("=" * 64)
    print(f"Expected range: {min(EXPECTED_RANGE)}..{max(EXPECTED_RANGE)} "
          f"({len(EXPECTED_RANGE)} years)")
    print(f"Year folders present: {len(present_years)}")
    print(f"Missing from expected: {len(missing)}")
    print(f"Extra (outside expected range): {len(extra)}")
    if non_year_entries:
        print(f"Non-year directory entries: {non_year_entries}")
    print()

    if missing:
        print(f"Missing years: {missing}")
        print()
    if extra:
        print(f"Extra years: {extra}")
        print()

    # Per-year CSV completeness
    print("=" * 64)
    print("Per-year CSV completeness")
    print("=" * 64)
    incomplete_years = []
    for y in sorted(present_years):
        year_dir = DATA_ROOT / str(y)
        missing_csvs = []
        for csv_type in EXPECTED_CSVS:
            p = year_dir / f"{y}{csv_type}.csv"
            if not p.exists():
                missing_csvs.append(csv_type)
        if missing_csvs:
            incomplete_years.append((y, missing_csvs))

    if not incomplete_years:
        print(f"All {len(present_years)} present years have all 7 expected CSVs.")
    else:
        print(f"{len(incomplete_years)} year(s) have incomplete CSV sets:")
        for y, miss in incomplete_years:
            print(f"  {y}: missing {miss}")
    print()


if __name__ == "__main__":
    main()
