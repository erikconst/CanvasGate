"""Package CanvasGate Studio with an isolated Python runtime for Windows x64."""

from hashlib import sha256
import importlib.metadata
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "desktop"
OUT = ROOT / "dist"
SDK_HASH = "ef128016dd1e51c59178c827ed5b8aa3322c57afa8675d930f8109505542ad74"
SIGNATURE = b"CANVASGATE_SETUP_04"


def make_icon(path):
    icon = Image.new("RGBA", (256, 256))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((12, 12, 244, 244), 45, fill="#262528", outline="#d2ab75", width=9)
    draw.line([(73, 80), (129, 80), (129, 174), (183, 174)], fill="#ab8758", width=13)
    for x, y in [(73, 80), (129, 127), (183, 174)]:
        draw.rounded_rectangle((x - 21, y - 21, x + 21, y + 21), 7, fill="#d2ab75")
    icon.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def copy_runtime(dest):
    source = Path(sys.base_prefix)
    for name in ("python.exe", "python3.dll", f"python{sys.version_info.major}{sys.version_info.minor}.dll",
                 "vcruntime140_1.dll", "LICENSE.txt"):
        shutil.copy2(source / name, dest / name)
    shutil.copytree(source / "DLLs", dest / "DLLs", ignore=shutil.ignore_patterns(
        "_tkinter.pyd", "tcl*.dll", "tk*.dll", "*.cat"))
    shutil.copytree(source / "Lib", dest / "Lib", ignore=shutil.ignore_patterns(
        "site-packages", "__pycache__", "test", "tests", "tkinter", "idlelib", "turtledemo", "ensurepip"))
    packages = dest / "Lib/site-packages"
    packages.mkdir()
    for name in ("PyYAML", "jsonschema", "jsonschema-specifications", "attrs", "referencing", "rpds-py", "typing-extensions"):
        distribution = importlib.metadata.distribution(name)
        for item in distribution.files:
            if ".." in item.parts or "__pycache__" in item.parts:
                continue
            target = packages / item
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(distribution.locate_file(item), target)
    shutil.copytree(ROOT / "canvasgate", packages / "canvasgate", ignore=shutil.ignore_patterns("__pycache__"))
    (dest / f"python{sys.version_info.major}{sys.version_info.minor}._pth").write_text(
        "Lib\nDLLs\nLib/site-packages\n", encoding="ascii")
    subprocess.run([str(dest / "python.exe"), "-I", "-c", "import canvasgate.desktop, jsonschema, yaml"],
                   check=True, cwd=dest)


def compile_app(source, output, icon, references=(), extra=()):
    compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
                    f"/out:{output}", f"/win32icon:{icon}", *[f"/r:{file}" for file in references],
                    *extra, str(SOURCE / source)], check=True)


def build(sdk):
    if sha256(sdk.read_bytes()).hexdigest() != SDK_HASH:
        raise ValueError("WebView2 SDK SHA-256 mismatch.")
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUT, prefix="desktop-build-") as work:
        work = Path(work)
        app = work / "app"
        runtime = app / "runtime"
        runtime.mkdir(parents=True)
        icon = work / "CanvasGate.ico"
        make_icon(icon)
        controls = ["Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll"]
        with zipfile.ZipFile(sdk) as archive:
            for sdk_entry in [*(f"lib/net462/{name}" for name in controls),
                              "runtimes/win-x64/native/WebView2Loader.dll", "LICENSE.txt", "NOTICE.txt"]:
                target = Path(sdk_entry).name
                if target.endswith(".txt"):
                    target = "WebView2-" + target
                (app / target).write_bytes(archive.read(sdk_entry))
        copy_runtime(runtime)
        setup_references = ["System.IO.Compression.dll", "System.IO.Compression.FileSystem.dll"]
        manifest = f"/win32manifest:{SOURCE / 'Windows.manifest'}"
        compile_app("CanvasGate.cs", app / "CanvasGate Studio.exe", icon, [app / name for name in controls], [manifest])
        shutil.copy2(SOURCE / "CanvasGate.exe.config", app / "CanvasGate Studio.exe.config")
        compile_app("Setup.cs", app / "Uninstall.exe", icon, setup_references, ["/define:UNINSTALL", manifest])
        stub = work / "setup.exe"
        compile_app("Setup.cs", stub, icon, setup_references, [manifest])
        archive = work / "payload.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as payload:
            for file in sorted(app.rglob("*")):
                if file.is_file() and "__pycache__" not in file.parts:
                    payload.write(file, file.relative_to(app).as_posix())
        installer = OUT / "CanvasGate-Studio-Setup.exe"
        with installer.open("wb") as stream, archive.open("rb") as package:
            stream.write(stub.read_bytes())
            shutil.copyfileobj(package, stream)
            stream.write(struct.pack("<q", archive.stat().st_size))
            stream.write(SIGNATURE)
        print(f"{installer}\nSHA-256: {sha256(installer.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    build(Path(sys.argv[1]))
