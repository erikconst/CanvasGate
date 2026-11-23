"""Verify the installer payload and all three MCP commands with a disposable vault."""

import http.cookiejar
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
import zipfile

from build import OUT, SIGNATURE


def smoke(installer):
    binary = installer.read_bytes()
    footer = len(SIGNATURE) + 8
    assert binary.endswith(SIGNATURE)
    size = struct.unpack("<q", binary[-footer:-len(SIGNATURE)])[0]
    with tempfile.TemporaryDirectory(prefix="canvasgate-package-") as name:
        directory = Path(name)
        with zipfile.ZipFile(io.BytesIO(binary[-footer - size:-footer])) as payload:
            payload.extractall(directory)
        assert (directory / "CanvasGate Studio.exe").is_file()
        assert "PerMonitorV2" in (directory / "CanvasGate Studio.exe.config").read_text(encoding="utf-8")
        python = directory / "runtime/python.exe"
        process = subprocess.Popen(
            [str(python), "-I", "-m", "canvasgate.desktop", "--state", str(directory / "bridge.json"),
             "--vault", str(directory / "vault"), "--demo"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            address = process.stdout.readline().strip()
            if not address.startswith("http://127.0.0.1:"):
                raise RuntimeError("Packaged engine startup failed: " + process.stderr.read())
            opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
            with opener.open(address, timeout=10) as response:
                assert b"agent-guides" in response.read()
            with opener.open(address + "api/bootstrap", timeout=10) as response:
                boot = json.load(response)
            assert boot["desktop"] and boot["default_workflow"]
            with opener.open(address + "api/guides", timeout=10) as response:
                docs = json.load(response)
            assert docs["USER_GUIDE.md"].startswith("# CanvasGate Studio User Guide")
            assert docs["HOW_IT_WORKS.md"].startswith("# How CanvasGate Works")
            with opener.open(address + "api/agents/guide", timeout=10) as response:
                guides = json.load(response)
            assert "Direct Streamable HTTP" in guides["user"]
            assert guides["resource"] == "canvasgate://docs/agent-guide"
            for provider in ("codex", "antigravity", "claude"):
                request = Request(address + "api/agents/verify", json.dumps({"provider": provider}).encode(),
                                  {"Content-Type": "application/json", "X-CSRF-Token": boot["csrf"],
                                   "Origin": address.rstrip("/")})
                with opener.open(request, timeout=20) as response:
                    assert json.load(response)["verified"]
            with opener.open(address + "api/agents", timeout=10) as response:
                rows = json.load(response)
            assert len(rows) == 3 and all(row["verified"] and not row["sessions"] for row in rows)
            print("Packaged desktop engine and guides passed. Three MCP bridges verified end to end.")
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    smoke(OUT / "CanvasGate-Studio-Setup.exe")
