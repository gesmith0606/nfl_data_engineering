"""Unit tests for src/waiver_sanity.

Gold projections have had a sanity gate since v7.0; waiver advice never did,
so every bad recommendation this season was caught by the user reading the
report. Each check below is one of those corrections, turned into something
that fails loudly instead. The tests prove each one actually fires.
"""

from __future__ import annotations

from src.waiver_sanity import (
    CRITICAL,
    WARN,
    check_report,
    parse_roster,
    parse_rows,
    summarise,
)

HEADER = (
    "=== LEAGUE — me — 2026 week 7 waivers ===\n"
    "OURS = weekly Gold projections_half_ppr_20261022_221035.parquet (2h old)\n"
)
MECHANICS = (
    "-- Roster mechanics --\n"
    "  active 17/18 (1 open — a claim needs a drop when 0) | IR 3/5 | taxi 3/3\n"
    "  IR accepts: IR\n"
)


def _report(rows, header=HEADER, mechanics=MECHANICS):
    body = "-- RB free agents --\n" + "".join(rows)
    return header + mechanics + body


def _row(name, pos, team, tail):
    return f"        {name:24} {pos:3}{team:4} {tail}\n"


GOOD = _row("Kendre Miller", "RB", "NO", "BENCH+  BID $7 [unclaimed]")


# --- parsing -----------------------------------------------------------------


def test_parses_name_position_team_and_tail():
    rows = parse_rows(_report([GOOD]))
    assert len(rows) == 1
    r = rows[0]
    assert (r.name, r.pos, r.team) == ("Kendre Miller", "RB", "NO")
    assert r.bid == 7
    assert r.verdict == "BENCH+"
    assert r.ending is False


def test_an_empty_report_is_critical_not_silently_fine():
    findings = check_report(HEADER + MECHANICS)
    assert findings[0].level == CRITICAL
    assert findings[0].check == "rows"


# --- each invariant is a correction that had to be made by hand -------------


def test_a_player_on_bye_is_never_a_recommendation():
    rows = [_row("Khalil Shakir", "WR", "BUF", "STARTS  BID $5 [unclaimed]")]
    f = check_report(_report(rows), bye_teams=["BUF"])
    assert any(x.check == "bye" and x.level == CRITICAL for x in f)


def test_a_bye_player_rated_no_help_is_not_flagged():
    rows = [_row("Khalil Shakir", "WR", "BUF", "no help BID $1 [unclaimed]")]
    f = check_report(_report(rows), bye_teams=["BUF"])
    assert not any(x.check == "bye" for x in f)


def test_paying_for_a_role_that_is_ending_is_critical():
    """The Daniels case: his starter was due back and the bid was $8."""
    rows = [
        _row(
            "Jalon Daniels",
            "QB",
            "TB",
            "no help BID $8 [cut wk4 (was $1)] ENDING<-Baker Mayfield(returning)",
        )
    ]
    f = check_report(_report(rows))
    assert any(x.check == "ending-role" and x.level == CRITICAL for x in f)


def test_a_dollar_on_an_ending_role_is_allowed():
    rows = [
        _row("Jalon Daniels", "QB", "TB", "no help BID $1 [x] ENDING<-Baker(returning)")
    ]
    assert not any(x.check == "ending-role" for x in check_report(_report(rows)))


def test_a_bid_over_a_quarter_of_the_budget_is_critical():
    """Kendre Miller at $55 of $392 was over the cap and lost anyway."""
    rows = [_row("Kendre Miller", "RB", "NO", "BENCH+ BID $55 [unclaimed]")]
    f = check_report(_report(rows), faab_left=200)
    assert any(x.check == "faab-cap" and x.level == CRITICAL for x in f)


def test_a_bid_above_the_room_record_is_critical():
    rows = [_row("Someone", "RB", "NO", "BENCH+ BID $500 [unclaimed]")]
    f = check_report(_report(rows), room_max_bid=450)
    assert any(x.check == "room-max" for x in f)


def test_bids_with_no_demand_history_are_critical():
    """Pricing with no [demand] bracket is the old median-guessing failure."""
    rows = [_row("Someone", "RB", "NO", "BENCH+ BID $12")]
    f = check_report(_report(rows))
    assert any(x.check == "no-demand" and x.level == CRITICAL for x in f)


