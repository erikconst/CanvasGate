import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canvasgate.backends import CodexBackend, MockBackend, WorkflowError
from canvasgate.canvasgate import CanvasGateWorkflow, edge_open
from canvasgate.cli import main
from canvasgate.engine import LegacyWorkflow, Workflow
from canvasgate.markdown import frontmatter, section
from canvasgate.providers import BackendRouter
from canvasgate.transactions import StagingBuffer, TransactionStore, atomic_bytes


class Recorder:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or [{"status": True, "confidence": 0.9, "text": "approved plan"}]

    def generate(self, prompt, context, feedback):
        self.calls.append({"prompt": prompt, "context": json.loads(json.dumps(context)), "feedback": list(feedback)})
        response = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response


class CanvasGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name).resolve()
        self.canvas = self.vault / "workflow.canvas"

    def workflow(self, texts, edges, files=None):
        nodes = [{"id": key, "type": "text", "text": text} for key, text in texts.items()]
        nodes += [{"id": key, "type": "file", "file": path} for key, path in (files or {}).items()]
        connections = [{"id": f"e{i}", "fromNode": item[0], "toNode": item[1], "label": item[2] if len(item) == 3 else ""} for i, item in enumerate(edges)]
        self.canvas.write_text(json.dumps({"nodes": nodes, "edges": connections}), encoding="utf-8")
        return CanvasGateWorkflow(self.canvas)

    def test_if_else_join_executes_only_active_branch(self):
        for flag in (True, False):
            with self.subTest(flag=flag):
                workflow = self.workflow({
                    "input": f"INPUT: {str(flag).lower()}", "yes": "JOIN: ANY", "no": "JOIN: ANY",
                    "join": "JOIN: ANY", "write": "WRITE: OVERWRITE:result.md",
                }, [("input", "yes", "true"), ("input", "no", "false"), ("yes", "join"), ("no", "join"), ("join", "write")])
                report = workflow.run(MockBackend())
                self.assertEqual(report["transaction_state"], "COMMITTED")
                self.assertEqual((self.vault / "result.md").read_text(), str(flag).lower())
                self.assertEqual(report["nodes"]["no" if flag else "yes"]["state"], "SKIPPED")
                self.assertEqual(report["calls"], 0)

    def test_yaml_section_boundary_does_not_send_unrelated_context(self):
        (self.vault / "spec.md").write_text("---\nstatus: approved\nsecret: PRIVATE_METADATA\n---\n# Overview\nPRIVATE_BACKGROUND\n## API\nBuild the exact API.\n### Errors\nReject bad input.\n## Marketing\nPRIVATE_MARKETING\n", encoding="utf-8")
        workflow = self.workflow({"gate": "GATE: YAML_EQ:status=approved", "slice": "SLICE: SECTION:API",
                                  "agent": "AGENT: Create an English plan.", "out": "OUTPUT: plan"},
                                 [("file", "gate"), ("gate", "slice", "true"), ("slice", "agent"), ("agent", "out")], {"file": "spec.md"})
        backend = Recorder()
        report = workflow.run(backend)
        self.assertEqual(report["outcome"], "completed")
        context = json.dumps(backend.calls[0]["context"])
        self.assertIn("Reject bad input", context)
        self.assertNotIn("PRIVATE_", context)
        self.assertEqual(set(backend.calls[0]["context"]), {"slice"})
        self.assertIsNone(report["usage"])

    def test_false_yaml_route_preserves_payload_for_review(self):
        (self.vault / "spec.md").write_text("---\nstatus: draft\n---\nNeeds approval.", encoding="utf-8")
        workflow = self.workflow({"gate": "GATE: YAML_EQ:status=approved", "yes": "AGENT: Implement.",
                                  "no": "AGENT: Explain missing approval.", "join": "MERGE:", "out": "OUTPUT:"},
                                 [("file", "gate"), ("gate", "yes", "true"), ("gate", "no", "false"), ("yes", "join"), ("no", "join"), ("join", "out")], {"file": "spec.md"})
        backend = Recorder()
        report = workflow.run(backend)
        self.assertEqual(report["calls"], 1)
        self.assertIn("Explain", backend.calls[0]["prompt"])
        self.assertIn("Needs approval", json.dumps(backend.calls[0]["context"]))
        self.assertEqual(report["nodes"]["yes"]["state"], "SKIPPED")

    def test_critical_false_gate_discards_previously_staged_write(self):
        (self.vault / "result.md").write_text("original", encoding="utf-8")
        workflow = self.workflow({"i": "INPUT: replacement", "w": "WRITE: OVERWRITE:result.md",
                                  "g": "GATE: LEN_LT:0", "o": "OUTPUT:"}, [("i", "w"), ("w", "g"), ("g", "o")])
        report = workflow.run(MockBackend())
        self.assertEqual(report["transaction_state"], "ABORTED")
        self.assertEqual((self.vault / "result.md").read_text(), "original")
        self.assertEqual(report["written_files"], [])
        self.assertEqual(len(report["staged_mutations"]), 1)
        self.assertTrue((self.vault / ".canvasgate/logs" / (report["run_id"] + ".md")).is_file())

    def test_join_all_requires_all_branches_any_does_not(self):
        workflow = self.workflow({"i": "INPUT: true", "a": "JOIN:", "b": "JOIN:", "all": "JOIN: ALL", "o": "OUTPUT:"},
                                 [("i", "a", "true"), ("i", "b", "false"), ("a", "all"), ("b", "all"), ("all", "o")])
        report = workflow.run(MockBackend())
        self.assertEqual(report["outcome"], "blocked")
        self.assertEqual(report["nodes"]["all"]["state"], "SKIPPED")

    def test_exact_switch_labels_are_case_sensitive(self):
        workflow = self.workflow({"i": "INPUT: refactor", "a": "OUTPUT: matched", "b": "OUTPUT: inactive"},
                                 [("i", "a", "refactor"), ("i", "b", "Refactor")])
        report = workflow.run(MockBackend())
        self.assertEqual(set(report["outputs"]), {"a"})
        self.assertFalse(edge_open("true", "false"))
        self.assertTrue(edge_open("fail", False))

    def test_retry_budget_and_json_validation(self):
        workflow = self.workflow({"i": "INPUT: data", "a": "AGENT: [schema=json] [max_retries=2] Return JSON.",
                                  "g": "GATE: JSON_KEYS:host,port,tls", "w": "WRITE: OVERWRITE:config.json"},
                                 [("i", "a"), ("a", "g"), ("g", "w", "true")])
        backend = Recorder([{"status": True, "confidence": 1, "text": "invalid"},
                            {"status": True, "confidence": 1, "text": '{"host":"localhost","port":443,"tls":true}'}])
        report = workflow.run(backend, max_calls=2)
        self.assertEqual(report["transaction_state"], "COMMITTED")
        self.assertEqual(report["calls"], 2)
        self.assertTrue(backend.calls[1]["feedback"])
        self.assertEqual(json.loads((self.vault / "config.json").read_text())["port"], 443)

    def test_shared_budget_prevents_second_agent(self):
        workflow = self.workflow({"i": "INPUT: data", "a": "AGENT: first", "b": "AGENT: second", "o": "OUTPUT:"},
                                 [("i", "a"), ("a", "b"), ("b", "o")])
        backend = Recorder()
        report = workflow.run(backend, max_calls=1)
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(report["transaction_state"], "ABORTED")

    def test_preview_and_duplicate_run_id_do_not_append_twice(self):
        workflow = self.workflow({"i": "INPUT: text", "w": "WRITE: APPEND:result.md"}, [("i", "w")])
        report = workflow.run(MockBackend(), commit=False, run_id="preview")
        self.assertEqual(report["transaction_state"], "PREVIEW")
        self.assertFalse((self.vault / "result.md").exists())
        workflow.run(MockBackend(), run_id="once")
        with self.assertRaises(WorkflowError):
            workflow.run(MockBackend(), run_id="once")
        self.assertEqual((self.vault / "result.md").read_text(), "text")

    def test_lines_and_yaml_typed_slices(self):
        (self.vault / "note.md").write_text("---\nreviewed: true\nlimits:\n  max: 12\n---\nfirst\nsecond\n", encoding="utf-8")
        workflow = self.workflow({"s": "SLICE: YAML:limits.max", "o": "OUTPUT:"}, [("file", "s"), ("s", "o")], {"file": "note.md"})
        self.assertEqual(workflow.run(MockBackend())["outputs"]["o"]["text"], "12")
        workflow = self.workflow({"i": "INPUT: one\ntwo\nthree", "s": "SLICE: LINES:2-3", "o": "OUTPUT:"}, [("i", "s"), ("s", "o")])
        self.assertEqual(workflow.run(MockBackend())["outputs"]["o"]["text"], "two\nthree")

    def test_missing_slice_never_calls_agent(self):
        workflow = self.workflow({"i": "INPUT: # Other\ntext", "s": "SLICE: SECTION:Missing", "a": "AGENT: run", "o": "OUTPUT:"},
                                 [("i", "s"), ("s", "a"), ("a", "o")])
        backend = Recorder()
        report = workflow.run(backend)
        self.assertEqual(backend.calls, [])
        self.assertEqual(report["outcome"], "error")

    def test_context_limit_and_transport_failure_stop_without_retry(self):
        workflow = self.workflow({"i": "INPUT: input", "a": "AGENT: [max_retries=2] run", "o": "OUTPUT:"}, [("i", "a"), ("a", "o")])
        backend = Recorder()
        self.assertEqual(workflow.run(backend, max_context_chars=1)["calls"], 0)
        backend = Recorder([WorkflowError("transport failure")])
        report = workflow.run(backend)
        self.assertEqual(report["calls"], 1)
        self.assertEqual(report["outcome"], "error")

    def test_source_edit_during_agent_prevents_stale_commit(self):
        note = self.vault / "spec.md"
        note.write_text("original specification", encoding="utf-8")
        workflow = self.workflow({"a": "AGENT: plan", "w": "WRITE: OVERWRITE:out.md"}, [("f", "a"), ("a", "w")], {"f": "spec.md"})
        backend = Recorder()
        original_generate = backend.generate

        def generate(*args):
            note.write_text("externally edited specification", encoding="utf-8")
            return original_generate(*args)

        backend.generate = generate
        report = workflow.run(backend)
        self.assertEqual(report["transaction_state"], "ABORTED")
        self.assertIn("Source changed", report["abort_reason"])
        self.assertFalse((self.vault / "out.md").exists())
        self.assertEqual(len(report["source_fingerprints"]), 1)

    def test_recovery_required_is_reported_when_rollback_also_fails(self):
        (self.vault / "a.md").write_bytes(b"old A")
        (self.vault / "b.md").write_bytes(b"old B")
        workflow = self.workflow({"i": "INPUT: new", "a": "WRITE: OVERWRITE:a.md", "b": "WRITE: OVERWRITE:b.md"}, [("i", "a"), ("i", "b")])
        real_replace = os.replace

        def replace(source, target):
            if Path(target) == self.vault / "b.md" or (Path(target) == self.vault / "a.md" and Path(source).read_bytes() == b"old A"):
                raise OSError("simulated disk failure during apply or rollback")
            return real_replace(source, target)

        with patch("canvasgate.transactions.os.replace", side_effect=replace):
            report = workflow.run(MockBackend())
        self.assertEqual(report["transaction_state"], "RECOVERY_REQUIRED")
        self.assertEqual(report["outcome"], "error")
        with self.assertRaisesRegex(WorkflowError, "recovery"):
            workflow.run(MockBackend())
        TransactionStore(self.vault).recover(report["run_id"])
        self.assertEqual((self.vault / "a.md").read_bytes(), b"old A")

    def test_code_only_validates_python_syntax_before_forwarding(self):
        workflow = self.workflow({"i": "INPUT: specification", "a": "AGENT: [schema=code_only] [max_retries=1] Implement.", "w": "WRITE: OVERWRITE:result.py"}, [("i", "a"), ("a", "w")])
        backend = Recorder([{"status": True, "confidence": 1, "text": "not python !!!"},
                            {"status": True, "confidence": 1, "text": "def valid():\n    return True\n"}])
        report = workflow.run(backend)
        self.assertEqual(report["calls"], 2)
        self.assertEqual(report["transaction_state"], "COMMITTED")
        self.assertTrue((self.vault / "result.py").read_text().startswith("def valid"))

    def test_backend_capabilities_checked_before_any_calls(self):
        workflow = self.workflow({"i": "INPUT: data", "a": "AGENT: [max_tokens=200] run", "o": "OUTPUT:"}, [("i", "a"), ("a", "o")])
        with self.assertRaisesRegex(WorkflowError, "cannot enforce"):
            workflow.run(CodexBackend())
        report = workflow.run(MockBackend())
        self.assertTrue(report["simulation"])
        self.assertEqual(report["usage"]["total_tokens"], 0)

    def test_invalid_graphs_and_paths_are_preflight_errors(self):
        for texts, edges in [
            ({"i": "INPUT: x", "w": "WRITE: OVERWRITE:../escape.md"}, [("i", "w")]),
            ({"i": "INPUT: x", "w": "WRITE: OVERWRITE:.obsidian/app.json"}, [("i", "w")]),
            ({"a": "JOIN:", "b": "JOIN:", "o": "OUTPUT:"}, [("a", "b"), ("b", "a"), ("a", "o")]),
            ({"i": "INPUT: x", "s": "SLICE: LINES:3-1", "o": "OUTPUT:"}, [("i", "s"), ("s", "o")]),
            ({"i": "INPUT: x", "a": "AGENT: [schema=made_up] run", "o": "OUTPUT:"}, [("i", "a"), ("a", "o")]),
        ]:
            with self.subTest(texts=texts), self.assertRaises(WorkflowError):
                self.workflow(texts, edges)

    def test_factory_preserves_legacy_graphs(self):
        self.workflow({"i": "INPUT: x", "o": "OUTPUT:"}, [("i", "o")])
        self.assertIsInstance(Workflow(self.canvas), CanvasGateWorkflow)
        self.workflow({"i": "TEXT:\nx", "o": "OUTPUT:"}, [("i", "o")])
        self.assertIsInstance(Workflow(self.canvas), LegacyWorkflow)

    def test_cli_dry_run_and_transactional_preview(self):
        self.workflow({"i": "INPUT: text", "w": "WRITE: OVERWRITE:result.md"}, [("i", "w")])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.canvas), "--dry-run"]), 0)
            self.assertFalse((self.vault / ".canvasgate").exists())
            self.assertEqual(main([str(self.canvas), "--no-commit", "--output-dir", str(self.vault / "runs")]), 0)
        self.assertFalse((self.vault / "result.md").exists())


