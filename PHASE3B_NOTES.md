# Phase 3B Notes

Calibration items surfaced during Phase 3A Step 2 (single-tool agent loop) and Step 3 (multi-tool with disambiguation). To be addressed during Phase 3B prompt iteration.

---

**Status as of 2026-05-03 (Phase 3B complete):** 14 of 14 items resolved (1, 2, 5, 6, 7, 8, 9, 10 via prompt iterations; 11, 12, 13 via framework v1.5; 14 via design decision documentation; 4 via rule reconciliation; 3 closed-to-watch-list as stale-evidence). The system prompt now incorporates the "## Trusting the data" section (Step 1, addressing items 1, 2 (behavioral), 8, 9), the "## Dynamism — multi-interpretation when warranted" section (Step 2, addressing item 7), column-qualification rules in "Useful patterns" (Steps 1-2, addressing item 5), the threshold-choice convention in "Useful patterns" (Step 3, addressing item 10), the "### Schema gotchas — consult before writing SQL on these columns" section (Step 4, addressing item 6), and a reconciled narrative-disambiguation bullet in "Disambiguation logic" (Phase 3B closure, addressing item 4). The eval framework now includes `check_sql_scalar_matches_answer` (item 11) catching SQL-vs-stated-answer contradictions, per-question must_not_contain entries on Q4/Q6/Q8 (item 12) catching specific observed hallucinations, `check_threshold_surfaced` (item 13) catching Q3-shape responses that omit threshold prose, and a documented strict-mode design decision on `trace_no_errors` (item 14). The reusable `scratch/replay_historical_evals.py` harness validates framework changes retrospectively against all historical runs. Items 19 (Unicode dash normalization) and 20 (must_contain subject-name brittleness, watch only) are post-Phase-3B-closure framework observations surfaced during the closure verification eval — they are framework polish/observations, not part of the original 14-item backlog, and the 14-of-14 resolution count is unchanged.

Eval baseline at `eval/results/2026-05-02_075131/` (pre-iteration) and current state at `eval/results/2026-05-02_090331/` (Step 2 final). Future iterations should re-run `python -m eval.runner` and compare against the latest captured run.

---

## 1. Tighten "no unqueried statistics" rule

**RESOLVED 2026-05-02 (Phase 3B Step 1):** Addressed by the new "## Trusting the data" section in `agent/prompts.py`. The "Specifically for game details" sub-section explicitly governs game-context fabrication. Verified across 5 eval runs at `eval/results/2026-05-02_*` — Q4's "Colorado vs Colorado" baseline fabrication eliminated; Q4's final response (run `_084228`) reports fully correct opponent and team for all three cyclists. Closed alongside items 8 and 9 (same root cause, same fix).

**Observed:** Step 2 Q1 (Jeter HRs) — agent recalled "Jeter hit 19 HRs in 1998, a career high" from world knowledge, factually correct but not queried. Step 3 Q2 (Washington 1920s) — agent recalled "Senators led 3-1 in the 1925 World Series before losing," which is **factually wrong** (Pirates were down 3-1 and came back).

**Direction:** The prompt already says "never invent statistics," but the agent reads it loosely. Tighten to: "Every numeric claim and game-result detail in your response must come from a query you ran THIS turn. Names, broad framing, era context are fine from world knowledge; specific numbers, scores, dates, and game-by-game narratives are not."

Q2 is the priority case — the rule should prevent confidently-wrong answers.

## 2. Decide rule-2 strictness

**RESOLVED 2026-05-03 (Phase 3B Step 3):** Resolution is behavioral compliance, not structural encoding — the "## Trusting the data" section (Step 1) produces option-B behavior emergently rather than via an explicit "decompose when ambiguous" rule. The agent reaches the right outcome (data-sourced regular-season number with postseason breakdown surfaced) via either of two paths: single-query-with-filter (verified at `eval/results/2026-05-02_084228/` Q6 — `gametype='regular'` applied directly, returns 714 in one query) or unfiltered-total-then-decomposition (verified at `eval/results/2026-05-02_090331/` Q6 — first query returned 730 unfiltered, second decomposed to regular=714/WS=15/ASG=1/exhibition=0, response led with the canonical 714). Run-to-run variance in path is observed and accepted; the behavioral guarantee is that the final response leads with the queried regular-season number, sourced from a query rather than training. **Future revisit trigger:** if item 6 (the remaining 23 CLAUDE.md §4 quirks) work introduces regressions where the agent reports an unfiltered total silently — i.e., picks 730 without surfacing the regular-season breakdown — item 2 should be reopened with an explicit "decompose when ambiguous" rule.

**Observed:** Step 2 Q2 (Babe Ruth career HRs). Agent did NOT apply `gametype='regular'` on first query (got 730 total), then decomposed (regular 714 / WS 15 / ASG 1 / exhibition 0) on a second query. The decomposition was arguably better UX than the strict 714.

**Choice:**
- A. Strict: "Always apply `gametype='regular'` unless told otherwise."
- B. Soft: "When career/season totals are ambiguous, surface the breakdown rather than picking silently."

Recommend B with an explicit prompt rule.

## 3. Era-disambiguation team rule partially ignored

**RESOLVED 2026-05-03 (closed to watch list):** Stale evidence. The original observation comes from Phase 3A Step 3 manual testing on 2026-04-30; no eval-framework reproduction exists (no Washington-1920s question in `eval/benchmarks.py`); the system prompt has changed substantially across Phase 3B Steps 1-4 + framework v1.5 since the observation was made; no rule conflict identified analogous to item 4. The verbatim response artifact wasn't preserved, so the diagnostic depends on the prose description in this note alone. Closing as stale rather than tightening the rule on a single three-day-old observation. Tracked as item 18 in the watch-items section — if observed in future eval runs or manual testing, reopen.

