"""
Phase 2 discovery -- CSV header drift across eras.

For each of the 7 per-year CSV types, reads just the header row for each
sampled year and diffs against the 1998 baseline. Reveals which columns
Retrosheet added or dropped as its recording conventions evolved. Read-only.
"""

import csv
from pathlib import Path

DATA_ROOT = Path(r"C:\BaseballOracle\data")

# Eight sampled eras. 1998 is the baseline (Phase 1 load); other years
# span dead-ball, liveball, WW2, modern-expansion, 80s, Phase-1, 2000s,
# current.
SAMPLE_YEARS = [1905, 1925, 1945, 1965, 1985, 1998, 2005, 2022]
BASELINE_YEAR = 1998

CSV_TYPES = [
    "gameinfo", "allplayers", "batting", "pitching",
    "fielding", "teamstats", "plays",
]


def read_header(path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return None
    return [h.lower() for h in header]


def main():
    print("=" * 64)
    print("PHASE 2 DISCOVERY - HEADER DRIFT")
    print("=" * 64)
    print(f"Sampled years: {SAMPLE_YEARS}  (baseline = {BASELINE_YEAR})")
    print(f"CSV types: {CSV_TYPES}")
    print()

    for csv_type in CSV_TYPES:
        print(f"--- {csv_type}.csv ---")
        # Collect headers per year
        headers = {}  # year -> list of columns (lowercased), or None
        for year in SAMPLE_YEARS:
            path = DATA_ROOT / str(year) / f"{year}{csv_type}.csv"
            headers[year] = read_header(path)

        missing_years = [y for y, h in headers.items() if h is None]
        if missing_years:
            print(f"  Missing file for years: {missing_years}")

        present = {y: set(h) for y, h in headers.items() if h is not None}
        if not present:
            print("  No files found for this CSV type in any sampled year.")
            print()
            continue

        if BASELINE_YEAR not in present:
            print(f"  {BASELINE_YEAR} file missing - cannot diff against baseline.")
            print()
            continue

        baseline = present[BASELINE_YEAR]
        union = set()
        intersection = None
        for h in present.values():
            union |= h
            intersection = set(h) if intersection is None else (intersection & h)

        print(f"  Columns in ALL present sampled eras: {len(intersection)}")
        print(f"  Columns in ANY present sampled era:  {len(union)}")
        print(f"  {BASELINE_YEAR} baseline column count:           "
              f"{len(baseline)}")
        print()

        for year in sorted(present.keys()):
            if year == BASELINE_YEAR:
                continue
            h = present[year]
            extra = sorted(h - baseline)
            missing = sorted(baseline - h)
            print(f"  {year} vs {BASELINE_YEAR}:")
            if not extra and not missing:
                print("    identical columns")
            else:
                if missing:
                    print(f"    missing in {year} ({len(missing)}): {missing}")
                if extra:
                    print(f"    added in {year} ({len(extra)}): {extra}")
        print()


if __name__ == "__main__":
    main()
