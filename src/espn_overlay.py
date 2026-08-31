"""In-room overlay for the ESPN draft co-pilot.

The 2026-08-31 mock exposed the co-pilot's real ergonomic failure: the board
lives in a terminal, but the operator is looking at the draft room with a
30-second clock. Relaying picks by hand lost two of them. This paints the
advisor's ranked board directly onto the ESPN page, refreshed only when a new
pick lands, so the operator reads it in place instead of switching windows.

Deliberately dependency-free and click-through (``pointer-events:none``) — an
overlay that swallows clicks on ESPN's own controls is worse than no overlay.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

OVERLAY_ID = "giq-board"

_JS = """
(function(){
  var ID=%s, HTML=%s;
  function build(){
    var old=document.getElementById(ID); if(old) old.remove();
    var d=document.createElement('div'); d.id=ID;
    d.style.cssText='position:fixed;top:8px;right:8px;z-index:2147483647;'+
      'background:rgba(11,18,32,.96);color:#e8eef9;font:13px/1.35 -apple-system,Segoe UI,sans-serif;'+
      'border:2px solid #4ade80;border-radius:10px;padding:10px 12px;min-width:270px;max-width:330px;'+
      'max-height:92vh;overflow:auto;box-shadow:0 8px 30px rgba(0,0,0,.6);pointer-events:none';
    d.innerHTML=HTML;
    document.body.appendChild(d);
  }
  build();
  // ESPN's SPA re-renders wipe injected nodes; keep it alive without re-running
  // the whole push from Python every cycle.
  if(window.__giqTimer) clearInterval(window.__giqTimer);
  window.__giqTimer=setInterval(function(){ if(!document.getElementById(ID)) build(); },1000);
  return 'ok';
})()
"""


def _esc(s: Any) -> str:
    """Escape for HTML, but keep literal ``<br>`` as a line break.

    Notes are two-line by design (market row, then decision row), so the one
    tag we intentionally emit survives escaping.
    """
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("&lt;br&gt;", "<br>")
    )


def build_html(header: str, rows: Sequence[Dict[str, Any]], footer: str = "") -> str:
    """Render the overlay's inner HTML.

    Args:
        header: Title line (e.g. ``"PICK 34 — take highest available"``).
        rows: Ordered entries; each may carry ``name``, ``pos``, ``note`` and a
            truthy ``dim`` to grey the line out (used for section separators).
        footer: Optional small print under the list.

    Returns:
        HTML string for the overlay body.
    """
    html = (
        "<div style='font-weight:700;color:#4ade80;margin-bottom:6px'>%s</div>"
        % _esc(header)
    )
    n = 0
    for row in rows:
        note = _esc(row.get("note", ""))
        if row.get("dim"):
            html += (
                "<div style='padding:4px 0;color:#64748b;font-size:11px;"
                "border-top:1px solid #1e293b;margin-top:4px'>%s %s</div>"
                % (_esc(row.get("name", "")), note)
            )
            continue
        n += 1
        html += (
            "<div style='padding:3px 0;border-bottom:1px solid #1e293b'>"
            "<b style='color:#fbbf24'>%d.</b> <b>%s</b> "
            "<span style='color:#7dd3fc'>%s</span><br>"
            "<span style='color:#94a3b8;font-size:11px;margin-left:14px'>%s</span></div>"
            % (n, _esc(row.get("name", "")), _esc(row.get("pos", "")), note)
        )
    if footer:
        html += (
            "<div style='margin-top:6px;font-size:11px;color:#94a3b8'>%s</div>"
            % _esc(footer)
        )
    return html


def rows_from_recs(
    recs: Sequence[Dict[str, Any]], limit: int = 10
) -> List[Dict[str, Any]]:
    """Turn advisor recommendation records into overlay rows.

    Keeps the note short on purpose — the operator is reading this on a clock,
    so it carries only what changes the pick: wait-cost, ADP, and any NEWS flag.
    """
    out: List[Dict[str, Any]] = []
    for r in list(recs)[:limit]:
        bits = []
        wait = r.get("wait_cost", r.get("cost_of_waiting"))
        if wait is not None:
            try:
                bits.append("wait %+.0f" % float(wait))
            except (TypeError, ValueError):
                pass
        adp = r.get("adp") if r.get("adp") is not None else r.get("adp_rank")
        if adp is not None:
            try:
                bits.append("ADP %d" % int(float(adp)))
            except (TypeError, ValueError):
                pass
        tier = r.get("tier") or r.get("value_tier")
        if tier:
            bits.append(str(tier).replace("_", " "))
        if r.get("news_risk"):
            bits.append("!" + str(r["news_risk"]).split()[0])
        out.append(
            {
                "name": r.get("player_name") or r.get("name") or "?",
                "pos": r.get("position", ""),
                "note": " · ".join(bits),
            }
        )
    return out


def push(
    page: Any, header: str, rows: Sequence[Dict[str, Any]], footer: str = ""
) -> bool:
    """Paint the overlay into the live draft room.

    Never raises: an overlay failure must not interrupt the co-pilot mid-draft.

    Args:
        page: Object exposing ``evaluate(expression)`` (``ChromeDraftPage``).
        header: Title line.
        rows: Ordered overlay rows.
        footer: Optional small print.

    Returns:
        True if the injection reported success.
    """
    try:
        js = _JS % (
            json.dumps(OVERLAY_ID),
            json.dumps(build_html(header, rows, footer)),
        )
        return page.evaluate(js) == "ok"
    except Exception:  # noqa: BLE001 - overlay is cosmetic; never break the draft
        return False


def clear(page: Any) -> bool:
    """Remove the overlay and stop its keep-alive timer."""
    try:
        page.evaluate(
            "(function(){if(window.__giqTimer)clearInterval(window.__giqTimer);"
            "var e=document.getElementById(%s);if(e)e.remove();return 'ok';})()"
            % json.dumps(OVERLAY_ID)
        )
        return True
    except Exception:  # noqa: BLE001
        return False


# --- Multi-source enrichment -------------------------------------------------
# The 08-31 mock showed the overlay needs to answer "why this name, and does the
# rest of the market agree?" in one glance: our rank, each platform's ADP, and
# any news flag. Loaded once at co-pilot start; missing files degrade to blanks
# rather than failing the draft.

_ADP_SOURCES = (
    ("ESPN", "data/adp/adp_espn_standard.csv"),
    ("FFC", "data/adp/adp_ffc_half_ppr.csv"),
    ("SLP", "data/adp/adp_sleeper_half_ppr.csv"),
)


def _key(name: str) -> str:
    import re as _re

    return _re.sub(r"[^a-z0-9]", "", str(name).lower())


def load_market_context(
    value_report_csv: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Build ``name_key -> {ours, ESPN, FFC, SLP, news}`` for overlay notes.

    Args:
        value_report_csv: Optional draft_value_report CSV supplying our VBD rank
            and news_risk. Falls back to ADP-only notes when absent.

    Returns:
        Mapping keyed by normalized player name; empty on any failure.
    """
    ctx: Dict[str, Dict[str, Any]] = {}
    try:
        import glob
        import os

        import pandas as pd

        for label, path in _ADP_SOURCES:
            match = sorted(glob.glob(path)) or sorted(
                glob.glob(path.replace(".csv", "_*.csv"))
            )
            if not match:
                continue
            df = pd.read_csv(match[-1])
            namecol = next(
                (c for c in ("player_name", "name", "player") if c in df.columns), None
            )
            rankcol = next(
                (
                    c
                    for c in ("adp_rank", "overall_rank", "adp", "rank")
                    if c in df.columns
                ),
                None,
            )
            if not namecol or not rankcol:
                continue
            for _, r in df.iterrows():
                k = _key(r[namecol])
                if not k:
                    continue
                try:
                    ctx.setdefault(k, {})[label] = int(float(r[rankcol]))
                except (TypeError, ValueError):
                    pass

        if value_report_csv is None:
            reports = sorted(glob.glob("output/draft_reports/value_report_*.csv"))
            value_report_csv = reports[-1] if reports else None
        if value_report_csv and os.path.exists(value_report_csv):
            vr = pd.read_csv(value_report_csv)
            for _, r in vr.iterrows():
                k = _key(r.get("player_name", ""))
                if not k:
                    continue
                slot = ctx.setdefault(k, {})
                if pd.notna(r.get("vbd_rank")):
                    slot["ours"] = int(float(r["vbd_rank"]))
                if isinstance(r.get("news_risk"), str) and r["news_risk"].strip():
                    slot["news"] = r["news_risk"].split()[0]
    except Exception:  # noqa: BLE001 - notes are cosmetic
        return ctx
    return ctx


