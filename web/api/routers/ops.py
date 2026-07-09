"""Ops endpoints — pipeline schedule/run-status dashboard.

Serves the snapshot built by ``scripts/build_pipeline_status.py`` (committed
6-hourly by the freshness-monitor workflow). The Space has no GitHub
credentials, so this is a read-the-committed-file pattern, same as the rest
of the data surface.

    GET /api/ops/pipeline-status   -> JSON document
    GET /api/ops/dashboard         -> self-contained HTML dashboard
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops", tags=["ops"])

_DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
STATUS_PATH = _DATA_ROOT / "ops" / "pipeline_status.json"


def _load_status() -> Dict[str, Any]:
    if not STATUS_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "pipeline_status.json not found — the freshness-monitor "
                "workflow has not committed a snapshot yet"
            ),
        )
    try:
        payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"unreadable status file: {exc}")

    # Staleness flag: the builder runs every 6 hours; >13h means two
    # consecutive builder runs were missed — itself an ops signal.
    try:
        generated = datetime.fromisoformat(payload.get("generated_at", ""))
        age_h = (datetime.now(timezone.utc) - generated).total_seconds() / 3600
        payload["age_hours"] = round(age_h, 1)
        payload["is_stale"] = age_h > 13
    except ValueError:
        payload["age_hours"] = None
        payload["is_stale"] = True
    return payload


@router.get("/pipeline-status")
def pipeline_status() -> Dict[str, Any]:
    """Return the latest pipeline-status snapshot with staleness metadata."""
    return _load_status()


_DASHBOARD_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Pipeline Status</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font-family:-apple-system,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;
      margin:0;padding:32px;}
 h1{font-size:20px;margin:0 0 4px;} .sub{color:#94a3b8;font-size:13px;margin-bottom:24px;}
 table{border-collapse:collapse;width:100%;max-width:1100px;}
 th{ text-align:left;font-size:11px;letter-spacing:1px;color:#94a3b8;padding:8px 12px;
     border-bottom:1px solid #334155;text-transform:uppercase;}
 td{padding:10px 12px;border-bottom:1px solid #1e293b;font-size:14px;vertical-align:middle;}
 .name{font-weight:600;} .purpose{color:#94a3b8;font-size:12px;}
 .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:3px;}
 .success{background:#22c55e;} .failure{background:#ef4444;} .other{background:#64748b;}
 .badge{padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;}
 .b-success{background:#052e16;color:#4ade80;} .b-failure{background:#450a0a;color:#f87171;}
 .b-running{background:#172554;color:#93c5fd;} .b-none{background:#1e293b;color:#94a3b8;}
 a{color:#93c5fd;text-decoration:none;} .stale{color:#fbbf24;}
</style></head><body>
<h1>Pipeline Status</h1>
<div class="sub" id="meta">loading…</div>
<table id="tbl"><thead><tr>
 <th>Workflow</th><th>Schedule</th><th>Last run</th><th>When</th>
 <th>Duration</th><th>Recent (new → old)</th><th>Success</th>
</tr></thead><tbody></tbody></table>
<script>
function rel(iso){if(!iso)return "—";const s=(Date.now()-new Date(iso))/1e3;
 if(s<3600)return Math.round(s/60)+"m ago";if(s<86400)return (s/3600).toFixed(1)+"h ago";
 return (s/86400).toFixed(1)+"d ago";}
function dur(x){return x==null?"—":(x<90?x+"s":Math.round(x/60)+"m");}
fetch("/api/ops/pipeline-status")
 .then(r=>{if(!r.ok)throw new Error("HTTP "+r.status);return r.json()})
 .then(d=>{
  document.getElementById("meta").innerHTML=
   "generated "+rel(d.generated_at)+" · repo "+d.repo+
   (d.is_stale?' · <span class="stale">STALE — builder has missed runs</span>':"");
  const tb=document.querySelector("#tbl tbody");
  d.workflows.forEach(w=>{
   const lr=w.last_run;
   let badge='<span class="badge b-none">no runs</span>';
   if(lr){
    if(lr.status!=="completed")badge='<span class="badge b-running">'+lr.status+'</span>';
    else if(lr.conclusion==="success")badge='<span class="badge b-success">success</span>';
    else badge='<span class="badge b-failure">'+(lr.conclusion||"?")+'</span>';
   }
   const dots=(w.recent||[]).map(c=>'<span class="dot '+
    (c==="success"?"success":(c==="failure"?"failure":"other"))+'" title="'+c+'"></span>').join("");
   const rate=w.success_rate==null?"—":Math.round(w.success_rate*100)+"%";
   tb.insertAdjacentHTML("beforeend",
    "<tr><td><div class='name'>"+w.name+"</div><div class='purpose'>"+w.purpose+"</div></td>"+
    "<td>"+w.schedule+"</td>"+
    "<td>"+(lr&&lr.html_url?("<a href='"+lr.html_url+"' target='_blank'>"+
     badge+"</a>"):badge)+"</td>"+
    "<td>"+rel(lr&&lr.started_at)+"</td><td>"+dur(lr&&lr.duration_seconds)+"</td>"+
    "<td>"+dots+"</td><td>"+rate+"</td></tr>");
  });
 }).catch(e=>{document.getElementById("meta").textContent="Could not load status: "+e;});
</script></body></html>"""


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    """Self-contained HTML dashboard rendering /api/ops/pipeline-status."""
    return _DASHBOARD_HTML
