"""
Phase 2 discovery -- width scan across all 1901-2023 years.

For every VARCHAR(N<=10) and CHAR(1) column the ingest touches, computes
the maximum observed length across ALL years and reports columns where
the observed max exceeds the declared width. Per-year progress line.
Early-termination safeguard: aborts if >50 distinct columns ever overflow
(likely script bug, not data).

Aggregation grain: one row in the final report per (csv_type, column_name).
Cross-year reference files (teams.csv, ballparks.csv, biofile0.csv,
relatives.csv) are scanned once up front.

Read-only. Long-running (~20-40 min expected).
"""

import csv
import time
from pathlib import Path

DATA_ROOT = Path(r"C:\BaseballOracle\data")
EXPECTED_RANGE = range(1901, 2024)
ABORT_THRESHOLD = 50   # distinct overflow columns

# kind: 'v' = VARCHAR(declared); 'c' = CHAR(1)

# Cross-year targets: (label, path, checks)
CROSS_YEAR_TARGETS = [
    ("teams.csv", DATA_ROOT / "teams.csv", [
        ("TEAM", 3, "v"),
    ]),
    ("ballparks.csv", DATA_ROOT / "ballparks.csv", [
        ("PARKID", 5, "v"),
    ]),
    ("biofile0.csv", DATA_ROOT / "biofile0.csv", [
        ("id", 8, "v"),
        ("birthdate", 8, "v"), ("deathdate", 8, "v"),
        ("debut_p", 8, "v"), ("last_p", 8, "v"),
        ("debut_c", 8, "v"), ("last_c", 8, "v"),
        ("debut_m", 8, "v"), ("last_m", 8, "v"),
        ("debut_u", 8, "v"), ("last_u", 8, "v"),
        ("bats", 2, "v"), ("throws", 2, "v"),
        ("HOF", 8, "v"),
    ]),
    ("relatives.csv", DATA_ROOT / "relatives.csv", [
        ("id1", 8, "v"),
        ("id2", 8, "v"),
    ]),
]

# Per-year targets: (csv_type_label, checks)
PER_YEAR_SPECS = [
    ("gameinfo", [
        ("visteam", 3, "v"), ("hometeam", 3, "v"),
        ("site", 5, "v"),
        ("starttime", 10, "v"), ("daynight", 10, "v"),
        ("umphome", 10, "v"),
        ("ump1b", 10, "v"), ("ump2b", 10, "v"), ("ump3b", 10, "v"),
        ("umplf", 10, "v"), ("umprf", 10, "v"),
        ("wp", 8, "v"), ("lp", 8, "v"), ("save", 8, "v"),
        ("wteam", 3, "v"), ("lteam", 3, "v"),
        ("line", 4, "v"), ("batteries", 10, "v"),
        ("lineups", 4, "v"), ("box", 4, "v"), ("pbp", 4, "v"),
    ]),
    ("allplayers", [
        ("id", 8, "v"),
        ("bat", 2, "v"), ("throw", 2, "v"),
        ("team", 3, "v"), ("pos", 3, "v"),
    ]),
    ("batting", [
        ("id", 8, "v"), ("team", 3, "v"),
        ("stattype", 10, "v"),
        ("site", 5, "v"), ("opp", 3, "v"),
        ("box", 4, "v"), ("wl", 1, "c"),
    ]),
    ("pitching", [
        ("id", 8, "v"), ("team", 3, "v"),
        ("stattype", 10, "v"),
        ("site", 5, "v"), ("opp", 3, "v"),
        ("box", 4, "v"), ("wl", 1, "c"),
    ]),
    ("fielding", [
        ("id", 8, "v"), ("team", 3, "v"),
        ("stattype", 10, "v"),
        ("site", 5, "v"), ("opp", 3, "v"),
        ("box", 4, "v"), ("wl", 1, "c"),
    ]),
    ("teamstats", [
        ("team", 3, "v"), ("mgr", 8, "v"),
        ("stattype", 10, "v"),
        *((f"start_l{i}", 8, "v") for i in range(1, 10)),
        *((f"start_f{i}", 8, "v") for i in range(1, 11)),
        ("site", 5, "v"), ("opp", 3, "v"),
        ("box", 4, "v"), ("wl", 1, "c"),
    ]),
    ("plays", [
        ("ballpark", 5, "v"),
        ("batteam", 3, "v"), ("pitteam", 3, "v"),
        ("batter", 8, "v"), ("pitcher", 8, "v"),
        ("count", 2, "v"),
        ("br1_pre", 8, "v"), ("br2_pre", 8, "v"), ("br3_pre", 8, "v"),
        ("br1_post", 8, "v"), ("br2_post", 8, "v"), ("br3_post", 8, "v"),
        ("run_b", 8, "v"),
        ("run1", 8, "v"), ("run2", 8, "v"), ("run3", 8, "v"),
        ("prun1", 8, "v"), ("prun2", 8, "v"), ("prun3", 8, "v"),
        ("f2", 8, "v"), ("f3", 8, "v"), ("f4", 8, "v"), ("f5", 8, "v"),
        ("f6", 8, "v"), ("f7", 8, "v"), ("f8", 8, "v"), ("f9", 8, "v"),
        ("loc", 10, "v"),
        ("bathand", 1, "c"), ("pithand", 1, "c"),
        ("hittype", 4, "v"),
    ]),
]


