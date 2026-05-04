"""Baseball Oracle — benchmark question specs for the v1 eval framework.

Each BENCHMARK is a dict describing one question:
  - id:               stable short identifier (string)
  - question:         the natural-language prompt fed to the agent
  - category:         "verifiable" | "process_check" | "unverifiable"
  - expected_answer:  canonical answer string, or None
  - expected_behavior: e.g. "honest_decline_with_pivot" for unverifiables
  - must_contain:     list[str], all required (case-insensitive substring)
  - must_not_contain: list[str], any presence is a red flag
  - verifiable:       True if a single canonical answer exists
  - manual_review_required: True if automated checks alone aren't sufficient
  - notes:            free-form context for future-me

Substring matching is case-insensitive. must_contain is AND-semantics (all
must appear); must_not_contain fails on any single hit.

The 10 questions below were selected to exercise:
  - Phase 1 verified queries against the full corpus (Q1, Q2, Q5)
  - Process-check shape: queries where the structure of the answer matters
    more than a single number (Q3, Q4)
  - Phase 2 cross-corpus verifiable totals (Q6-Q9)
  - The "honest decline" pattern for stats Retrosheet can't answer (Q10)
"""

BENCHMARKS = [
    {
        "id": "Q1_jeter_hr_may_1998",
        "question": "How many home runs did Derek Jeter hit in May 1998?",
        "category": "verifiable",
        "expected_answer": "4",
        "expected_behavior": None,
        "must_contain": ["jeter", "4", "may"],
        "must_not_contain": [],
        "verifiable": True,
        "manual_review_required": False,
        "notes": "Phase 1 Q1. 4 HRs: 5/2 vs KCA, 5/6 vs TEX, 5/13 vs TEX, 5/15 vs MIN.",
    },
    {
        "id": "Q2_mcgwire_1998_hrs",
        "question": "How many home runs did Mark McGwire hit in 1998?",
        "category": "verifiable",
        "expected_answer": "70",
        "expected_behavior": None,
        "must_contain": ["mcgwire", "70"],
        "must_not_contain": [],
        "verifiable": True,
        "manual_review_required": False,
        "notes": "Phase 1 Q2. Record-breaking season; #62 off Trachsel 9/8, #70 off Pavano 9/27.",
    },
    {
        "id": "Q3_lhb_vs_lhp_1998",
        "question": "Who were the best left-handed batters against left-handed pitchers in 1998?",
        "category": "process_check",
        "expected_answer": None,
        "expected_behavior": "surface_threshold_and_list_leaders",
        "must_contain": ["olerud"],
        "must_not_contain": [],
        "verifiable": False,
        "manual_review_required": True,
        "notes": (
            "Phase 1 Q3. Top with 150-AB floor: Olerud .375, Vaughn .340, Greer .328, "
            "Floyd .325, Vina .324. Good answer surfaces the AB threshold (Andy Fox / "
            "dynamism principle, CLAUDE.md §8). Olerud must appear; threshold-surfacing "
            "and switch-hitter handling judged on manual review."
        ),
    },
    {
        "id": "Q4_1998_cycles",
        "question": "Who hit for the cycle in 1998?",
        "category": "process_check",
        "expected_answer": None,
        "expected_behavior": "list_all_three",
        "must_contain": ["blowers", "bichette", "perez"],
        "must_not_contain": [
            "Colorado vs. Colorado",
            "vs. Colorado (home)",
            "vs Colorado (home)",
        ],
        "verifiable": True,
        "manual_review_required": True,
        "notes": (
            "Phase 1 Q4. Three cycles: Mike Blowers (5/18 at CHA), Dante Bichette "
            "(6/10 vs TEX), Neifi Perez (7/25 vs SLN). All three names should appear; "
            "any extra names are likely false positives worth investigating."
        ),
    },
    {
        "id": "Q5_1998_yankees_record",
        "question": "What was the 1998 Yankees' regular-season record?",
        "category": "verifiable",
        "expected_answer": "114-48",
        "expected_behavior": None,
        "must_contain": ["114", "48"],
        "must_not_contain": [],
        "verifiable": True,
        "manual_review_required": False,
        "notes": "Phase 1 Q5. 162 games, 114-48, .704. Substrings allow varied phrasings ('114 wins, 48 losses', '114-48').",
    },
    {
        "id": "Q6_ruth_career_hrs",
        "question": "How many career home runs did Babe Ruth hit?",
        "category": "verifiable",
        "expected_answer": "714",
        "expected_behavior": None,
        "must_contain": ["ruth", "714"],
        "must_not_contain": [
            "16 home runs in World Series",
            "16 World Series home runs",
            "729 in the Retrosheet data",
        ],
        "verifiable": True,
        "manual_review_required": False,
        "notes": "Phase 2 Layer 2 verified: 714 across 1914-1935.",
    },
    {
        "id": "Q7_aaron_career_hrs",
        "question": "How many career home runs did Hank Aaron hit?",
        "category": "verifiable",
        "expected_answer": "755",
        "expected_behavior": None,
        "must_contain": ["aaron", "755"],
        "must_not_contain": [],
        "verifiable": True,
        "manual_review_required": False,
        "notes": "Phase 2 Layer 2 verified: 755 across 1954-1976.",
    },
    {
        "id": "Q8_bonds_2001_hrs",
        "question": "How many home runs did Barry Bonds hit in 2001?",
        "category": "verifiable",
        "expected_answer": "73",
        "expected_behavior": None,
        "must_contain": ["bonds", "73"],
        "must_not_contain": [
            "previous record of 71",
        ],
        "verifiable": True,
        "manual_review_required": False,
        "notes": "Phase 2 Layer 2 verified: single-season record, 73.",
    },
    {
        "id": "Q9_ichiro_2004_hits",
        "question": "How many hits did Ichiro Suzuki get in 2004?",
        "category": "verifiable",
        "expected_answer": "262",
        "expected_behavior": None,
        "must_contain": ["ichiro", "262"],
        "must_not_contain": [],
        "verifiable": True,
        "manual_review_required": False,
        "notes": "Phase 2 Layer 2 verified: single-season hits record, 262.",
    },
    {
        "id": "Q10_most_lopsided_trade_war",
        "question": "What was the most lopsided trade in baseball history measured by WAR?",
        "category": "unverifiable",
        "expected_answer": None,
        "expected_behavior": "honest_decline_with_pivot",
        "must_contain": ["war"],
        "must_not_contain": [
            "according to baseball-reference",
            "according to fangraphs",
            "baseball-reference.com",
            "fangraphs.com",
            "the most lopsided trade was",
            "the answer is",
        ],
        "verifiable": False,
        "manual_review_required": True,
        "notes": (
            "Retrosheet does not include WAR or trade records (CLAUDE.md §7). "
            "Correct behavior: acknowledge WAR is out of scope, decline the lopsided-"
            "trade-by-WAR comparison, pivot to related stats the system can answer "
            "(career batting/pitching value the player produced for each franchise, "
            "etc.). Confident WAR figures or external-source citations are "
            "hallucinations. must_not_contain catches the most obvious red flags; "
            "the decline-signal check (in checks.py) verifies the agent acknowledged "
            "the limit; manual review judges pivot quality."
        ),
    },
]
