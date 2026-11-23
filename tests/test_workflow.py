import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from canvasgate.backends import ApiBackend, CodexBackend, MockBackend, WorkflowError, validate_response
from canvasgate.cli import main
from canvasgate.engine import Workflow


class Recorder:
    def __init__(self, responses=None):
        self.inputs = []
        self.responses = responses or [{"status": True, "confidence": 0.9, "text": "output valid"}]

    def generate(self, instruction, context, feedback):
        self.inputs.append(json.loads(json.dumps({"task": instruction, "context": context, "feedback": feedback})))
        return self.responses[min(len(self.inputs) - 1, len(self.responses) - 1)]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.canvas = self.root / "workflow.canvas"

    def workflow(self, texts, edges):
        nodes = [{"id": key, "type": "text", "text": text} for key, text in texts.items()]
        self.save(nodes, edges)
        return Workflow(self.canvas)

    def save(self, nodes, edges):
        self.canvas.write_text(json.dumps({"nodes": nodes, "edges": [
            {"id": f"e{i}", "fromNode": a, "toNode": b} for i, (a, b) in enumerate(edges)
        ]}), encoding="utf-8")

    def base(self, approved=True, extra=None):
        texts = {
            "source": 'DATA:\n' + json.dumps({"status": approved, "confidence": 1, "text": "private source"}),
            "gate": "GATE: AND",
            "model": "CODEX:\n" + json.dumps({"prompt": "summarize", **(extra or {})}),
            "output": "OUTPUT: Final",
        }
        return self.workflow(texts, [("source", "gate"), ("gate", "model"), ("model", "output")])

    def test_closed_gate_makes_zero_calls(self):
        backend = Recorder()
        report = self.base(False).run(backend)
        self.assertEqual(report["outcome"], "blocked")
        self.assertEqual(report["calls"], 0)
        self.assertEqual(backend.inputs, [])
        self.assertEqual(report["outputs"], {})

    def test_success_forwards_only_selected_context(self):
        workflow = self.workflow({
            "secret": 'DATA:\n{"status":false,"confidence":1,"text":"DO NOT SEND"}',
            "source": "TEXT:\npublic source", "or": "GATE: OR",
            "model": 'CODEX:\n{"prompt":"summarize"}', "output": "OUTPUT:",
        }, [("secret", "or"), ("source", "or"), ("or", "model"), ("model", "output")])
        backend = Recorder()
        report = workflow.run(backend)
        self.assertEqual(report["outcome"], "completed")
        self.assertEqual(set(backend.inputs[0]["context"]), {"source"})
        self.assertNotIn("DO NOT SEND", json.dumps(backend.inputs))
        self.assertEqual(report["outputs"]["output"]["text"], "output valid")

    def test_retry_has_feedback_and_stops_at_valid_response(self):
        backend = Recorder([{"wrong": True}, {"status": True, "confidence": 0.9, "text": "output valid"}])
        report = self.base(extra={"max_retries": 2}).run(backend)
        self.assertEqual(report["calls"], 2)
        self.assertEqual(report["outcome"], "completed")
        self.assertTrue(backend.inputs[1]["feedback"])

    def test_retry_exhaustion_never_publishes_failed_output(self):
        backend = Recorder([{"status": True, "confidence": 0.1, "text": "untrusted"}])
        report = self.base(extra={"max_retries": 1, "min_confidence": 0.8}).run(backend)
        self.assertEqual(report["calls"], 2)
        self.assertEqual(report["outcome"], "error")
        self.assertEqual(report["outputs"], {})
        self.assertEqual(report["nodes"]["output"]["state"], "skipped")

    def test_global_budget_overrides_retries(self):
        report = self.base(extra={"max_retries": 10}).run(Recorder([{}]), max_calls=2)
        self.assertEqual(report["calls"], 2)
        self.assertIn("max_calls", report["nodes"]["model"]["reason"])

    def test_global_budget_is_shared_by_distinct_model_nodes(self):
        workflow = self.workflow({
            "source": "TEXT:\ninput", "a": 'CODEX:\n{"prompt":"first"}',
            "b": 'CODEX:\n{"prompt":"second"}', "o": "OUTPUT:",
        }, [("source", "a"), ("a", "b"), ("b", "o")])
        backend = Recorder()
        report = workflow.run(backend, max_calls=1)
        self.assertEqual(len(backend.inputs), 1)
        self.assertEqual(report["nodes"]["b"]["attempts"], 0)
        self.assertEqual(report["outcome"], "error")

    def test_routing_does_not_increase_confidence(self):
        workflow = self.workflow({
            "source": 'DATA:\n{"status":true,"confidence":0.2,"text":"uncertain"}',
            "or": "GATE: OR", "check": 'GATE: CONFIDENCE\n{"min_confidence":0.8}',
            "o": "OUTPUT:",
        }, [("source", "or"), ("or", "check"), ("check", "o")])
        report = workflow.run(MockBackend())
        self.assertEqual(report["outcome"], "blocked")
        self.assertEqual(report["nodes"]["or"]["confidence"], 0.2)

    def test_zero_budget_never_calls_model(self):
        backend = Recorder()
        report = self.base().run(backend, max_calls=0)
        self.assertEqual(report["calls"], 0)
        self.assertEqual(backend.inputs, [])

    def test_context_limit_blocks_before_call(self):
        backend = Recorder()
        report = self.base().run(backend, max_context_chars=1)
        self.assertEqual(backend.inputs, [])
        self.assertEqual(report["outcome"], "error")

    def test_cycle_rejected_before_execution(self):
        with self.assertRaisesRegex(WorkflowError, "Cycle"):
            self.workflow({"a": "GATE: AND", "b": "GATE: AND", "o": "OUTPUT:"}, [("a", "b"), ("b", "a"), ("b", "o")])

    def test_invalid_edges_and_duplicate_ids(self):
        with self.assertRaises(WorkflowError):
            self.workflow({"a": "hello", "o": "OUTPUT:"}, [("missing", "o")])
        self.canvas.write_text('{"nodes":[{"id":"x","type":"text","text":"a"},{"id":"x","type":"text","text":"b"}],"edges":[]}', encoding="utf-8")
        with self.assertRaises(WorkflowError):
            Workflow(self.canvas)

    def test_invalid_config_is_preflight_error(self):
        for extra in ({"max_retries": -1}, {"min_words": 8, "max_words": 3}, {"pattern": "["}, {"unknown": 1}):
            with self.subTest(extra=extra), self.assertRaises(WorkflowError):
                self.base(extra=extra)

    def test_gate_checks_and_not(self):
        workflow = self.workflow({
            "s": "TEXT:\naprobat aici", "regex": 'GATE: REGEX\n{"pattern":"^aprobat"}',
            "words": 'GATE: WORDS\n{"min_words":2,"max_words":2}',
            "confidence": 'GATE: CONFIDENCE\n{"min_confidence":0.8}', "o": "OUTPUT:",
        }, [("s", "regex"), ("regex", "words"), ("words", "confidence"), ("confidence", "o")])
        self.assertEqual(workflow.run(MockBackend())["outcome"], "completed")
        workflow = self.workflow({"s": 'DATA:\n{"status":false,"confidence":1,"text":"secret"}', "n": "GATE: NOT", "o": "OUTPUT:"}, [("s", "n"), ("n", "o")])
        report = workflow.run(MockBackend())
        self.assertEqual(report["outcome"], "completed")
        self.assertEqual(report["outputs"]["o"]["text"], "")

    def test_not_cannot_revive_skipped_branch(self):
        self.base(False)
        raw = json.loads(self.canvas.read_text())
        raw["nodes"].insert(-1, {"id": "not", "type": "text", "text": "GATE: NOT"})
        raw["edges"][-1]["toNode"] = "not"
        raw["edges"].append({"id": "en", "fromNode": "not", "toNode": "output"})
        self.canvas.write_text(json.dumps(raw), encoding="utf-8")
        report = Workflow(self.canvas).run(MockBackend())
        self.assertEqual(report["nodes"]["not"]["state"], "skipped")

    def test_file_vault_boundary(self):
        with tempfile.TemporaryDirectory() as outside:
            note = Path(outside) / "private.md"
            note.write_text("secret", encoding="utf-8")
            self.save([{"id": "file", "type": "file", "file": str(note)}, {"id": "o", "type": "text", "text": "OUTPUT:"}], [("file", "o")])
            with self.assertRaisesRegex(WorkflowError, "vault"):
                Workflow(self.canvas)

    def test_markdown_file_source(self):
        (self.root / "note.md").write_text("notă locală", encoding="utf-8")
        self.save([{"id": "f", "type": "file", "file": "note.md"}, {"id": "o", "type": "text", "text": "OUTPUT:"}], [("f", "o")])
        report = Workflow(self.canvas).run(MockBackend())
        self.assertEqual(report["outputs"]["o"]["text"], "notă locală")

    def test_schema_rejects_nan_bool_confidence_and_extras(self):
        for value in (float("nan"), float("inf"), True, -1, 1.1, "0.9"):
            with self.subTest(value=value), self.assertRaises(WorkflowError):
                validate_response({"status": True, "confidence": value, "text": "x"})

    def test_transport_error_is_not_retried(self):
        backend = Recorder()
        with patch.object(backend, "generate", side_effect=WorkflowError("timeout")) as generate:
            report = self.base(extra={"max_retries": 2}).run(backend)
        generate.assert_called_once()
        self.assertEqual(report["calls"], 1)
        self.assertEqual(report["outcome"], "error")

    def test_cli_dry_run_and_report(self):
        self.base()
        out = self.root / "runs"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.canvas), "--dry-run", "--output-dir", str(out)]), 0)
            self.assertFalse(out.exists())
            self.assertEqual(main([str(self.canvas), "--output-dir", str(out)]), 0)
        report_path = next(out.glob("*/report.json"))
        self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["backend"], "mock")
        self.assertTrue(report_path.with_name("results.md").is_file())

    def test_example_canvas(self):
        workflow = Workflow(Path(__file__).resolve().parents[1] / "examples/vault/workflow.canvas")
        self.assertEqual(workflow.run(MockBackend())["outcome"], "completed")