def test_a_stale_board_warns():
    """A 26h-old board still had four starters projecting as healthy."""
    header = HEADER.replace("(2h old)", "(72h old)")
    f = check_report(_report([GOOD], header=header))
    assert any(x.check == "board-age" and x.level == WARN for x in f)


def test_a_missing_board_age_warns():
    f = check_report(_report([GOOD], header="=== LEAGUE ===\n"))
    assert any(x.check == "board-age" for x in f)


def test_missing_roster_mechanics_warns():
    """Without it, a drop gets recommended against rules the league does not have."""
    f = check_report(_report([GOOD], mechanics=""))
    assert any(x.check == "roster-mechanics" and x.level == WARN for x in f)


def test_ir_slots_without_their_rules_warns():
    mech = "-- Roster mechanics --\n  active 17/18 (1 open) | IR 3/5 | taxi 3/3\n"
    f = check_report(_report([GOOD], mechanics=mech))
    assert any(x.check == "ir-rules" for x in f)


# --- verdict -----------------------------------------------------------------


def test_a_clean_report_passes():
    f = check_report(
        _report([GOOD]), bye_teams=["BUF"], faab_left=380, room_max_bid=450
    )
    assert summarise(f)["passed"] is True
    assert summarise(f)["critical"] == 0


def test_any_critical_fails_the_gate():
    rows = [_row("X", "RB", "BUF", "STARTS BID $5 [unclaimed]")]
    assert summarise(check_report(_report(rows), bye_teams=["BUF"]))["passed"] is False


def test_findings_are_ordered_most_severe_first():
    rows = [_row("X", "RB", "BUF", "STARTS BID $5 [unclaimed]")]
    header = HEADER.replace("(2h old)", "(99h old)")
    f = check_report(_report(rows, header=header), bye_teams=["BUF"])
    assert f[0].level == CRITICAL
    assert f[-1].level == WARN


# --- rules the skill states that nothing used to enforce ---------------------


def test_paying_to_re_buy_a_player_we_cut_is_critical():
    """Week 7 2026 the model wanted $55 for Drew Lock, whom we cut for $55."""
    rows = [_row("Drew Lock", "QB", "SEA", "no help BID $55 [cut wk4 by US (was $55)]")]
    f = check_report(_report(rows), dynasty=True)
    assert any(x.check == "re-buy" and x.level == CRITICAL for x in f)


def test_a_minimum_bid_on_a_player_we_cut_is_allowed():
    rows = [_row("Drew Lock", "QB", "SEA", "no help BID $1 [cut wk4 by US (was $55)]")]
    assert not any(
        x.check == "re-buy" for x in check_report(_report(rows), dynasty=True)
    )


def test_someone_else_cutting_him_is_not_a_re_buy():
    rows = [_row("A Player", "QB", "SEA", "no help BID $9 [cut wk4 (was $55)]")]
    assert not any(
        x.check == "re-buy" for x in check_report(_report(rows), dynasty=True)
    )


def test_paying_for_a_no_help_player_is_critical_in_a_redraft_league():
    rows = [_row("Hot Guy", "WR", "NO", "no help BID $12 [unclaimed]")]
    f = check_report(_report(rows), dynasty=False)
    assert any(x.check == "no-help-priced" and x.level == CRITICAL for x in f)


def test_no_help_is_advisory_in_dynasty():
    """Jalon Daniels read 'no help' and was the correct Mantis add."""
    rows = [_row("Jalon Daniels", "QB", "TB", "no help BID $12 [unclaimed]")]
    assert not any(
        x.check == "no-help-priced" for x in check_report(_report(rows), dynasty=True)
    )


def test_a_starter_verdict_is_never_a_no_help_violation():
    rows = [_row("Real Add", "RB", "NO", "STARTS BID $20 [unclaimed]")]
    assert not any(
        x.check == "no-help-priced" for x in check_report(_report(rows), dynasty=False)
    )


def test_a_minimum_bid_on_a_no_help_player_is_allowed_in_redraft():
    """The model prices every unclaimed player; $1 is the honest refusal."""
    rows = [_row("Depth Guy", "TE", "PIT", "no help BID $1 [unclaimed]")]
    assert not any(
        x.check == "no-help-priced" for x in check_report(_report(rows), dynasty=False)
    )