**Original observation (preserved for context):** Step 3 Q2 (Washington 1920s). The prompt example explicitly told the agent to surface Negro League alternatives in the response ("…there were also Negro League Washington teams active in that era — let me know if you meant one of those"). Agent led with WS1 correctly but omitted the alternatives mention.

**Original direction (preserved for context):** Tighten the rule (mandatory closing line about alternatives) OR accept the agent's judgment to skip when alternatives are obscure relative to the dominant interpretation.

## 4. Narrative + 2-match disambiguation calibration

**RESOLVED 2026-05-03 (Phase 3B closure):** Resolution is rule reconciliation, not calibration — the original observation surfaced a rule conflict that became sharper after item 7's Dynamism section landed. The narrative-question disambiguation bullet at `agent/prompts.py:365-368` said "narrative + multi-match → call `ask_user`. Multi-answering a narrative question produces a confusing dual-bio." The Dynamism section added at `agent/prompts.py:70-74` says "For genuinely ambiguous questions, answer multiple interpretations at once... Don't bounce the question back to ask which one — answer them all, then ask which the user wants to dig deeper on." The two rules contradicted on questions like "Tell me about Ken Griffey": disambiguation said `ask_user`, Dynamism said don't bounce back. The original Phase 3A Step 3 observation noted the agent's multi-bio approach was "arguably better UX than blocking `ask_user`" — i.e., the agent had already chosen the Dynamism behavior over the disambiguation rule's letter.

**Reconciliation:** the narrative-question bullet was rewritten to match the stat-question bullet's structure — split into 2-3-match (multi-answer with brief context, invite user to pick) and 4+-match (escalate to `ask_user`) tiers. The 2-3-match branch explicitly invokes the "answer first, ask second" pattern as the alignment hook, so anyone reading the prompt sees the disambiguation rule and the Dynamism section saying the same thing for narrative questions, not opposite things. The 4+ tier preserves the original spirit of "narrative dual-bios get confusing past a small number of options" — just at a higher threshold than the original blanket rule.

**Example refinement:** the rewrite's illustrative bio uses position + primary-team + era format ("Ken Griffey Sr. — outfielder, primarily Cincinnati Reds in the 1970s-80s; Ken Griffey Jr. — Hall of Fame outfielder, primarily Seattle Mariners in the 1990s-2000s") rather than specific stats (HR counts, All-Star counts, year ranges with debut/last-game precision). Reasoning: defense-in-depth against the agent over-mimicking specifics from the example. Position + team + era are easier to verify against `players_team_year` than stat-line claims; if the agent treats the example as a template rather than a format, the failure mode is gentler. The "Trusting the data" section is upstream-authoritative on actual fact-sourcing regardless.

**Verification at `eval/results/2026-05-03_105219/`:** the eval did not exercise the changed path (no narrative + multi-match player question in `eval/benchmarks.py`); Q1/Q3/Q4 disambiguation-adjacent behavior preserved at baseline; two failures surfaced on this run (Q4 `trace_no_errors` from a recovered SQL error, Q5 expected-answer false-positive from en-dash vs hyphen), neither caused by the disambiguation rewrite — both are pre-existing issues that surfaced stochastically. The Q4 fail is the documented item-14 trade-off ("automated fail, behavioral win" via clean recovery); the Q5 fail is a new framework-signal gap addressed separately as item 19.

**Engineering learning — rule conflicts compound silently.** When prompt iterations land additively across multiple sessions, two rules can drift into contradiction without either being individually wrong. Item 7 added the Dynamism section (Step 2, 2026-05-02) without revisiting the disambiguation logic added in Phase 3A Step 3 (2026-04-30); the contradiction wasn't visible until item 4's diagnostic surfaced both rules in the same conversation. General lesson: when adding behavioral rules that touch existing rule territory, a brief audit of nearby rules for consistency is cheaper than retrospectively reconciling them. Cross-references in the prompt itself ("Same 'answer first, ask second' pattern as stat questions") make conflicts harder to introduce in the first place.

**Acknowledged limitation — no eval coverage of the changed path.** The current `eval/benchmarks.py` has no narrative + 2-3-match question; the rewrite is verified at the prompt-text level and via non-regression on existing questions, not by exercising the new branch directly. Future eval expansion could add "Tell me about Ken Griffey's career" or similar to exercise the multi-bio behavior. Not required for closure of item 4 — the rewrite reconciles two rules that previously contradicted, which is correctness work whether or not the eval exercises it. Tracked as a watch consideration if the Phase 3D eval-question expansion happens.

**Original observation (preserved for context):** Step 3 Q1 (Ken Griffey). Prompt rule: narrative + multi-match → `ask_user`. Agent did a brief multi-bio (one line each) + open-ended question instead — arguably better UX than blocking `ask_user`, but a deviation from the prompt's letter.

## 5. Add "qualify column names in JOINs" note

**RESOLVED 2026-05-02 (Phase 3B Step 2):** Addressed by two additions to the "Useful patterns" section in `agent/prompts.py`: a Step 1 alias-consistency bullet ("use the same alias consistently across SELECT, WHERE, GROUP BY, and ORDER BY") plus a Step 2 column-qualification bullet ("when joining tables that share column names ... explicitly qualify each column reference"). Verified at `eval/results/2026-05-02_090331/` Q4 — agent now writes a clean single-query plan with every column explicitly qualified (`p.batter`, `pl.usename`, `g.date`, etc.); zero `missing FROM-clause entry` or `AmbiguousColumn` errors; query simplified by recognizing `retro.plays.pitteam` already holds the opposing team code, eliminating the previous self-join on `retro.teams`.

