import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from canvasgate.backends import CodexBackend, MockBackend, WorkflowError
from canvasgate.canvasgate import CanvasGateWorkflow
from canvasgate.security import SecurityPolicy, ensure_no_secrets, redact
from canvasgate.snapshots import RunSession, claim_operation


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name).resolve()
        self.canvas = self.vault / "flow.canvas"

    def workflow(self, texts, edges, *, files=None, settings=None):
        raw = {"nodes": [{"id": key, "type": "text", "text": value} for key, value in texts.items()]
               + [{"id": key, "type": "file", "file": value} for key, value in (files or {}).items()],
               "edges": [{"id": f"e{i}", "fromNode": a, "toNode": b} for i, (a, b) in enumerate(edges)],
               "canvasgate": settings or {}}
        self.canvas.write_text(json.dumps(raw), encoding="utf-8")
        return CanvasGateWorkflow(self.canvas)

    def test_empty_policy_slice_fails_explicit_contract_before_any_model(self):
        (self.vault / "policy.md").write_text("---\nrevision: 2\nrole: policy\n---\n## Policy\n# Heading escape\nRequired rule.\n", encoding="utf-8")
        workflow = self.workflow({"s": "SLICE: SECTION:Policy", "a": "AGENT: use policy", "o": "OUTPUT:"},
            [("f", "s"), ("s", "a"), ("a", "o")], files={"f": "policy.md"}, settings={"contracts": {
                "a": {"input": {"required_text": ["Required rule."], "required_sources": [{"path": "policy.md", "version": {"key": "revision", "equals": 2}, "role": "policy"}], "allowed_sources": ["policy.md"]}}}})
        report = workflow.run(MockBackend())
        self.assertEqual(report["calls"], 0)
        self.assertEqual(report["nodes"]["a"]["state"], "FAILED")
        self.assertIn("Essential text", report["abort_reason"])
        self.assertTrue((Path(report["snapshot"]["path"]) / "manifest.json").exists())

    def test_hash_version_and_authorization_checks(self):
        content = "---\nrevision: 2\nrole: policy\n---\nRequired rule."
        (self.vault / "policy.md").write_text(content, encoding="utf-8")
        sha = hashlib.sha256((self.vault / "policy.md").read_bytes()).hexdigest()
        for required, allowed, should_pass in [
            ({"path": "policy.md", "sha256": sha, "version": {"key": "revision", "equals": 2}}, ["policy.md"], True),
            ({"path": "policy.md", "sha256": "0" * 64}, ["policy.md"], False),
            ({"path": "policy.md", "version": {"key": "revision", "equals": "2"}}, ["policy.md"], False),
            ({"path": "policy.md"}, ["another.md"], False),
        ]:
            with self.subTest(required=required):
                workflow = self.workflow({"a": "AGENT: plan", "o": "OUTPUT:"}, [("f", "a"), ("a", "o")], files={"f": "policy.md"},
                    settings={"contracts": {"a": {"input": {"required_sources": [required], "allowed_sources": allowed}}}})
                report = workflow.run(MockBackend())
                self.assertEqual(report["outcome"] == "completed", should_pass)
                self.assertEqual(report["calls"], 1 if should_pass else 0)

    def test_json_fields_and_full_output_schema(self):
        workflow = self.workflow({"i": 'INPUT: {"policy":{"rules":["a"]}}', "a": "AGENT: JSON", "o": "OUTPUT:"}, [("i", "a"), ("a", "o")],
            settings={"require_contracts": ["AGENT"], "contracts": {"a": {
                "input": {"required_fields": ["policy.rules"]},
                "output": {"schema": {"type": "object", "required": ["items"], "properties": {"items": {"type": "array", "minItems": 2}}}}}}})
        good = MockBackend({"status": True, "confidence": 1, "text": '{"items":[1,2]}'})
        self.assertEqual(workflow.run(good)["outcome"], "completed")
        bad = MockBackend({"status": True, "confidence": 1, "text": '{"items":[1]}'})
        self.assertEqual(workflow.run(bad)["outcome"], "error")

    def test_remote_schema_refs_and_missing_required_contract_rejected(self):
        for settings in ({"require_contracts": ["AGENT"]}, {"contracts": {"a": {"input": {"schema": {"$ref": "https://example.com/schema"}}}}}):
            with self.subTest(settings=settings), self.assertRaises(WorkflowError):
                self.workflow({"i": "INPUT: x", "a": "AGENT: x", "o": "OUTPUT:"}, [("i", "a"), ("a", "o")], settings=settings)

    def test_replay_uses_snapshot_after_live_graph_and_sources_deleted(self):
        (self.vault / "note.md").write_text("---\nrevision: 3\n---\nOriginal policy", encoding="utf-8")
        workflow = self.workflow({"a": "AGENT: plan", "w": "WRITE: APPEND:out.md"}, [("f", "a"), ("a", "w")], files={"f": "note.md"})
        report = workflow.run(MockBackend(), run_id="original")
        original_output = (self.vault / "out.md").read_bytes()
        self.canvas.unlink()
        (self.vault / "note.md").unlink()
        with patch.object(MockBackend, "generate", side_effect=AssertionError("Replay called a model")):
            replay = CanvasGateWorkflow.replay_run(self.vault, "original", new_run_id="replayed")
        self.assertTrue(replay["replay_comparison"]["matches"])
        self.assertEqual(replay["external_calls"], 0)
        self.assertEqual(replay["usage"]["total_tokens"], 0)
        self.assertEqual(replay["written_files"], [])
        self.assertEqual((self.vault / "out.md").read_bytes(), original_output)
        self.assertEqual(report["nodes"]["a"]["text"], replay["nodes"]["a"]["text"])

    def test_snapshot_tampering_is_detected(self):
        workflow = self.workflow({"i": "INPUT: x", "o": "OUTPUT:"}, [("i", "o")])
        report = workflow.run(MockBackend(), run_id="tamper")
        root = Path(report["snapshot"]["path"])
        graph = json.loads((root / "graph.json").read_text())
        graph["nodes"][0]["text"] = "INPUT: changed"
        (root / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
        with self.assertRaisesRegex(WorkflowError, "hash mismatch"):
            CanvasGateWorkflow.replay_run(self.vault, "tamper")

    def test_operation_key_reuses_completed_result_without_duplicate_append(self):
        workflow = self.workflow({"i": "INPUT: appended", "w": "WRITE: APPEND:out.md"}, [("i", "w")])
        first = workflow.run(MockBackend(), operation_key="same-operation")
        second = workflow.run(MockBackend(), operation_key="same-operation")
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertTrue(second["resume"]["already_completed"])
        self.assertEqual((self.vault / "out.md").read_text(), "appended")
        with self.assertRaisesRegex(WorkflowError, "different operation"):
            claim_operation(self.vault, "same-operation", {"different": True})

    def test_completed_resume_is_idempotent(self):
        workflow = self.workflow({"i": "INPUT: text", "w": "WRITE: APPEND:out.md"}, [("i", "w")])
        workflow.run(MockBackend(), run_id="once")
        report = CanvasGateWorkflow.resume_run(self.vault, "once", MockBackend())
        self.assertTrue(report["resume"]["already_completed"])
        self.assertEqual((self.vault / "out.md").read_text(), "text")

    def test_directory_permissions_and_strict_cli_boundary(self):
        (self.vault / "inputs").mkdir()
        (self.vault / "inputs/a.md").write_text("safe")
        policy = SecurityPolicy(self.vault, {"read_dirs": ["inputs"], "write_dirs": ["outputs"]}, strict_isolation=True)
        self.assertEqual(policy.path("inputs/a.md"), self.vault / "inputs/a.md")
        with self.assertRaises(WorkflowError):
            policy.path("outside.md")
        with self.assertRaises(WorkflowError):
            policy.path("inputs/a.md", writing=True)
        with self.assertRaisesRegex(WorkflowError, "not process isolation"):
            policy.check_backend(CodexBackend())
        for path in (".env", ".ssh/id_rsa", "key.pem", "../outside.md"):
            with self.subTest(path=path), self.assertRaises(WorkflowError):
                policy.path(path)

    def test_secrets_are_rejected_before_snapshot_or_redacted_from_diagnostics(self):
        secret = "sk-proj-" + "X" * 40
        with self.assertRaises(WorkflowError):
            ensure_no_secrets(secret)
        self.assertNotIn(secret, redact("Error: " + secret))
        workflow = self.workflow({"i": "INPUT: " + secret, "o": "OUTPUT:"}, [("i", "o")])
        with self.assertRaisesRegex(WorkflowError, "Sensitive"):
            workflow.run(MockBackend(), run_id="no-secret")
        self.assertFalse((self.vault / ".canvasgate/runs/no-secret").exists())


class ProcessRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name).resolve()
        self.script = self.vault / "child.py"

    def graph(self, agent=False):
        texts = {"i": "INPUT: appended", "w": "WRITE: APPEND:out.md"}
        edges = [("i", "w")]
        if agent:
            texts["a"] = "AGENT: plan"
            edges = [("i", "a"), ("a", "w")]
        raw = {"nodes": [{"id": key, "type": "text", "text": value} for key, value in texts.items()],
               "edges": [{"id": f"e{i}", "fromNode": a, "toNode": b} for i, (a, b) in enumerate(edges)]}
        path = self.vault / "flow.canvas"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return path

    def child(self, code, expected):
        self.script.write_text(code, encoding="utf-8")
        result = subprocess.run([sys.executable, str(self.script), str(self.vault)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stderr)

    def test_full_process_exit_during_external_call_requires_reconciliation(self):
        self.graph(agent=True)
        self.child('''import os, sys
from pathlib import Path
from canvasgate.canvasgate import CanvasGateWorkflow
root = Path(sys.argv[1])
class CrashBackend:
    def generate(self, *args):
        (root / "external-effect.txt").write_text("performed once")
        os._exit(73)
CanvasGateWorkflow(root / "flow.canvas").run(CrashBackend(), run_id="interrupted")
''', 73)
        class CrashBackend:
            def generate(self, *args):
                raise AssertionError("The uncertain call was repeated")
        report = CanvasGateWorkflow.resume_run(self.vault, "interrupted", CrashBackend())
        self.assertIn("Reconcile", report["abort_reason"])
        session = RunSession.load(self.vault, "interrupted")
        effect_id = next(iter(session.manifest["effects"]))
        session.reconcile(effect_id, "record_result", {"status": True, "confidence": 1, "text": "reconciled"})
        result = CanvasGateWorkflow.resume_run(self.vault, "interrupted", CrashBackend())
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual((self.vault / "out.md").read_text(), "reconciled")
        self.assertEqual((self.vault / "external-effect.txt").read_text(), "performed once")

    def test_process_exit_after_commit_does_not_append_twice_on_resume(self):
        self.graph()
        (self.vault / "out.md").write_text("base-")
        self.child('''import os, sys
from pathlib import Path
from canvasgate.canvasgate import CanvasGateWorkflow
from canvasgate.backends import MockBackend
root = Path(sys.argv[1])
CanvasGateWorkflow.audit = staticmethod(lambda *args: os._exit(74))
CanvasGateWorkflow(root / "flow.canvas").run(MockBackend(), run_id="committed-crash")
''', 74)
        self.assertEqual((self.vault / "out.md").read_text(), "base-appended")
        result = CanvasGateWorkflow.resume_run(self.vault, "committed-crash", MockBackend())
        self.assertEqual(result["transaction_state"], "COMMITTED")
        self.assertEqual((self.vault / "out.md").read_text(), "base-appended")


if __name__ == "__main__":
    unittest.main()