def rows_from_recs_enriched(
    recs: Sequence[Dict[str, Any]],
    market: Optional[Dict[str, Dict[str, Any]]] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Overlay rows carrying our rank, per-platform ADP, and news in the note."""
    market = market or {}
    out: List[Dict[str, Any]] = []
    for r in list(recs)[:limit]:
        name = r.get("player_name") or r.get("name") or "?"
        m = market.get(_key(name), {})
        line1 = []
        if m.get("ours") is not None:
            line1.append("ours #%s" % m["ours"])
        for label, _ in _ADP_SOURCES:
            if m.get(label) is not None:
                line1.append("%s %s" % (label, m[label]))
        line2 = []
        wait = r.get("wait_cost", r.get("cost_of_waiting"))
        if wait is not None:
            try:
                line2.append("wait %+.0f" % float(wait))
            except (TypeError, ValueError):
                pass
        tier = r.get("tier") or r.get("value_tier")
        if tier:
            line2.append(str(tier).replace("_", " "))
        news = m.get("news") or r.get("news_risk")
        if news:
            line2.append("!" + str(news).split()[0])
        note = " · ".join(line1)
        if line2:
            note += ("<br>" if note else "") + " · ".join(line2)
        out.append({"name": name, "pos": r.get("position", ""), "note": note})
    return out


def outstanding_positions(reasoning: str) -> List[str]:
    """Positions the engine still lists as unfilled starters, from its reasoning.

    The engine appends e.g. ``"§0 starters first: QB1/TE1 outstanding"``; that
    is the authority on what MUST still be filled.
    """
    import re as _re

    m = _re.search(
        r"starters first:\s*([A-Z0-9/]+)\s+outstanding", str(reasoning or "")
    )
    if not m:
        return []
    return [_re.sub(r"\d+$", "", p) for p in m.group(1).split("/") if p]


def diversify(
    recs: Sequence[Dict[str, Any]],
    per_position: int = 2,
    limit: int = 8,
    reasoning: str = "",
    current_pick: Optional[int] = None,
    steal_gap: int = 18,
) -> List[Dict[str, Any]]:
    """Reorder recommendations so the overlay shows real ALTERNATIVES.

    The engine sorts purely by cost-of-waiting, which at some picks returns a
    single position for every slot (all 8 recs were TEs at pick 82 of the
    2026-08-31 mock, all QBs at pick 90). On a 30-second clock the operator
    needs a few genuinely different options, not one position ranked ten deep.

    Keeps the engine's ranking as the primary order, but caps how many of one
    position appear before another position gets a turn.

    Args:
        recs: Recommendation records, best first.
        per_position: Max entries per position in the first pass.
        limit: Total rows to return.

    Returns:
        Reordered records, best-first within the diversity constraint.
    """
    # STEALS FIRST. A player sitting far past his ADP (Ja'Marr Chase still on
    # the board at pick 60) outranks both positional need and diversity — take
    # the value, sort the roster out later. Pinned to the top, exempt from the
    # per-position cap, and never crowded out by the interleave below.
    steals: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for r in recs:
        adp = r.get("adp") if r.get("adp") is not None else r.get("adp_rank")
        try:
            gap = float(current_pick) - float(adp) if (current_pick and adp) else 0.0
        except (TypeError, ValueError):
            gap = 0.0
        (steals if gap >= steal_gap else rest).append(r)

    def _adp(r: Dict[str, Any]) -> float:
        try:
            return float(
                r.get("adp") if r.get("adp") is not None else r.get("adp_rank")
            )
        except (TypeError, ValueError):
            return float("inf")

    steals.sort(key=_adp)  # earliest ADP = biggest steal, first
    if steals:
        return (steals + rest)[:limit]
    recs = rest

    # A single outstanding starter is a FORCED need (round 14, still no QB):
    # showing alternatives at other positions would be actively misleading, so
    # leave the engine's depth-at-one-position ranking alone.
    if len(outstanding_positions(reasoning)) == 1:
        return list(recs)[:limit]
    seen: Dict[str, int] = {}
    primary: List[Dict[str, Any]] = []
    overflow: List[Dict[str, Any]] = []
    for r in recs:
        pos = str(r.get("position", "") or "?")
        seen[pos] = seen.get(pos, 0) + 1
        (primary if seen[pos] <= per_position else overflow).append(r)
    return (primary + overflow)[:limit]