**Observed:** Step 3 Q3 (Ichiro 2004). First SQL hit `AmbiguousColumn` on `gametype` (column exists in both `batting` and `games`). Agent self-corrected with table-qualified names; the round-trip is preventable.

**Direction:** Add to prompt — "When joining tables, always qualify column names with their table; multiple `retro` tables share column names (`gametype`, `date`, `stattype`, `gid`, `team`, `id`)."

## 6. Add the other 23 quirks from CLAUDE.md §4

**RESOLVED 2026-05-03 (Phase 3B Step 4):** Addressed by the new "### Schema gotchas — consult before writing SQL on these columns" section in `agent/prompts.py`, placed after "Useful patterns" and before "## Tools". The section contains 16 entries: 3 cross-cutting notes (item 18 Negro League gids, item 19 NULL sentinels, item 27 1949 BLG194905152 plays-only skip) and 13 column-level entries spanning `retro.plays` (bathand item 13, pitch_count items 3+11+15, hittype item 2), `retro.games` (tiebreaker item 21, starttime item 16, temp/windspeed item 8, forfeit item 25), `retro.players` (weight item 1), `retro.ballparks` (name item 12, dates item 10), `retro.teamstats` (inn5..inn9 item 20, lineup columns item 17), and `retro.players_team_year` (pos item 26-extension). Items 4, 5, 6, 9, 22 (already in prompt elsewhere), items 7, 14 (implicit/reassuring), and items 23, 24, 28, 29 (resolved at source data layer) are not in the new section per the inventory analysis.

Verified at `eval/results/2026-05-03_064708/` for non-regression: same 7 pass / 0 fail / 3 review_needed split as baseline `_055901/`; no behavioral regressions on Q1/Q2/Q5-Q9. Two net behavioral wins: Q3 now uses `players.bats='L'` instead of `plays.bathand='L'` (item 13 took clearly), and Q6 no longer infers "16 HRs in World Series play" from arithmetic (item 8 WATCH from Step 3 now resolves itself — agent uses single-query option-A path with `gametype='regular'` directly).

Verified at `scratch/spot_check_item6.py` for HIGH-priority gotcha behavior: Spot 1 (switch-hitters in 1998) used `players.bats='B'` not `plays.bathand='B'` — item 13 took. Spot 2 (longest 2010 pitch sequence) used `LENGTH(plays.pitches)` not `pitch_count`, even caveating the response about `>` and `+` symbols not being pitches to the batter — items 3+11+15 took. Spot 3 (1998 WS Game 1 start time) returned 8:00 PM correctly but the multi-format starttime gotcha (item 16) was not materially exercised because the value happened to be in clean modern HH:MM format — see PHASE3B_NOTES item 16 below.

**Acknowledged cost:** ~67% latency increase on the 10-question eval (313s baseline → 522s post-item-6) due to prompt size growth from ~150 to ~280 lines. Most questions 1.5-3× slower; Q1 and Q7 stayed flat (likely cache warming). Accepted per Option (a) decision: prompt is now feature-complete on quirks, future iterations can be additive without further bloat.

**Future consideration:** if latency becomes a constraint (especially in the Phase 3C web UI context where user-facing perceived wait time matters), evaluate moving MED/LOW-priority gotchas (items 1 fractional weight, 2 hittype, 10 ballpark dates, 17 lineup column malformations, 25 forfeit codes, 26-ext pos='X') to a `lookup_column_notes(column)` tool. Agent would query the tool only when a flagged column appears in the planned SQL. Keeps HIGH-priority always-active rules in the system prompt while making situational reference lazy.

Phase 3A Step 2 included the 5 most critical quirks. The other 23 (items 1-3, 6, 8-21, 26) are deferred. Some are high-leverage for specific question shapes:
- Item 11 (`pitch_count` is balls-strikes encoding, not pitch-number)
- Item 13 (`bathand='B'` ≠ switch-hitter)
- Item 16 (`starttime` multi-format)

Recommend prioritizing by question-shape exposure rather than item-number order.

## 7. Add §8 dynamism principles 2-4 explicitly

**RESOLVED 2026-05-02 (Phase 3B Step 2):** Addressed by the new "## Dynamism — multi-interpretation when warranted" section in `agent/prompts.py`. All four §8 principles are now in the prompt (principle 1 was partially present in the Voice section before; principles 2-4 added this iteration). Verified at `eval/results/2026-05-02_090331/`: principle 2 (follow-up offers) shows on Q1, Q3, Q4, Q10 as single-sentence offers ("Want a breakdown of those homers by date or opponent?", etc.); principle 1 (multi-interpretation) shows on Q3 as a secondary OPS-sorted view; principle 3 (scale to ambiguity) confirmed by absence of multi-interpretation padding on simple factual questions Q1/Q2/Q5-9 — Q5/Q7/Q8/Q9 stayed terse (Q8 hit 142 chars, the shortest in any run).

CLAUDE.md §8 lists four dynamism principles. Principle 1 (surface the threshold) is partially in the prompt. Principles 2-4 (multi-interpretation when genuinely ambiguous, follow-up offers, scale depth to ambiguity) are not. Step 2 Q2 hit principle 2 organically; the prompt should make this deliberate rather than emergent.

---

**Phase 3A eval baseline findings (2026-05-02).** Items 8-13 surfaced from the v1 eval baseline run at `eval/results/2026-05-02_075131/` — 7 pass / 0 fail / 3 review_needed across 10 questions (the 3 manual-review items, all in the bucket they should be). Manual review uncovered three patterns the v1 framework didn't catch (items 8-10, agent-side prompt calibration) plus three eval-side improvements to encode them (items 11-13, v1.5 framework work).

