"""Serve the snake comparison on localhost with locally pinned Three.js assets."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import shutil
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

from .snake_benchmark import OUTPUT


def prepare_vendor():
    package = OUTPUT / "node_modules/three"
    if not package.is_dir():
        raise SystemExit("Run npm.cmd install in benchmarks/snake first.")
    vendor = OUTPUT / "vendor"
    vendor.mkdir(exist_ok=True)
    for filename in ("three.module.js", "three.core.js"):
        shutil.copy2(package / "build" / filename, vendor / filename)
    shutil.copy2(package / "examples/jsm/controls/OrbitControls.js", vendor / "OrbitControls.js")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8873)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--open", action="store_true", help="Open the interactive viewer; reuse an already running Snake Lab")
    args = parser.parse_args()
    prepare_vendor()
    if args.prepare_only:
        print(OUTPUT / "index.html")
        return
    url = f"http://127.0.0.1:{args.port}/"
    if args.open:
        try:
            with urlopen(url, timeout=2) as response:
                existing = response.read(8192)
            if b"Snake Lab" not in existing or b"CanvasGate" not in existing:
                raise SystemExit("Port is in use by another application; choose --port.")
            webbrowser.open(url)
            print(f"Opened existing Snake Lab: {url}")
            return
        except (URLError, TimeoutError):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(SimpleHTTPRequestHandler, directory=str(OUTPUT)))
    print(f"Snake Lab: {url}", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
