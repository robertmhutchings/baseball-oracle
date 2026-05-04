"""
Proactive width sweep: scan every VARCHAR(N<=10) and CHAR(1) column the
ingest touches, comparing actual max length in the CSV against the schema's
declared width. Reports OVER cases plus the full per-file landscape.

Covers only the CSVs in the Phase-1 1998 load (cross-year + 1998 folder).
"""

import csv
from pathlib import Path

DATA_ROOT = Path(r"C:\BaseballOracle\data")
YEAR_DIR = DATA_ROOT / "1998"

# kind: 'v' = VARCHAR(declared); 'c' = CHAR(1)
TARGETS = [
    (DATA_ROOT / "teams.csv", [
        ("TEAM", 3, "v"),
    ]),
    (DATA_ROOT / "ballparks.csv", [
        ("PARKID", 5, "v"),
    ]),
    (DATA_ROOT / "biofile0.csv", [
        ("id", 8, "v"),
        ("birthdate", 8, "v"),
        ("deathdate", 8, "v"),
        ("debut_p", 8, "v"),
        ("last_p", 8, "v"),
        ("debut_c", 8, "v"),
        ("last_c", 8, "v"),
        ("debut_m", 8, "v"),
        ("last_m", 8, "v"),
        ("debut_u", 8, "v"),
        ("last_u", 8, "v"),
        ("bats", 2, "v"),
        ("throws", 2, "v"),
        ("HOF", 8, "v"),
    ]),
    (DATA_ROOT / "relatives.csv", [
        ("id1", 8, "v"),
        ("id2", 8, "v"),
    ]),
    (YEAR_DIR / "1998gameinfo.csv", [
        ("visteam", 3, "v"),
        ("hometeam", 3, "v"),
        ("site", 5, "v"),
        ("starttime", 10, "v"),
        ("daynight", 10, "v"),
        ("umphome", 10, "v"),
        ("ump1b", 10, "v"),
        ("ump2b", 10, "v"),
        ("ump3b", 10, "v"),
        ("umplf", 10, "v"),
        ("umprf", 10, "v"),
        ("wp", 8, "v"),
        ("lp", 8, "v"),
        ("save", 8, "v"),
        ("wteam", 3, "v"),
        ("lteam", 3, "v"),
        ("line", 4, "v"),
        ("batteries", 10, "v"),
        ("lineups", 4, "v"),
        ("box", 4, "v"),
        ("pbp", 4, "v"),
    ]),
    (YEAR_DIR / "1998allplayers.csv", [
        ("id", 8, "v"),
        ("bat", 2, "v"),
        ("throw", 2, "v"),
        ("team", 3, "v"),
        ("pos", 3, "v"),
    ]),
    (YEAR_DIR / "1998batting.csv", [
        ("id", 8, "v"),
        ("team", 3, "v"),
        ("stattype", 10, "v"),
        ("site", 5, "v"),
        ("opp", 3, "v"),
        ("box", 4, "v"),
        ("wl", 1, "c"),
    ]),
    (YEAR_DIR / "1998pitching.csv", [
        ("id", 8, "v"),
        ("team", 3, "v"),
        ("stattype", 10, "v"),
        ("site", 5, "v"),
        ("opp", 3, "v"),
        ("box", 4, "v"),
        ("wl", 1, "c"),
    ]),
    (YEAR_DIR / "1998fielding.csv", [
        ("id", 8, "v"),
        ("team", 3, "v"),
        ("stattype", 10, "v"),
        ("site", 5, "v"),
        ("opp", 3, "v"),
        ("box", 4, "v"),
        ("wl", 1, "c"),
    ]),
    (YEAR_DIR / "1998teamstats.csv", [
        ("team", 3, "v"),
        ("mgr", 8, "v"),
        ("stattype", 10, "v"),
        *((f"start_l{i}", 8, "v") for i in range(1, 10)),
        *((f"start_f{i}", 8, "v") for i in range(1, 11)),
        ("site", 5, "v"),
        ("opp", 3, "v"),
        ("box", 4, "v"),
        ("wl", 1, "c"),
    ]),
    (YEAR_DIR / "1998plays.csv", [
        ("ballpark", 5, "v"),
        ("batteam", 3, "v"),
        ("pitteam", 3, "v"),
        ("batter", 8, "v"),
        ("pitcher", 8, "v"),
        ("count", 2, "v"),  # CSV 'count' -> DB pitch_count VARCHAR(2)
        ("br1_pre", 8, "v"),
        ("br2_pre", 8, "v"),
        ("br3_pre", 8, "v"),
        ("br1_post", 8, "v"),
        ("br2_post", 8, "v"),
        ("br3_post", 8, "v"),
        ("run_b", 8, "v"),
        ("run1", 8, "v"),
        ("run2", 8, "v"),
        ("run3", 8, "v"),
        ("prun1", 8, "v"),
        ("prun2", 8, "v"),
        ("prun3", 8, "v"),
        ("f2", 8, "v"), ("f3", 8, "v"), ("f4", 8, "v"), ("f5", 8, "v"),
        ("f6", 8, "v"), ("f7", 8, "v"), ("f8", 8, "v"), ("f9", 8, "v"),
        ("loc", 10, "v"),
        ("bathand", 1, "c"),
        ("pithand", 1, "c"),
        ("hittype", 4, "v"),  # post-update VARCHAR(4)
    ]),
]