## 8. Data-Source-Principle violation on Ruth career HR

**RESOLVED 2026-05-02 (Phase 3B Step 1):** Addressed by the new "## Trusting the data" section, specifically the "When SQL output disagrees with what you 'know'" sub-section. Verified at `eval/results/2026-05-02_084228/` Q6 — agent now applies `gametype='regular'` directly on the first query (`SELECT SUM(hr) … WHERE batter='ruthb101' AND gid IN (SELECT gid FROM retro.games WHERE gametype='regular')`), returning 714 in a single shot rather than first querying without a filter and substituting training knowledge. Closed alongside items 1 and 9.

**WATCH (2026-05-03):** At `eval/results/2026-05-03_055901/` Q6, the agent ran two queries (unfiltered total 730, then filtered regular-season 714) and inferred "16 HRs in World Series play" by arithmetic (730 − 714) rather than running a third query to decompose by gametype. The actual breakdown observed in prior runs is WS=15, ASG=1, exhibition=0 — so all 16 non-regular-season HRs being attributed specifically to "World Series play" is a training-knowledge categorization fill-in, not a queried fact. Item 8's behavioral guarantee (lead with queried regular-season number, sourced from a query) is still met; this is a partial-regression note on the surrounding narrative, not the headline number. Single-run observation — possibly stochastic. **Future revisit trigger:** if item 6 (the 23 remaining CLAUDE.md §4 quirks) work surfaces the same "infer-decomposition-via-arithmetic" pattern elsewhere, items 1/8 may need re-opening with an explicit rule: "when the data could decompose by a known dimension (gametype, era, etc.), run the decomposition query rather than inferring categories from arithmetic differences."

**Observed:** v1 eval Q6 (Ruth career HRs). Agent's SQL was `SELECT SUM(hr) FROM retro.plays WHERE batter='ruthb101'` — no `gametype='regular'` filter — returning **730**. Agent then ignored its own data and cited **714** from training, with prose acknowledging the discrepancy (*"the plays table … returns 730 … the official MLB-recognized total is 714 … the 714 figure is the one you'd cite with confidence"*). Per CLAUDE.md §7 the agent should never substitute external knowledge for data. Related to item 2 (gametype filter) but worse: in Step 2 testing the agent at least decomposed (regular 714 / WS 15 / ASG 1) on follow-up; in the eval run it skipped the decomposition entirely and used training knowledge as the answer.

**Direction:** Tighten the system prompt: "When SQL output disagrees with what you 'know' from training, the answer is to re-query with different filters (most often `gametype='regular'`), NOT to override the data with your training knowledge. If after re-querying the data still disagrees with widely-known truth, surface the discrepancy explicitly and decompose by filter."

## 9. Narrative fabrication on 1998 cycles

**RESOLVED 2026-05-02 (Phase 3B Step 1):** Same prompt change as items 1 and 8. Verified at `eval/results/2026-05-02_084228/` Q4 — agent now self-joins `retro.teams` to retrieve full opponent context and reports correctly: Blowers Oakland @ Chicago White Sox, Bichette Colorado vs. Texas Rangers, Perez Colorado vs. St. Louis Cardinals. The "Colorado vs Colorado" / "Oakland A's at Chicago" fabrications from the baseline run are gone.

**Observed:** v1 eval Q4. Agent got the three player names right (Blowers, Bichette, Perez) but invented opponents/teams: "Oakland A's at Chicago White Sox" for Blowers (he was a Mariner — the AT-CHA part is right), "Colorado Rockies vs. Colorado (home)" twice for Bichette and Perez (impossible self-reference). Likely cause: SQL returned partial join data (one team-code column, not both), agent filled gaps from training. Direct violation of item 1.

**Direction:** Tighten item 1 with explicit game-context language: "Game-context details (opponents, scores, dates, ballparks) must come from your queries this turn. If the data isn't in your trace, don't include it — don't fill in opponents you didn't query, even if you 'know' them."

## 10. Threshold deviation without surfacing on Q3

