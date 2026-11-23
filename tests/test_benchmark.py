import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from canvasgate.backends import CodexBackend
from canvasgate.benchmark import expected_result, assess


class MeasurementTests(unittest.TestCase):
    def test_usage_events_are_recorded_and_cache_is_not_double_counted(self):
        def run(command, **kwargs):
            Path(command[command.index("--output-last-message") + 1]).write_text(
                '{"status":true,"confidence":1,"text":"ok"}', encoding="utf-8")
            events = [
                {"type": "item.completed", "item": {"type": "command_execution"}},
                {"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 700, "output_tokens": 100, "reasoning_output_tokens": 30}},
            ]
            return subprocess.CompletedProcess(command, 0, stdout="\n".join(json.dumps(e) for e in events), stderr="")
        with tempfile.TemporaryDirectory() as folder:
            backend = CodexBackend(event_dir=folder)
            with patch("canvasgate.backends.shutil.which", return_value="codex.exe"), patch("canvasgate.backends.subprocess.run", side_effect=run):
                backend.generate("task", {}, [])
                backend.generate("task", {}, [])
            usage = backend.token_usage()
            self.assertEqual(usage["total_tokens"], 2200)
            self.assertEqual(usage["uncached_input_tokens"], 600)
            self.assertEqual(usage["reasoning_output_tokens"], 60)
            self.assertEqual(backend.runs[0]["tool_calls"], 1)
            self.assertTrue((Path(folder) / "call-002.jsonl").exists())

    def test_missing_usage_is_unavailable_not_zero(self):
        backend = CodexBackend()
        backend.runs = [{"usage": None}]
        self.assertIsNone(backend.token_usage())
        backend.runs = [{"usage": {"output_tokens": 10}}]
        self.assertIsNone(backend.token_usage())

    def test_oracle_matches_hand_calculated_dispatch(self):
        expected = expected_result()
        self.assertEqual([(a["order_id"], a["truck_id"]) for a in expected["assignments"]],
                         [("O01", "T1"), ("O02", "T3"), ("O03", "T2"), ("O04", "T1"), ("O06", "T2"), ("O07", "T3"), ("O08", "T1")])
        self.assertEqual(expected["total_revenue"], 1610)
        self.assertEqual(expected["truck_loads"], [
            {"truck_id": "T1", "weight_kg": 1000, "volume_m3": 6},
            {"truck_id": "T2", "weight_kg": 750, "volume_m3": 5},
            {"truck_id": "T3", "weight_kg": 600, "volume_m3": 4},
        ])
        self.assertEqual(len(expected["rejected"]), 7)

    def test_quality_check_detects_wrong_load_even_with_confidence_one(self):
        expected = expected_result()
        response = {"status": True, "confidence": 1, "text": json.dumps(expected)}
        self.assertTrue(assess(response)["passed"])
        expected["truck_loads"][0]["weight_kg"] = 999
        response["text"] = json.dumps(expected)
        assessment = assess(response)
        self.assertFalse(assessment["passed"])
        self.assertFalse(assessment["checks"]["truck_loads"])


if __name__ == "__main__":
    unittest.main()