def _roster(lines, drops):
    """A "My roster" block plus the drop-candidate line that follows it."""
    return (
        "\n-- My roster (weakest dynasty value first) --\n"
        + "".join(lines)
        + f"\n  Drop candidates (bench, keepers excluded, weakest first): {drops}\n"
    )


def _mine(tag, name, pos, team, tail):
    return f"  {tag:6}{name:24} {pos:3}{team:4} {tail}\n"


YOUNG = _mine("bench", "Jaylen Wright", "RB", "MIN", "adds   41k  dyn  820 age 23")
OLD = _mine("bench", "Mike Gesicki", "TE", "CIN", "adds    1k  dyn  310 age 30")
QUIET_YOUNG = _mine("bench", "Pat Bryant", "WR", "DEN", "adds    0k  dyn 1263 age 23")
STARTED = _mine("START", "DeMario Douglas", "WR", "NE", "adds    0k  dyn 1088 age 25")
FA = _row("Jahan Dotson", "WR", "ATL", "BENCH+ BID $7 [unclaimed] age 26")


def test_young_riser_is_not_a_drop_candidate_where_players_are_kept():
    """Skill Step 4: never drop a young player with a role path."""
    text = _report([FA]) + _roster([YOUNG, OLD], "Mike Gesicki, Jaylen Wright")
    for keeps in ({"dynasty": True}, {"keeper": True}):
        found = [f for f in check_report(text, **keeps) if f.check == "young-drop"]
        assert len(found) == 1 and "Jaylen Wright" in found[0].detail
        assert found[0].level == CRITICAL
    # A redraft league has no reason to protect him.
    assert not [f for f in check_report(text) if f.check == "young-drop"]


def test_young_player_nobody_is_adding_stays_droppable():
    """The role path is the signal — otherwise this fires every single week."""
    text = _report([FA]) + _roster([QUIET_YOUNG, OLD], "Pat Bryant, Mike Gesicki")
    assert not [f for f in check_report(text, dynasty=True) if f.check == "young-drop"]


def test_a_player_we_are_starting_is_never_a_drop_candidate():
    """The tag and the drop list used different starter sets (week 7, Douglas)."""
    text = _report([FA]) + _roster([STARTED, OLD], "Mike Gesicki, DeMario Douglas")
    for kw in ({}, {"dynasty": True}):
        found = [f for f in check_report(text, **kw) if f.check == "start-drop"]
        assert len(found) == 1 and "DeMario Douglas" in found[0].detail
        assert found[0].level == CRITICAL


def test_a_clean_drop_list_raises_nothing():
    text = _report([FA]) + _roster([OLD, QUIET_YOUNG], "Mike Gesicki, Pat Bryant")
    assert not [
        f
        for f in check_report(text, dynasty=True)
        if f.check in ("young-drop", "start-drop")
    ]


def test_no_drop_candidates_line_means_no_drop_findings():
    text = _report([FA]) + _roster([OLD], "none")
    assert not [
        f
        for f in check_report(text, dynasty=True)
        if f.check in ("young-drop", "start-drop")
    ]


NEWS_LINE = "NEWS = Gold sentiment, 13 flags for week 7\n"


def test_a_week_with_no_sentiment_flags_is_a_warning_not_a_silence():
    """The extractor no-ops to keyword rules while its cron still reports success."""
    rows = [_row("Jahan Dotson", "WR", "ATL", "BENCH+ BID $7 [unclaimed] age 26")]
    silent = _report(
        rows, header=HEADER + "NEWS = Gold sentiment, 0 flags for week 7\n"
    )
    found = [f for f in check_report(silent) if f.check == "news-source"]
    assert len(found) == 1 and found[0].level == WARN
    assert "fails open" in found[0].detail

    missing = _report(rows)
    assert [f.check for f in check_report(missing) if f.check == "news-source"]

    present = _report(rows, header=HEADER + NEWS_LINE)
    assert not [f for f in check_report(present) if f.check == "news-source"]