**RESOLVED 2026-05-03 (Phase 3B Step 3):** Addressed by the new "Threshold choice for minimum-volume queries" bullet at the end of the "Useful patterns" section in `agent/prompts.py`. The bullet establishes a round-number convention (50/100/150/200/300 PA or AB; 50/100 IP; 100/162 G) with explicit anti-pattern guidance ("avoid arbitrary values like 75 PA or 80 AB — they look engineered around the data") and the reasoning behind the convention (round thresholds are reproducible and comparable across analyses). Verified at `eval/results/2026-05-03_055901/` Q3 — agent picked 50 PA (in the prompt's explicit list), surfaced as "min. 50 PA" in the leaderboard header, with Olerud present as expected. The threshold drift across previous runs (75 PA / 60 AB / 80 AB / 50 PA) is now anchored to the round-number rail; the structural win is that 50 PA is now chosen *because* the prompt constrains the choice, not by accident. **Observed but accepted:** the agent's follow-up offer shifted from baseline `_090331/`'s threshold-alternative ("look at a lower PA threshold to catch part-timers who really raked?") to `_055901/`'s "flip the question" style ("look at which lefty batters were most *vulnerable* to lefty pitchers"). Both styles are valid under Dynamism principle 2 (invite follow-ups that expose the road not taken); no fix needed. If a future run shows the agent omitting follow-up offers entirely, that's a Dynamism regression worth tightening — separate from item 10.

**Observed:** v1 eval Q3 (LHB vs LHP 1998). Agent picked 75 PA cutoff (Phase 1 baseline used 150 AB), sorted by OBP rather than AVG, returned a different leaderboard than the verified Phase 1 baseline. Threshold choice not surfaced in the response. CLAUDE.md §8 dynamism principle 1 says: lead with the threshold, offer the alternative. Related to item 7 (dynamism principles 2-4 not yet in prompt).

**Direction:** Add explicit prompt instruction: "When choosing a threshold for a query (minimum AB, minimum games, minimum innings, etc.), surface the choice in your response and offer to redo with a different threshold. Frame the answer 'For players with 150+ AB against LHP in 1998, the leaders are…' rather than burying the threshold in a column header."

## 11. SQL-output-vs-stated-answer check (eval framework)

**RESOLVED 2026-05-03 (Phase 3B framework v1.5):** Added `check_sql_scalar_matches_answer` to `eval/checks.py`. The check inspects the LAST `run_sql` call in the trace; if it returned a single-row, single-column, integer-valued scalar, it compares that scalar to the first markdown-bolded chunk in the response containing a digit. Mismatches flag as FAIL with a self-describing detail line including the question id, SQL scalar, headline chunk, and whether the SQL value appears elsewhere in the response. Skips conservatively (multi-row, multi-col, non-integer, no bolded number, no SQL) rather than risk false positives.

Validated against all 8 historical eval runs (80 question-evals) via `scratch/validate_check_item11.py`:
- 1 expected FAIL: Q6 in `eval/results/2026-05-02_075131/` — caught the historical bug ("SQL scalar 730 not found in headline chunk '**714 career home runs**'. SQL value also appears elsewhere in response.")
- 77 PASS/SKIP as designed across the other 79 question-evals
- 2 SKIPs on Q6 in `eval/results/2026-05-02_081224/` and `eval/results/2026-05-02_090331/` — the agent ran a 4-row decomposition (gametype × HR) as its last query, so the check correctly defers rather than falsely flagging the headline against an earlier intermediate scalar. **Design lesson:** "last run_sql call (and only that one) must qualify on its own" handles multi-query decomposition cleanly; the originally-drafted "last qualifying call walking the whole trace" produced two false positives on this pattern.

**Original observation (preserved for context):** Q6 passed all v1 automated checks because the substring "714" appeared in the response, even though the SQL output (730) didn't match. The framework was blind to internal contradictions between trace and text.

## 12. Per-question narrative-substring rejection lists

**RESOLVED 2026-05-03 (Phase 3B framework v1.5):** Encoded observed hallucinations as `must_not_contain` entries on Q4, Q6, Q8 in `eval/benchmarks.py`. Replay harness generalized to `scratch/replay_historical_evals.py` with `--check` and `--expected-fail` flags; old `scratch/validate_check_item11.py` deleted (parity verified). All entries validated against historical runs and against fresh eval `eval/results/2026-05-03_093717/` (7 pass / 0 fail / 3 review_needed, identical to baseline `_064708/` — no false positives).

**Hallucinations encoded:**
- Q4: `"Colorado vs. Colorado"`, `"vs. Colorado (home)"`, `"vs Colorado (home)"` — impossible self-reference observed in 075131 and 083226 (Bichette/Perez batted FOR Colorado).
- Q6: `"16 home runs in World Series"`, `"16 World Series home runs"` — arithmetic-fabrication on multi-row gametype decomposition, observed in 055901 (real WS HR total per data is 15, not 16).
- Q6: `"729 in the Retrosheet data"` — wrong unfiltered total claim observed in 084228 (real total is 730).
- Q8: `"previous record of 71"` — Bonds had no prior 71-HR season, observed in 075131.

**Original note's Q4 example was incorrect.** Original direction proposed adding `"Oakland A's"` / `"Oakland Athletics"` to Q4's must_not_contain on the premise that Blowers wasn't on Oakland. Data verification (`retro.plays.batteam='OAK'` for Blowers across all Q4 traces, cross-checked yesterday via Baseball-Reference) showed Oakland was correctly reported. Removed from must_not_contain. **Lesson:** directions written in PHASE3B_NOTES are not authoritative on factual matters; verify against actual data before encoding.

**Design lessons from validation work:**

1. **Spec-source fix in the replay harness was essential.** Initial replay used `q["spec"]` (frozen at run time, must_not_contain=[]) rather than current specs from `eval/benchmarks.py`. This made all item-12 changes invisible to retrospective validation. Fix: load current specs keyed by qid; the historical raw.json provides only response_text and trace. Future framework iterations that change benchmark config (must_contain, expected_answer, decline phrases, etc.) MUST use this pattern — otherwise the validation answers a question we don't care about ("how would historical specs evaluate today's responses?") instead of the one we do ("how would today's specs evaluate historical responses?").

2. **Retrospective coverage of pre-fix behavior surfaces 3 fails the original 6-fail hypothesis missed.** Final expected-fails list = 9 = 5 item-12 hits + 1 item-11 SQL-scalar bug + 3 pre-existing fails (082219:Q4 and 084228:Q4 trace_no_errors from alias bugs during Phase 3B Step 1 prompt iteration; 081224:Q10 must_not_contain "baseball-reference.com" hit). The pre-existing fails aren't actionable — all are records of pre-fix behavior we've since addressed via prompt iterations. But the framework now retrospectively confirms the prompt iteration path delivered what it claimed; the trace_no_errors fails on Q4 vanish in post-Step-1 runs.

3. **Defensive variants cost nothing.** "Colorado vs. Colorado", "vs Colorado (home)", "16 World Series home runs" are re-orderings/punctuation-variants of the observed forms; they didn't fire on any historical run but cost nothing to encode and provide cheap defense if those phrasings emerge.

**Original observation (preserved for context):** Q4's "Colorado vs Colorado" hallucinations were caught only by manual review. Earlier observation in this session: "framework grows specificity through use."

## 13. Threshold-surfacing check for process_check questions

**RESOLVED 2026-05-03 (Phase 3B framework v1.5):** Added `check_threshold_surfaced` to `eval/checks.py`. Skips unless `expected_behavior == "surface_threshold_and_list_leaders"` (Q3 only at present). PASSes if response contains either a threshold keyword (`minimum`, `min.`, `at least`, `cutoff`, `for players with`, `qualifying`) or a numeric-with-unit phrase (`\d+\+?\s*(PA|AB|IP|innings?|games?)`). FAIL surfaces the response opening for manual review.

Validated against all 9 historical runs (8 pre-today + the 2026-05-03_093717 fresh run from item 12 work) via `scratch/replay_historical_evals.py --check check_threshold_surfaced`: 9 Q3s all PASS via the keyword recognizer (every Q3 used either `(min. N XX)` or `(minimum N XX)`); 81 non-Q3 question-runs all SKIP via the expected_behavior gate. Zero unexpected verdicts. Fresh eval at `eval/results/2026-05-03_095609/`: 7 pass / 0 fail / 3 review_needed (identical structure to baseline `_064708/` and the item-12 fresh run `_093717/`); Q3 passes the new check via `'min.'` keyword.

**Design notes:**

1. **`"min."` and `"minimum"` are distinct substring matches.** The four-character `"min."` (with period) does not appear within `"minimum"` (which is `m-i-n-i-m-u-m`, no period). All historical Q3 responses use one form or the other; both must be in the keyword list.

2. **Numeric-with-unit recognizer is forward-compat cover.** Every observed Q3 response surfaces the threshold via `(min. N XX)` prose, so the keyword path always fires first. The numeric path catches future short-form responses like `"Olerud led at 150+ AB"` that omit the keyword. Cost: if a future leaderboard prose like `"Players with 150 AB or more..."` lacks any keyword, the regex still matches `"150 AB"`.

3. **No false-positive risk on table data.** Q3 leaderboard tables put unit headers in one row (`| PA |`) and digits in data rows (`| 182 |`); never adjacent. Regex `\d+\s*PA` only fires on prose like `"75 PA"`.

4. **Fail mode coverage.** The check catches dynamism-principle-1 violations where the response presents a leaderboard with no threshold prose at all (the failure shape originally observed in early Q3 testing). It does not catch failure mode 2 (unconventional threshold values like 75 PA instead of round-number 150 PA) — that's item 10's territory and is already addressed in the prompt's "Threshold choice for minimum-volume queries" bullet.

## 14. Recoverable SQL errors and framework signal

**RESOLVED 2026-05-03 (Phase 3B framework v1.5, design decision):** Framework stays in strict mode on `trace_no_errors`. Any `run_sql` error in a trace flags the question as fail, regardless of whether the agent self-corrected on retry. No code change — the framework already operates this way; this entry locks the design choice.

**Reasoning.** The framework's purpose is to signal correctness for prompt iteration, not to assess whether the agent ultimately produced an acceptable user-facing response. Recovery is persistence, not quality — an agent that succeeds via retry has surfaced a prompt-tightening opportunity (the failed first query reveals a gap in the agent's planning context that the prompt should close). Treating recovered errors as passes hides those opportunities. The "automated fail, behavioral win" asymmetry is informative, not noise.