class MarkdownTests(unittest.TestCase):
    def test_typed_yaml_and_duplicate_keys(self):
        metadata, body = frontmatter("---\nreviewed: true\ncount: 2\n---\ncontent")
        self.assertIs(metadata["reviewed"], True)
        self.assertEqual(body, "content")
        for text in ("---\na: 1\na: 2\n---\n", "---\na: &x [1]\nb: *x\n---\n", "---\na: true", "---\na: !!python/object:bad {}\n---\n"):
            with self.subTest(text=text), self.assertRaises(WorkflowError):
                frontmatter(text)

    def test_section_skips_fenced_code_headings_and_ambiguity(self):
        text = "# Intro\n```md\n## API\nnot real\n```\n## API\nreal\n### Errors\nerrors\n## End\nexcluded"
        self.assertEqual(section(text, "API"), "## API\nreal\n### Errors\nerrors")
        with self.assertRaises(WorkflowError):
            section("## API\none\n## API\ntwo", "API")


class ProviderTests(unittest.TestCase):
    def test_router_aggregates_codex_and_api_usage_without_network(self):
        from canvasgate.backends import ApiBackend
        default = CodexBackend("test-cli-model")
        router = BackendRouter(default)
        response = {"status": True, "confidence": 1, "text": "ok"}

        def codex_generate(backend, *args):
            backend.runs.append({"usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 2}})
            return response

        def api_generate(backend, *args):
            backend.runs.append({"usage": {"input_tokens": 20, "input_tokens_details": {"cached_tokens": 5}, "output_tokens": 3}})
            return response

        with patch.object(CodexBackend, "generate", codex_generate), patch.object(ApiBackend, "generate", api_generate):
            router.generate({"prompt": "first"}, {}, [])
            router.generate({"prompt": "second", "model": "openai/test-api-model", "max_tokens": 200}, {}, [])
        self.assertEqual(router.usage()["total_tokens"], 35)
        self.assertEqual(router.usage()["cached_input_tokens"], 5)
        self.assertEqual(router.usage()["uncached_input_tokens"], 25)
        self.assertEqual(router.select({"model": "openai/test-api-model", "max_tokens": 200}).max_output_tokens, 200)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name).resolve()
        self.store = TransactionStore(self.vault)

    def stage_two(self):
        (self.vault / "a.md").write_bytes(b"old A")
        (self.vault / "b.md").write_bytes(b"old B")
        staging = StagingBuffer(self.vault)
        staging.stage("a.md", "OVERWRITE", "new A", "a")
        staging.stage("b.md", "OVERWRITE", "new B", "b")
        return staging

    def test_staging_is_memory_only_and_combines_mutations_in_order(self):
        staging = StagingBuffer(self.vault)
        staging.stage("new.md", "APPEND", "one", "n1")
        staging.stage("new.md", "APPEND", "two", "n2")
        staging.stage("new.md", "OVERWRITE", "three", "n3")
        staging.stage("new.md", "APPEND", "four", "n4")
        self.assertFalse((self.vault / "new.md").exists())
        self.store.commit("combined", staging.files)
        self.assertEqual((self.vault / "new.md").read_bytes(), b"threefour")

    def test_mid_commit_os_error_restores_both_originals(self):
        staging = self.stage_two()
        real_replace = os.replace
        failed = False

        def replace(source, target):
            nonlocal failed
            if Path(target) == self.vault / "b.md" and not failed:
                failed = True
                raise OSError("simulated disk failure")
            return real_replace(source, target)

        with patch("canvasgate.transactions.os.replace", side_effect=replace), self.assertRaises(WorkflowError):
            self.store.commit("disk-failure", staging.files)
        self.assertEqual((self.vault / "a.md").read_bytes(), b"old A")
        self.assertEqual((self.vault / "b.md").read_bytes(), b"old B")
        self.assertEqual(self.store.read_manifest(self.store.root / "disk-failure")["status"], "rolled_back")

    def crash_transaction(self):
        staging = self.stage_two()
        real_replace = os.replace

        def replace(source, target):
            if Path(target) == self.vault / "b.md":
                raise KeyboardInterrupt("simulated process crash")
            return real_replace(source, target)

        with patch("canvasgate.transactions.os.replace", side_effect=replace), self.assertRaises(KeyboardInterrupt):
            self.store.commit("crash", staging.files)
        self.assertEqual((self.vault / "a.md").read_bytes(), b"new A")

    def test_crash_recovery_restores_partial_commit_and_is_repeatable(self):
        self.crash_transaction()
        with self.assertRaisesRegex(WorkflowError, "recovery"):
            self.store.ensure_ready()
        self.assertEqual(self.store.recover("crash")["status"], "rolled_back")
        self.assertEqual((self.vault / "a.md").read_bytes(), b"old A")
        self.assertEqual((self.vault / "b.md").read_bytes(), b"old B")
        self.assertEqual(self.store.recover("crash")["status"], "rolled_back")

    def test_recovery_does_not_overwrite_external_edit(self):
        self.crash_transaction()
        (self.vault / "a.md").write_bytes(b"external edit")
        with self.assertRaisesRegex(WorkflowError, "External edit"):
            self.store.recover("crash")
        self.assertEqual((self.vault / "a.md").read_bytes(), b"external edit")
        self.assertEqual(self.store.read_manifest(self.store.root / "crash")["status"], "recovery_required")

    def test_staging_conflict_never_overwrites_external_edit(self):
        staging = self.stage_two()
        (self.vault / "a.md").write_bytes(b"external edit")
        with self.assertRaisesRegex(WorkflowError, "changed after staging"):
            self.store.commit("conflict", staging.files)
        self.assertEqual((self.vault / "a.md").read_bytes(), b"external edit")
        self.assertEqual((self.vault / "b.md").read_bytes(), b"old B")

    def test_new_file_removed_when_later_write_fails(self):
        staging = StagingBuffer(self.vault)
        staging.stage("new.md", "OVERWRITE", "new", "a")
        staging.stage("later.md", "OVERWRITE", "later", "b")
        real_replace = os.replace

        def replace(source, target):
            if Path(target) == self.vault / "later.md":
                raise OSError("disk failure")
            return real_replace(source, target)

        with patch("canvasgate.transactions.os.replace", side_effect=replace), self.assertRaises(WorkflowError):
            self.store.commit("new-file-rollback", staging.files)
        self.assertFalse((self.vault / "new.md").exists())

    def test_lock_serializes_writers(self):
        with self.store.lock():
            with self.assertRaisesRegex(WorkflowError, "lock"):
                with self.store.lock():
                    self.fail("second lock acquired")

    def test_committed_transaction_cannot_be_crash_rolled_back(self):
        staging = self.stage_two()
        self.store.commit("done", staging.files)
        with self.assertRaisesRegex(WorkflowError, "committed"):
            self.store.recover("done")


if __name__ == "__main__":
    unittest.main()
