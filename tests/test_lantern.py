import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from lantern.core import summarize, synthetic
from lantern.checker import load_config, check_service
from lantern.server import create_app


class SummaryTests(unittest.TestCase):
    def test_gap_is_unknown_with_reduced_coverage(self):
        services, samples = synthetic(200000, "gap")
        row = summarize(services, samples, 200000, 24, 600)["services"][0]
        self.assertEqual(row["state"], "unknown")
        self.assertLess(row["coverage"], 100)
        self.assertEqual(row["reachability"], 100)

    def test_no_observations_does_not_claim_uptime(self):
        row = summarize([{"id": "x", "label": "X", "kind": "tcp"}], [], 2000, 1, 60)[
            "services"
        ][0]
        self.assertIsNone(row["reachability"])
        self.assertEqual(row["coverage"], 0)
        self.assertEqual(row["state"], "unknown")

    def test_incident_does_not_claim_recovery_across_gap(self):
        rows = [
            {"service_id": "x", "time": 100, "state": "down", "latency": None},
            {"service_id": "x", "time": 1000, "state": "up", "latency": 1},
        ]
        report = summarize(
            [{"id": "x", "label": "X", "kind": "tcp"}], rows, 1000, 1, 60
        )["services"][0]
        self.assertEqual(report["incidents"][0]["resolution"], "coverage gap")
        self.assertEqual(report["incidents"][0]["ended"], 100)

    def test_future_samples_are_not_counted(self):
        services, samples = synthetic(200000, "normal")
        report = summarize(services, samples, 199000, 1, 600)
        self.assertTrue(
            all(
                s["checked_at"] is None or s["checked_at"] <= 199000
                for s in report["services"]
            )
        )


class CheckerTests(unittest.TestCase):
    def config(self, folder, service):
        path = Path(folder) / "services.json"
        path.write_text(
            json.dumps(
                {"allowed_hosts": ["127.0.0.1"], "interval": 30, "services": [service]}
            ),
            encoding="utf-8",
        )
        return path

    def test_config_requires_explicit_allowed_host_and_no_url_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            for url in [
                "http://other.example/",
                "http://user:secret@127.0.0.1/",
                "http://127.0.0.1/?token=secret",
            ]:
                with self.assertRaises(ValueError):
                    load_config(
                        self.config(
                            folder,
                            {"id": "x", "label": "X", "kind": "http", "url": url},
                        )
                    )

    def test_probe_returns_only_redacted_states(self):
        with patch(
            "lantern.checker.socket.create_connection",
            side_effect=OSError("private endpoint should not leak"),
        ):
            self.assertEqual(
                check_service({"kind": "tcp", "host": "127.0.0.1", "port": 1}),
                {"state": "down", "latency": None},
            )
        fake = MagicMock()
        fake.__enter__.return_value = fake
        fake.stream.return_value.__enter__.return_value.status_code = 302
        with patch("lantern.checker.httpx.Client", return_value=fake):
            self.assertEqual(
                check_service({"kind": "http", "url": "http://127.0.0.1/"})["state"],
                "down",
            )

    def test_local_collector_stores_results_and_report_omits_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = self.config(
                folder,
                {
                    "id": "x",
                    "label": "My service",
                    "kind": "tcp",
                    "host": "127.0.0.1",
                    "port": 12345,
                },
            )
            with TestClient(
                create_app(
                    cfg,
                    Path(folder) / "data.sqlite",
                    probe=lambda s: {"state": "up", "latency": 2},
                )
            ) as client:
                report = None
                for _ in range(50):
                    report = client.get("/api/summary").json()
                    if report["services"][0]["samples"]:
                        break
                    time.sleep(0.01)
                self.assertEqual(report["services"][0]["state"], "up")
                serialized = json.dumps(report)
                self.assertNotIn("127.0.0.1", serialized)
                self.assertNotIn("12345", serialized)

    def test_demo_mode_and_bounds(self):
        with TestClient(create_app()) as client:
            self.assertEqual(client.get("/api/config").json()["mode"], "synthetic")
            self.assertEqual(client.get("/api/summary?hours=999").status_code, 422)
            self.assertEqual(
                client.get("/api/summary?scenario=gap").json()["services"][0]["state"],
                "unknown",
            )
            self.assertEqual(client.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