**Alternatives considered and rejected.**

1. **Lenient mode** — distinguish "agent failed to recover" from "agent recovered cleanly," only failing the former. Rejected because it conflates "worked eventually" with "worked correctly." Recovery doesn't validate the original behavior; it just shows the agent kept trying. Lenient mode masks genuine quality issues by accepting successful retries as primary successes.

2. **Two-axis tracking** — keep strict pass/fail on `trace_no_errors` but add a separate `recovery_rate` metric capturing how often errors led to a corrected retry. Rejected for v1.5 because it's substantial engineering work (new metric type in evaluate(), separate column in raw.json, new aggregation in report.md) for marginal behavioral change. Path of least surprise: revisit if the framework grows beyond binary pass/fail in some future iteration.

**Acknowledged trade-off.** Some traces will report "automated fail, behavioral win" — e.g., Q4 in `eval/results/2026-05-02_084228/` where the agent hit `opp.nick` (column-name truncation from the SELECT alias `opp_nick`), self-corrected in one retry, and produced a fully correct final response. Manual review distinguishes this from "automated fail, behavioral fail." Cost: interpretation overhead on every flagged trace. Benefit: signal integrity — the prompt iteration loop sees every error class.

**Future revisit trigger.** If eval runs start producing many "automated fail, behavioral win" cases (rule of thumb: >20% of fails turning out to be clean recoveries on manual review), the noise might justify revisiting alternative 1 or 2. For now: monitor. The retrospective coverage now provided by `scratch/replay_historical_evals.py` makes it cheap to reassess this decision against any future run.

---

**Phase 3B watch items (2026-05-03).** Items 15-17 surfaced during item 6 verification at `eval/results/2026-05-03_064708/` and `scratch/spot_check_item6.py`. Item 18 added on Phase 3B closure as the close-to-watch-list pointer for item 3. None are active failures; tracked for future iterations.

## 15. Q4 ballpark-names-from-training pattern (WATCH)

**Observed:** At `eval/results/2026-05-03_064708/` Q4 (1998 cycles), the agent's response includes ballpark names — "Comiskey Park" for the Blowers cycle at CHA199805180, "Coors Field" for both Bichette and Perez cycles at COL games. The SQL joined `games`, `players`, and `plays` but NOT `retro.ballparks`. Ballpark names are correct (Comiskey Park was the era-correct name, renamed U.S. Cellular Field in 2003), but sourced from training knowledge, not the database.