def test_espn_yahoo_line_format_still_yields_age_and_adds():
    """Those reports insert an `adp` column between adds and age (week 7, live)."""
    line = (
        "  bench Emeka Egbuka             WR TB   ours  7.7 slpr  8.7 "
        "blend  8.2 last 14.3 adds   99k adp32   age 24 wk7 report"
    )
    (r,) = parse_roster(line)
    assert (r.tag, r.pos, r.age, r.adds) == ("bench", "WR", 24, 99)


def test_partial_slot_accounting_satisfies_the_mechanics_checks():
    """ESPN/Yahoo cannot know IR rules, so they say so rather than printing nothing.

    Omitting the block entirely made both mechanics warnings fire every single
    week on those two leagues, which is a check that is really a platform note.
    """
    partial = (
        "-- Roster mechanics --\n"
        "  active 9/9 (0 open — a claim needs a drop when 0) | roster 15/16\n"
        "  IR accepts: unknown on espn — confirm on the site before using an "
        "IR slot (Step 4b)\n"
    )
    text = _report(
        [_row("Jahan Dotson", "WR", "ATL", "BENCH+ BID $7 [unclaimed] age 26")],
        header=HEADER + NEWS_LINE,
        mechanics=partial,
    )
    assert not [
        f for f in check_report(text) if f.check in ("roster-mechanics", "ir-rules")
    ]


def test_every_configured_rss_feed_has_a_distinct_live_looking_url():
    """Three of five feeds were 404/301 for months while the cron stayed green.

    This does not hit the network -- it pins the shape that let the rot hide:
    a feed list is only useful if each entry is a distinct host we still
    believe in, and `ingest_sentiment_rss.py` is what proves liveness (it now
    names dead feeds and exits non-zero when most of them are gone).
    """
    from src.config import SENTIMENT_CONFIG

    feeds = SENTIMENT_CONFIG["rss_feeds"]
    assert len(feeds) >= 4, "news coverage should not rest on two publishers"
    hosts = {url.split("/")[2] for url in feeds.values()}
    assert len(hosts) == len(feeds), f"duplicate publisher among {sorted(feeds)}"
    assert "www.nfl.com" not in hosts, "nfl.com no longer publishes RSS (404/301)"


class TestSourcesDisagree:
    """One source says he is inactive, the other says he starts.

    Week 8 2026: Tyler Huntley printed "ours 16.8 slpr 0.0 blend 8.4 ...
    BENCH+" and was recommended twice. Our engine had zeroed Lamar Jackson off
    a stale injury tag and promoted his backup; Sleeper carried no week-8
    projection for Huntley at all. The blend, 8.4, described nobody.
    """

    HUNTLEY = (
        "-- QB free agents --\n"
        "        Tyler Huntley            QB BAL  ours 16.8 slpr  0.0 blend  8.4"
        " last 16.1 adds    0k dyn 1055 age 28 BENCH+  BID $4 [unclaimed] \n"
    )

    def _findings(self, text, **kw):
        kw.setdefault("bye_teams", [])
        return [f for f in check_report(text, **kw) if f.check == "sources-disagree"]

    def test_flags_a_starter_verdict_when_one_source_says_inactive(self):
        found = self._findings(self.HUNTLEY)
        assert len(found) == 1
        assert found[0].level == "CRITICAL"
        assert "Tyler Huntley" in found[0].detail

    def test_ordinary_disagreement_is_not_flagged(self):
        """15.5 vs 18.2 is noise about degree, not about playing."""
        text = self.HUNTLEY.replace("ours 16.8 slpr  0.0", "ours 15.5 slpr 18.2")
        assert self._findings(text) == []

    def test_depth_verdict_is_not_flagged(self):
        """A depth add is not a claim that he starts, so the split is moot."""
        assert self._findings(self.HUNTLEY.replace("BENCH+ ", "depth  ")) == []

    def test_both_sources_low_is_not_flagged(self):
        text = self.HUNTLEY.replace("ours 16.8 slpr  0.0", "ours  0.4 slpr  0.0")
        assert self._findings(text) == []

    def test_missing_source_number_is_not_flagged(self):
        """ "-" means not scored, which is silence, not disagreement."""
        text = self.HUNTLEY.replace("ours 16.8 slpr  0.0", "ours    - slpr  0.0")
        assert self._findings(text) == []