class BackendTests(unittest.TestCase):
    def test_api_sends_no_tools_history_or_vault_access(self):
        response = io.BytesIO(json.dumps({"status": "completed", "output": [{"type": "message", "content": [{
            "type": "output_text", "text": '{"status":true,"confidence":0.9,"text":"ok"}'
        }]}]}).encode())
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret"}), patch("canvasgate.backends.urlopen", return_value=response) as call:
            data = ApiBackend("test-model").generate("task", {"a": "text"}, [])
        request = call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["tools"], [])
        self.assertFalse(payload["store"])
        self.assertNotIn("previous_response_id", payload)
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertEqual(data["text"], "ok")
        self.assertNotIn("test-secret", request.data.decode())

    def test_api_incomplete_response_is_failure(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}), patch("canvasgate.backends.urlopen", return_value=io.BytesIO(b'{"status":"incomplete"}')):
            with self.assertRaisesRegex(WorkflowError, "Incomplete"):
                ApiBackend("test-model").generate("task", {}, [])

    def test_cli_argv_uses_stdin_and_separate_temporary_cwd(self):
        def run(command, **kwargs):
            self.assertEqual(command[-1], "-")
            self.assertIn("--ephemeral", command)
            self.assertIn("--ignore-user-config", command)
            self.assertIn("read-only", command)
            self.assertIn("shell_tool=false", " ".join(command))
            self.assertIn("task", kwargs["input"])
            self.assertNotIn("shell", kwargs)
            Path(command[command.index("--output-last-message") + 1]).write_text('{"status":true,"confidence":1,"text":"ok"}', encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)
        with patch("canvasgate.backends.shutil.which", return_value="codex.exe"), patch("canvasgate.backends.subprocess.run", side_effect=run):
            self.assertEqual(CodexBackend().generate("task", {}, [])["text"], "ok")


if __name__ == "__main__":
    unittest.main()