**Direction:** Same shape as items 1/8/9 (narrative-fabrication concern), narrowed to ballpark names. Item 12's gotcha (`ballparks.name` multi-name with `;` separator, era-dependent display) is not exercised because the agent doesn't query the table. Watch only — single-run observation, names happen to be correct. If pattern persists across runs, add an explicit "if a ballpark name appears in the response, query `retro.ballparks` for it" rule analogous to the team-code JOIN pattern in Useful patterns.

## 16. Item 16 (starttime multi-format) untested by current eval data (WATCH)

**Observed:** At `scratch/spot_check_item6.py` Spot 3 (1998 WS Game 1 start time), the starttime value retrieved was `'8:00'` — clean modern HH:MM format. The multi-format gotcha in CLAUDE.md §4 item 16 (`'H:MMPM'` and `'0.5833...'` Excel-fraction encodings) was not materially exercised because no 1940s-era starttime appeared in the queried data. The agent's query worked correctly for this specific question; whether the gotcha-section prose actually changes behavior on a malformed-format row remains unverified.

**Direction:** The CLAUDE.md §4 item 16 prose is in the prompt and would presumably guide handling, but until an eval question targets a 1940s game (or a row known to use Excel-fraction encoding), there's no behavioral evidence. Future eval expansion should include at least one pre-1950 game-time question.

**Naming-collision note:** PHASE3B_NOTES item 16 (this entry) and CLAUDE.md §4 item 16 (the gotcha being discussed) share a number by coincidence — item-number namespaces are independent across the two files.

## 17. gametype value-vocabulary discovery overhead (WATCH)

**Observed:** At `scratch/spot_check_item6.py` Spot 3, the agent's first SQL used `WHERE gametype = 'WS'` for the 1998 World Series Game 1 question — returned 0 rows. The agent then ran a meta-query (`SELECT DISTINCT gametype FROM retro.games WHERE EXTRACT(YEAR FROM date) = 1998`) to discover the canonical value is `'worldseries'`, then re-queried with the corrected filter. Result was correct (8:00 PM) but cost two extra round-trips.

**Direction:** Self-correction worked; this isn't a failure mode. But the prompt's `gametype` mentions are in passing references — there's no explicit list of canonical values. If this pattern recurs, add a one-line list to the `retro.games` row of the Tables section: e.g., `gametype` values: `'regular'`, `'worldseries'`, `'lcs'`, `'divisionseries'`, `'playoff'`, `'allstar'`, `'exhibition'`. Low priority — single-run observation, agent recovered without manual intervention.

## 18. Item 3 (era-disambiguation team rule partially ignored) — stale evidence, watch only

**Observed:** Phase 3A Step 3 manual testing 2026-04-30. Asked about Washington in the 1920s; agent led with WS1 (AL Senators) correctly but omitted the closing line about Negro League Washington teams that the prompt's example explicitly demonstrates. See item 3 above for full context.

**Status:** Closed-to-watch-list on 2026-05-03 as stale evidence — no verbatim artifact preserved, no eval-framework reproduction (no Washington-era-disambiguation question in `eval/benchmarks.py`), prompt has changed substantially across Phase 3B Steps 1-4 + framework v1.5 since the observation. No rule-conflict basis analogous to item 4 was identified.

**Reopen trigger:** any eval-framework or manual-testing observation of the same shape — agent identifies the era-ambiguous-team pattern, picks the dominant franchise correctly, but omits the alternatives-mention closing line. If reopened, consider whether to (a) tighten the rule with a mandatory closing line, (b) accept the omission as judgment-call territory, or (c) audit for a Dynamism-vs-disambiguation rule conflict similar to item 4. The right approach depends on whether the agent's choice to skip alternatives in the new run is contextually defensible.

## 19. Framework: Unicode dash normalization in expected_answer/must_contain checks

**RESOLVED 2026-05-03 (Phase 3B closure):** Added `_normalize_dashes` helper to `eval/checks.py` mapping U+2013 en-dash, U+2014 em-dash, and U+2212 minus sign to ASCII hyphen. Applied in both `check_expected_answer` and `check_must_contain` on both sides of the substring comparison.

**Discovery:** at `eval/results/2026-05-03_105219/`, Q5 (1998 Yankees record) failed `expected_answer` because the agent wrote `**114–48**` with U+2013 en-dash and the spec's expected_answer `"114-48"` uses ASCII hyphen. The factual answer was correct; the framework's substring check just doesn't normalize Unicode dash variants. This was the first time across 11 eval runs that the agent picked an en-dash for score notation (verified at `_064708/` and `_095609/` where Q5 used a hyphen and passed) — stochastic phrasing variation. The fix prevents the same false-positive on any future run where the agent picks a Unicode dash for score, year-range, or date-range strings.

**Scope intentionally narrow — dashes only.** Did not normalize other Unicode variants (fancy quotes U+2018-U+201D, ellipsis U+2026, NBSP U+00A0, etc.). Reasoning: dashes are visually equivalent and carry no semantic distinction in score/year/date contexts; quotes and other punctuation may carry semantic weight in some contexts (e.g. distinguishing direct-quote attribution). If similar false-positives surface for other Unicode variants, extend the helper at that point — additive change, no need to over-engineer now.

**Not extended to `check_must_not_contain`.** Reasoning: must_not_contain catches specific hallucinated phrases; the existing pattern (item 12) handles variants by adding multiple must_not_contain entries. Dash-normalization there is plausibly safe (current entries' hyphens are all ASCII; only Q10's "baseball-reference" / "fangraphs" hyphens would interact at all), but the user-defined scope was deliberately two checks. Extending to must_not_contain would be a one-line additive change if a future false-negative (hallucination not caught due to variant dash) is observed.

