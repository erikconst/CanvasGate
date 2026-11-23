import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

from canvasgate.agent_bridge import AgentConnections, GUIDE_URI, PROVIDERS
from canvasgate.web import StudioServer


class DesktopMcpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        vault = Path(self.temp.name)
        self.agents = AgentConnections(vault / "test-bridge.json", Path(sys.executable))
        self.server = StudioServer(("127.0.0.1", 0), vault, agents=self.agents)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.close)
        self.session = None
        self.number = 0

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.server.studio.pool.shutdown(wait=True)
        self.thread.join()

    def rpc(self, method, params=None, *, notification=False, token=True, request_headers=None):
        self.number += 1
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            message["id"] = self.number
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if token:
            headers["Authorization"] = "Bearer " + self.agents.token
        headers.update(request_headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("POST", "/mcp", json.dumps(message), headers)
            response = connection.getresponse()
            text = response.read()
            if response.getheader("Mcp-Session-Id"):
                self.session = response.getheader("Mcp-Session-Id")
            return response.status, json.loads(text) if text else None
        finally:
            connection.close()

    def initialize(self, provider):
        self.session = None
        status, message = self.rpc("initialize", {"protocolVersion": "2025-06-18",
            "clientInfo": {"name": PROVIDERS[provider], "version": "test"}}, request_headers={"X-CanvasGate-Client": provider})
        self.assertEqual(status, 200)
        self.assertEqual(message["result"]["protocolVersion"], "2025-06-18")
        self.assertIn(GUIDE_URI, message["result"]["instructions"])
        self.assertEqual(self.rpc("notifications/initialized", notification=True)[0], 202)

    def tool(self, name, arguments=None):
        status, response = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        self.assertEqual(status, 200)
        result = response["result"]
        return result["isError"], result["content"][0]["text"]

    def call(self, name, arguments=None):
        error, value = self.tool(name, arguments)
        self.assertFalse(error, value)
        return json.loads(value)

    def wait_for_job(self, job_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.call("canvasgate_run_status", {"job_id": job_id})
            if result["state"] not in {"QUEUED", "RUNNING"}:
                return result
            time.sleep(.05)
        self.fail("MCP job did not finish")

    def test_authentication_and_browser_origin(self):
        self.assertEqual(self.rpc("initialize", token=False)[0], 401)
        origin = f"http://127.0.0.1:{self.server.server_port}"
        self.assertEqual(self.rpc("initialize", request_headers={"Origin": origin})[0], 401)
        self.assertEqual(self.rpc("tools/list")[0], 404)

    def test_discovery_and_guides_for_each_connector(self):
        for provider, name in PROVIDERS.items():
            self.initialize(provider)
            self.assertIn("canvasgate_status", {tool["name"] for tool in self.rpc("tools/list")[1]["result"]["tools"]})
            row = next(item for item in self.agents.status() if item["id"] == provider)
            self.assertEqual(row["sessions"], [name])
            guide = self.rpc("resources/read", {"uri": GUIDE_URI})[1]["result"]["contents"][0]
            self.assertIn("canvasgate_validate_workflow", guide["text"])
            self.assertTrue(self.call("canvasgate_status")["ready"])

    def test_agent_simulation_and_replay_are_scoped_and_idempotent(self):
        self.initialize("codex")
        path = self.call("canvasgate_list_workflows")["workflows"][0]
        self.assertTrue(self.call("canvasgate_validate_workflow", {"path": path})["valid"])
        self.assertTrue(self.tool("canvasgate_validate_workflow", {"path": "../outside.canvas"})[0])
        args = {"path": path, "operation_key": "mcp-test-preview"}
        job = self.call("canvasgate_simulate_workflow", args)
        self.assertEqual(self.call("canvasgate_simulate_workflow", args)["job_id"], job["job_id"])
        preview = self.wait_for_job(job["job_id"])
        self.assertEqual(preview["outcome"], "completed")
        self.assertEqual(preview["external_calls"], 0)
        self.assertEqual(preview["transaction_state"], "PREVIEW")
        self.assertFalse((Path(self.temp.name) / "Studio/Output/Plan.md").exists())
        replay = self.call("canvasgate_replay_run", {"run_id": job["run_id"], "operation_key": "mcp-test-replay"})
        self.assertTrue(self.wait_for_job(replay["job_id"])["replay_comparison"]["matches"])
