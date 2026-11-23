import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canvasgate.backends import ApiBackend
from canvasgate.benchmark import expected_result
from canvasgate.canvasgate import CanvasGateWorkflow
from canvasgate import stress_benchmark as stress


class Recorder:
    def __init__(self):
        self.calls = []

    def generate(self, instruction, context, feedback):
        self.calls.append(context)
        return {"status": True, "confidence": 1, "text": json.dumps(expected_result())}


class StressBenchmarkTests(unittest.TestCase):
    def test_corpus_contains_actual_conflicts_and_typed_filtering_removes_them(self):
        with tempfile.TemporaryDirectory() as folder:
            vault = Path(folder).resolve()
            with patch.object(stress, "VAULT", vault), patch.object(stress, "FIXTURE", vault / "StressBenchmark"):
                notes = stress.prepare()
                self.assertEqual(len(notes), 30)
                self.assertEqual(notes, stress.build_notes())
                self.assertIn('"frozen"', notes["Archive-01-fleet.md"])
                self.assertNotIn('"frozen"', notes["Current-fleet.md"])
                self.assertIn('"status": "active"', notes["Archive-01-orders.md"])
                backend = Recorder()
                report = CanvasGateWorkflow(stress.FIXTURE / "workflow.canvas", vault).run(backend, max_calls=1)
                self.assertEqual(report["calls"], 1)
                self.assertEqual(report["outcome"], "completed")
                sent = json.dumps(backend.calls[0])
                self.assertNotIn("ARCHIVE_ONLY", sent)
                self.assertNotIn("NOT_DISPATCH_INPUT", sent)
                self.assertNotIn("title: Current", sent)
                self.assertIn("status: current", sent)
                self.assertIn("Reject status=cancelled", sent)
                self.assertIn("FIRST truck", sent)
                self.assertIn("remaining capacity", sent)
                self.assertEqual(len(backend.calls[0]), 3)
                self.assertEqual(sum(n["state"] == "EXECUTED" for key, n in report["nodes"].items() if key.endswith("-slice")), 3)
                self.assertTrue(stress.assess({"status": True, "confidence": 1, "text": report["outputs"]["output"]["text"]})["passed"])

    def test_api_retains_real_usage_reasoning_and_never_logs_credentials(self):
        provider_result = {"status": "completed", "usage": {"input_tokens": 123, "input_tokens_details": {"cached_tokens": 0},
                           "output_tokens": 45, "output_tokens_details": {"reasoning_tokens": 20}},
                           "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"status":true,"confidence":1,"text":"ok"}'}]}]}
        with tempfile.TemporaryDirectory() as folder:
            backend = ApiBackend("test-model", reasoning_effort="medium", event_dir=folder)
            with patch.dict("os.environ", {"OPENAI_API_KEY": "DO_NOT_LOG_THIS"}), patch("canvasgate.backends.urlopen", return_value=io.BytesIO(json.dumps(provider_result).encode())):
                self.assertEqual(backend.generate("task", {}, [])["text"], "ok")
            request = json.loads((Path(folder) / "call-001.request.json").read_text())
            self.assertEqual(request["reasoning"]["effort"], "medium")
            self.assertEqual(backend.runs[0]["usage"]["output_tokens_details"]["reasoning_tokens"], 20)
            self.assertTrue(all("DO_NOT_LOG_THIS" not in path.read_text() for path in Path(folder).iterdir()))


if __name__ == "__main__":
    unittest.main()