**Verification at `eval/results/2026-05-03_111550/`:** 6 pass / 1 fail / 3 review_needed. Q5 dash normalization confirmed (passes via `_normalize_dashes` — was the targeted fix). Q4 ran clean SQL this stochastic run (no recovered errors, so `trace_no_errors` didn't fire — positive surprise, item 14's strict-mode behavior was just dormant this run). Q7 surfaced as new framework signal pattern (must_contain on subject names — tracked as item 20).

## 20. Framework: must_contain on subject names produces stochastic false-positives (WATCH)

**Observed:** at `eval/results/2026-05-03_111550/`, Q7 (Hank Aaron career HRs) failed `must_contain` — missing substring `'aaron'`. Response was factually correct and well-formed:

> "**755 regular-season home runs** — the iconic total that stood as the all-time record from 1974 until Barry Bonds passed it in 2007. Add in postseason play and it climbs to 763. But 755 is the number everyone knows, and the data confirms it perfectly."

The agent answered the question accurately but never restated the subject's name (no "Aaron", no "Hank"). The `expected_answer` check passed; the `sql_scalar_matches_answer` check passed. The fail came solely from the subject-name substring requirement.

**Pattern:** for verifiable single-subject questions, `must_contain` entries that require the subject's name (e.g., "aaron", "ruth", "jeter") are functionally stylistic checks rather than correctness checks. The factual-correctness pair (`expected_answer` + `sql_scalar_matches_answer`) already validates the substantive answer. The subject-name requirement is a heuristic that mostly works because the agent usually restates the subject in its first sentence — but it produces false-positives when the agent assumes the named subject is implied by the question and skips restating it.

**Diagnosis — not a regression from Phase 3B closure work.** Step 1 (disambiguation rule rewrite) targets multi-match handling and doesn't influence subject restatement; Q7's `lookup_player` yields exactly one match. Step 2 (dash normalization) is in `eval/checks.py`, not in the agent prompt. The Q7 response is stochastic phrasing variation — across the 11 prior eval runs, Q7 has consistently restated "Aaron" in the response opening; this run is the first observed miss.

**Reopen/action trigger:** if the pattern recurs across multiple runs OR surfaces on the other single-subject verifiable questions (Q1 jeter, Q5 yankees, Q6 ruth, Q8 bonds, Q9 ichiro), consider softening the affected `must_contain` entries to drop the subject-name requirement and let `expected_answer` + `sql_scalar_matches_answer` carry the correctness load. The fix is a per-spec edit in `eval/benchmarks.py`, ~5 minutes per spec.

**Deliberately not acting now.** Discipline of "encode framework changes based on observed patterns, not anticipated ones" — a single observation across 12 eval runs is below the threshold for changing 6 spec entries preemptively. The current Q7 fail is informative noise; if the next 2-3 runs all pass cleanly, this stays a watch item; if they recur, soften then. Premature softening also has a real cost: it removes the framework's signal that the agent is restating subjects, which is mild stylistic guidance worth keeping if the cost is low.

## 21. Fabricated stats in stat-bullet example may model fabrication (WATCH)

**Observed:** the stat-question disambiguation bullet at `agent/prompts.py:359-361` uses "Ken Griffey Sr. hit 14; Ken Griffey Jr. hit 22" as its illustrative example for the multi-answer-in-one-response pattern. The numbers are not factual stats from any specific Retrosheet query — Sr.'s 1990 May HR total (the most natural reading of "hit 14") is not 14, and the example was constructed for shape rather than fact. The example is labeled as illustrative by context, but per item 4's `LEARNINGS.md` companion entry "Examples in prompts are sticky," agents reading prompts treat examples as templates rather than as labeled illustrations. A fabricated stat in an example carries some risk of modeling fabrication behavior in production responses.

**Why it matters:** the principle from `LEARNINGS.md` "Examples in prompts are sticky" — examples have two failure modes: factually wrong examples can model fact-fabrication, and structurally specific examples can over-template the response shape. The narrative-bullet example was already refined during Phase 3B closure (item 4) to swap specifics for patterns specifically because of this concern. The stat-bullet example was not similarly refined because the `LEARNINGS.md` entry's drafting process is what surfaced the parallel issue.

**Defense-in-depth context:** the upstream "## Trusting the data" section is authoritative on actual fact-sourcing — every numeric claim must come from a query the agent ran this turn. The fabrication-modeling risk from the stat-bullet example is mitigated by that section, not eliminated. Defense-in-depth on the example is cheap (replace fabricated numbers with verified Retrosheet stats from a real query, e.g., Griffey Sr.'s actual 1990 HR total of 8 and Jr.'s 22 — both rate-checkable against the corpus); the cost of a hidden fabrication-modeling failure mode is real if it ever surfaces.

**Reopen/action trigger:** if a future eval run or manual test surfaces a response where the agent fabricates a number that traces back to mimicking the stat-bullet example shape (the "Sr. hit X; Jr. hit Y" structure), prioritize replacing the example with verified stats. Otherwise, leave for future cleanup — the risk is theoretical until observed, and the existing "Trusting the data" upstream rule is the authoritative line of defense.

**Discovery path:** surfaced 2026-05-03 while drafting `LEARNINGS.md` entry 4 ("Examples in prompts are sticky"). The act of formalizing the pattern made the parallel observation about the still-existing fabricated stat-bullet example visible — a real example of LEARNINGS.md drafting generating new project-state observations.
