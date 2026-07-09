"""
Tests for the pipeline-status ops dashboard (builder script + API).
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_pipeline_status as bps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from web.api.main import app  # noqa: E402
from web.api.routers import ops  # noqa: E402

client = TestClient(app)


def _run(conclusion="success", status="completed", started="2026-07-09T09:00:00Z"):
    return {
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "run_started_at": started,
        "updated_at": "2026-07-09T09:07:30Z",
        "html_url": "https://github.com/x/y/actions/runs/1",
        "event": "schedule",
    }


class TestSummarizeRuns(unittest.TestCase):
    def test_empty_runs(self):
        out = bps.summarize_runs([])
        self.assertIsNone(out["last_run"])
        self.assertEqual(out["recent"], [])
        self.assertIsNone(out["success_rate"])

    def test_success_rate_over_completed_only(self):
        runs = [
            _run(status="in_progress"),
            _run("success"),
            _run("failure"),
            _run("success"),
        ]
        out = bps.summarize_runs(runs)
        self.assertAlmostEqual(out["success_rate"], 2 / 3, places=3)
        self.assertEqual(out["recent"][0], "in_progress")

    def test_last_run_duration(self):
        out = bps.summarize_runs([_run("success")])
        self.assertEqual(out["last_run"]["duration_seconds"], 450)
        self.assertEqual(out["last_run"]["conclusion"], "success")

    def test_build_status_fails_open_per_workflow(self):
        with mock.patch.object(
            bps, "fetch_workflow_runs", side_effect=RuntimeError("boom")
        ):
            doc = bps.build_status("o/r", "tok")
        self.assertEqual(len(doc["workflows"]), len(bps.WORKFLOWS))
        self.assertTrue(all("error" in w for w in doc["workflows"]))
        self.assertIn("generated_at", doc)


class TestOpsEndpoints(unittest.TestCase):
    def _write_status(self, tmp_path, age_hours=1.0):
        generated = datetime.now(timezone.utc) - timedelta(hours=age_hours)
        doc = {
            "generated_at": generated.isoformat(),
            "repo": "o/r",
            "workflows": [
                {
                    "file": "weekly-pipeline.yml",
                    "name": "Weekly Pipeline",
                    "schedule": "Tuesdays 09:00 UTC",
                    "purpose": "test",
                    "last_run": _run("success"),
                    "recent": ["success", "failure"],
                    "success_rate": 0.5,
                }
            ],
        }
        path = tmp_path / "pipeline_status.json"
        path.write_text(json.dumps(doc))
        return path

    def test_status_endpoint_serves_snapshot(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            path = self._write_status(Path(td))
            with mock.patch.object(ops, "STATUS_PATH", path):
                resp = client.get("/api/ops/pipeline-status")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["is_stale"])
        self.assertEqual(body["workflows"][0]["name"], "Weekly Pipeline")

    def test_stale_snapshot_flagged(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            path = self._write_status(Path(td), age_hours=20)
            with mock.patch.object(ops, "STATUS_PATH", path):
                resp = client.get("/api/ops/pipeline-status")
        self.assertTrue(resp.json()["is_stale"])

    def test_missing_snapshot_404s(self):
        from pathlib import Path

        with mock.patch.object(ops, "STATUS_PATH", Path("/nonexistent/x.json")):
            resp = client.get("/api/ops/pipeline-status")
        self.assertEqual(resp.status_code, 404)

    def test_dashboard_serves_html(self):
        resp = client.get("/api/ops/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Pipeline Status", resp.text)


if __name__ == "__main__":
    unittest.main()
