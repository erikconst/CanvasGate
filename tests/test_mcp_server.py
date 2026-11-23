import json
from pathlib import Path
import tempfile
import unittest

from canvasgate.mcp_server import handle_request
from canvasgate.web import create_demo


class McpServerTests(unittest.TestCase):
    def test_initialize_and_list_tools(self):
        init = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "canvasgate")
        listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertEqual(
            names,
            {"list_vaults", "list_canvases", "validate_canvas", "run_canvas", "replay_canvas", "open_in_obsidian"},
        )

    def test_validate_run_and_replay_demo_canvas(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            canvas_rel = create_demo(vault)

            listed = handle_request({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_canvases", "arguments": {"vault": str(vault)}},
            })
            self.assertFalse(listed["result"]["isError"])
            canvases = json.loads(listed["result"]["content"][0]["text"])["canvases"]
            self.assertEqual([c["path"] for c in canvases], [canvas_rel])

            validated = handle_request({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "validate_canvas", "arguments": {"vault": str(vault), "canvas": canvas_rel}},
            })
            self.assertFalse(validated["result"]["isError"])
            plan = json.loads(validated["result"]["content"][0]["text"])["plan"]
            self.assertIsInstance(plan, list)
            self.assertTrue(any(item["id"] == "approved" for item in plan))

            simple_canvas = vault / "Simple.canvas"
            simple_canvas.write_text(json.dumps({
                "nodes": [
                    {"id": "t1", "type": "text", "text": "TEXT:\nHello Obsidian"},
                    {"id": "a1", "type": "text", "text": "AGENT:\nSummarize"},
                    {"id": "o1", "type": "text", "text": "OUTPUT: Result"},
                ],
                "edges": [
                    {"id": "e1", "fromNode": "t1", "toNode": "a1"},
                    {"id": "e2", "fromNode": "a1", "toNode": "o1"},
                ],
            }), encoding="utf-8")

            run_resp = handle_request({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "run_canvas", "arguments": {"vault": str(vault), "canvas": "Simple.canvas"}},
            })
            self.assertFalse(run_resp["result"]["isError"])
            run_data = json.loads(run_resp["result"]["content"][0]["text"])
            self.assertEqual(run_data["outcome"], "completed")
            self.assertTrue(Path(run_data["inspect_canvas"]).is_file())

            replay_resp = handle_request({
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "replay_canvas", "arguments": {"vault": str(vault), "run_id": run_data["run_id"]}},
            })
            self.assertFalse(replay_resp["result"]["isError"])
            replay_data = json.loads(replay_resp["result"]["content"][0]["text"])
            self.assertEqual(replay_data["external_calls"], 0)
            self.assertTrue(replay_data["matches_original"])

    def test_open_in_obsidian_builds_uri_without_launching(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            canvas_rel = create_demo(vault)
            resp = handle_request({
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "open_in_obsidian", "arguments": {"vault": str(vault), "file": canvas_rel, "launch": False}},
            })
            self.assertFalse(resp["result"]["isError"])
            data = json.loads(resp["result"]["content"][0]["text"])
            self.assertTrue(data["uri"].startswith("obsidian://open?vault="))
            self.assertFalse(data["launched"])