def scan_file(csv_path, checks, tracker, type_label, source_tag):
    """Scan csv_path, accumulate per-column max lengths into tracker.

    tracker is keyed by (type_label, column_name). source_tag identifies
    where the max came from (e.g. 1998 for per-year, the filename for
    cross-year).
    """
    if not csv_path.exists():
        return 0, [], False

    rows = 0
    missing = []
    with open(csv_path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return 0, [], False
        lower = [h.lower() for h in header]
        col_plan = []
        for name, declared, kind in checks:
            try:
                idx = lower.index(name.lower())
            except ValueError:
                missing.append(name)
                continue
            col_plan.append((idx, name, declared, kind))

        for row in reader:
            rows += 1
            for idx, name, declared, kind in col_plan:
                v = row[idx] if idx < len(row) else ""
                L = len(v)
                key = (type_label, name)
                t = tracker.get(key)
                if t is None:
                    t = {
                        "declared": declared,
                        "kind": kind,
                        "max_len": 0,
                        "max_val": "",
                        "source_of_max": None,
                    }
                    tracker[key] = t
                if L > t["max_len"]:
                    t["max_len"] = L
                    t["max_val"] = v
                    t["source_of_max"] = source_tag
    return rows, missing, True


def distinct_overflow_count(tracker):
    return sum(1 for t in tracker.values() if t["max_len"] > t["declared"])


def fmt_elapsed(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def main():
    tracker = {}  # (type_label, col_name) -> info
    aborted = False
    abort_year = None

    overall_start = time.monotonic()

    print("=" * 64)
    print("PHASE 2 DISCOVERY - WIDTH SCAN")
    print("=" * 64)

    # Cross-year reference files
    print("Scanning cross-year reference files...")
    for label, path, checks in CROSS_YEAR_TARGETS:
        t0 = time.monotonic()
        rows, missing, existed = scan_file(path, checks, tracker, label, label)
        dt = time.monotonic() - t0
        status = "" if existed else " [MISSING]"
        miss_note = f" (headers not found: {missing})" if missing else ""
        print(f"  {label}: {rows:,} rows in {dt:.1f}s{status}{miss_note}")
    print()

    # Per-year loop
    years_scanned = 0
    years_skipped = 0
    print(f"Scanning years {min(EXPECTED_RANGE)}..{max(EXPECTED_RANGE)}...")
    for year in EXPECTED_RANGE:
        year_dir = DATA_ROOT / str(year)
        if not year_dir.exists():
            years_skipped += 1
            continue
        years_scanned += 1
        t0 = time.monotonic()
        year_rows = 0
        for csv_type, checks in PER_YEAR_SPECS:
            path = year_dir / f"{year}{csv_type}.csv"
            rows, _missing, _existed = scan_file(
                path, checks, tracker, csv_type, year
            )
            year_rows += rows
        dt = time.monotonic() - t0
        cumulative = time.monotonic() - overall_start
        print(f"  [{year}] {year_rows:,} rows in {dt:.1f}s "
              f"· cumulative {fmt_elapsed(cumulative)}",
              flush=True)

        overflows_now = distinct_overflow_count(tracker)
        if overflows_now > ABORT_THRESHOLD:
            print(f"\n!!! ABORTING: cumulative distinct-column overflow count "
                  f"reached {overflows_now} after year {year}.")
            print(f"!!! Threshold of {ABORT_THRESHOLD} exceeded - likely "
                  "script bug, not data issue.")
            aborted = True
            abort_year = year
            break

    total_elapsed = time.monotonic() - overall_start

    # Report
    print()
    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)
    if aborted:
        print(f"STATUS: ABORTED after year {abort_year} "
              f"({years_scanned} of {len(EXPECTED_RANGE)} expected years scanned)")
    else:
        print(f"STATUS: completed normally")
    print(f"Years scanned:  {years_scanned}")
    print(f"Years skipped (folder missing): {years_skipped}")
    print(f"Total elapsed:  {fmt_elapsed(total_elapsed)}")
    print()

    overflows = [(k, t) for k, t in tracker.items()
                 if t["max_len"] > t["declared"]]
    if not overflows:
        print("No width overflows detected across any scanned year or "
              "reference file.")
    else:
        print(f"{len(overflows)} column(s) exceed declared width:")
        print()
        print(f"  {'csv_type':14s} {'column':18s} "
              f"{'declared':12s} {'max_len':>8s} {'source':12s} sample")
        print(f"  {'-'*14} {'-'*18} {'-'*12} {'-'*8} {'-'*12} {'-'*30}")
        for (type_label, col), t in sorted(overflows):
            decl = (f"VARCHAR({t['declared']})" if t["kind"] == "v"
                    else "CHAR(1)")
            sample = repr(t["max_val"])
            if len(sample) > 40:
                sample = sample[:37] + "...'"
            print(f"  {type_label:14s} {col:18s} {decl:12s} "
                  f"{t['max_len']:>8d} {str(t['source_of_max']):12s} {sample}")

    # Also report columns that fit but are close to declared (within 1 char):
    # potential future risk. Only show this if no aborts.
    if not aborted:
        close = [(k, t) for k, t in tracker.items()
                 if t["max_len"] == t["declared"] and t["kind"] == "v"]
        if close:
            print()
            print(f"{len(close)} column(s) fit at exactly the declared width "
                  "(no headroom):")
            for (type_label, col), t in sorted(close):
                print(f"  {type_label}::{col} VARCHAR({t['declared']}) "
                      f"max={t['max_len']} source={t['source_of_max']}")


if __name__ == "__main__":
    main()