def scan(csv_path, checks):
    with open(csv_path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        lower = [h.lower() for h in header]
        tracked = []
        missing = []
        for name, declared, kind in checks:
            try:
                idx = lower.index(name.lower())
            except ValueError:
                missing.append(name)
                continue
            tracked.append({
                "idx": idx, "name": name,
                "declared": declared, "kind": kind,
                "max_len": 0, "max_val": "", "over_count": 0,
            })
        for row in reader:
            for t in tracked:
                i = t["idx"]
                v = row[i] if i < len(row) else ""
                L = len(v)
                if L > t["max_len"]:
                    t["max_len"] = L
                    t["max_val"] = v
                if L > t["declared"]:
                    t["over_count"] += 1
    return tracked, missing


def main():
    overall_problems = []  # (file, column, declared, max_len, sample, over_count)

    for csv_path, checks in TARGETS:
        print()
        print(f"=== {csv_path.name} ({len(checks)} cols checked) ===")
        if not csv_path.exists():
            print(f"  MISSING FILE: {csv_path}")
            continue
        tracked, missing = scan(csv_path, checks)

        print(f"  {'col':18s} {'declared':12s} {'max_len':>8s}  "
              f"{'status':6s}  sample_of_longest")
        print(f"  {'-'*18} {'-'*12} {'-'*8}  {'-'*6}  {'-'*30}")
        for t in tracked:
            declared_str = (f"VARCHAR({t['declared']})" if t["kind"] == "v"
                            else "CHAR(1)")
            over = t["over_count"] > 0
            status = f"OVER" if over else "ok"
            sample = repr(t["max_val"]) if t["max_val"] else "''"
            if len(sample) > 40:
                sample = sample[:37] + "...'"
            print(f"  {t['name']:18s} {declared_str:12s} {t['max_len']:>8d}  "
                  f"{status:6s}  {sample}")
            if over:
                overall_problems.append(
                    (csv_path.name, t["name"], declared_str,
                     t["max_len"], t["max_val"], t["over_count"])
                )
        if missing:
            print(f"  NOTE: headers not found in CSV: {missing}")

    print()
    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)
    if not overall_problems:
        print("No width overflows detected. All VARCHAR(N<=10) and CHAR(1) "
              "columns fit the declared width in 1998 data.")
    else:
        print(f"{len(overall_problems)} column(s) exceed declared width:")
        for f, c, decl, ml, samp, cnt in overall_problems:
            print(f"  {f} :: {c} :: declared {decl}, "
                  f"max_len={ml}, sample={samp!r}, {cnt} rows over")


if __name__ == "__main__":
    main()
