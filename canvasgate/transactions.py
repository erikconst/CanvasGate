"""Recoverable vault writes: staging, conflict checks, per-file replace, rollback.

This is NOT a multi-file atomic visibility primitive. The journal makes partial
commits detectable and recoverable after a process crash; concurrent editors may
observe intermediate files. A lock serializes cooperating CanvasGate writers.
"""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import tempfile
import time

from .backends import WorkflowError


def confined_path(vault, name, *, writing=False):
    if not isinstance(name, str) or not name or "\x00" in name:
        raise WorkflowError("A non-empty vault-relative path is required.")
    relative = Path(name)
    if relative.is_absolute() or PureWindowsPath(name).drive or ".." in relative.parts:
        raise WorkflowError("Absolute paths and parent traversal are not allowed.")
    if writing and any(part.lower() in {".git", ".obsidian", ".canvasgate"} for part in relative.parts):
        raise WorkflowError("WRITE cannot target application or transaction metadata.")
    target = (vault / relative).resolve()
    if not target.is_relative_to(vault) or target == vault:
        raise WorkflowError("Path escapes the vault, possibly through a symlink or junction.")
    if writing and any(part.lower() in {".git", ".obsidian", ".canvasgate"} for part in target.relative_to(vault).parts):
        raise WorkflowError("WRITE cannot resolve into application or transaction metadata.")
    if target.exists() and not target.is_file():
        raise WorkflowError("Target is not a regular file.")
    if writing and target.suffix.lower() not in {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".csv", ".toml"}:
        raise WorkflowError("WRITE supports text artifacts: md, txt, json, yaml, yml, py, csv, toml.")
    return target


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def read_optional(path):
    return path.read_bytes() if path.exists() else None


def atomic_bytes(path, data, mode=None):
    """Same-directory fsynced temporary file followed by atomic replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".canvasgate-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            temporary.chmod(mode)
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 7:
                    raise
                time.sleep(.005 * (2 ** attempt))
    finally:
        temporary.unlink(missing_ok=True)


class TransactionStore:
    def __init__(self, vault):
        self.vault = Path(vault).resolve()
        self.root = self.metadata_path("transactions")

    def metadata_path(self, suffix):
        if Path(suffix).is_absolute() or ".." in Path(suffix).parts:
            raise WorkflowError("Invalid metadata path.")
        from .security import reject_links
        reject_links(self.vault, ".canvasgate/" + suffix)
        path = (self.vault / ".canvasgate" / suffix).resolve()
        if not path.is_relative_to(self.vault):
            raise WorkflowError("CanvasGate metadata directory escapes the vault.")
        return path

    @contextmanager
    def lock(self, name="writer.lock"):
        path = self.metadata_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise WorkflowError("Another CanvasGate writer holds the vault lock.") from exc
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def validate_id(run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
            raise WorkflowError("Run ID must contain only letters, digits, underscore or hyphen.")

    def read_manifest(self, directory):
        try:
            return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise WorkflowError(f"Unreadable transaction journal: {directory.name}.") from exc

    def save_manifest(self, directory, manifest):
        atomic_bytes(directory / "manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

    def ensure_ready(self):
        if not self.root.exists():
            return
        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            manifest = self.read_manifest(directory)
            if manifest.get("status") not in {"committed", "rolled_back"}:
                raise WorkflowError(f"Transaction {directory.name} requires recovery before another run can write.")

    def rollback(self, directory, manifest):
        """Never overwrite content modified externally since the attempted commit."""
        problems = []
        for entry in reversed(manifest["files"]):
            try:
                path = confined_path(self.vault, entry["path"], writing=True)
                if str(path) != entry["resolved"]:
                    raise WorkflowError(f"Target path changed since commit preparation: {entry['path']}")
                current = digest(read_optional(path))
                if current == entry["old_hash"]:
                    continue
                if current != entry["new_hash"]:
                    raise WorkflowError(f"External edit prevents recovery: {entry['path']}")
                old = (directory / entry["backup"]).read_bytes() if entry["backup"] else None
                if digest(old) != entry["old_hash"]:
                    raise WorkflowError("Backup hash mismatch.")
                if old is None:
                    path.unlink()
                else:
                    atomic_bytes(path, old, entry["mode"])
            except (WorkflowError, OSError) as exc:
                problems.append(str(exc))
        manifest["status"] = "recovery_required" if problems else "rolled_back"
        manifest["recovery_errors"] = problems
        self.save_manifest(directory, manifest)
        if problems:
            raise WorkflowError("Recovery incomplete: " + "; ".join(problems))

    def recover(self, run_id):
        self.validate_id(run_id)
        directory = self.metadata_path("transactions/" + run_id)
        with self.lock():
            manifest = self.read_manifest(directory)
            if manifest.get("status") == "committed":
                raise WorkflowError("A committed transaction cannot be rolled back by crash recovery.")
            if manifest.get("status") != "rolled_back":
                self.rollback(directory, manifest)
        return manifest

    def commit(self, run_id, staged):
        self.validate_id(run_id)
        if not staged:
            return []
        with self.lock():
            self.ensure_ready()
            directory = self.metadata_path("transactions/" + run_id)
            directory.mkdir(parents=True, exist_ok=False)
            manifest = {"run_id": run_id, "status": "preparing", "files": []}
            self.save_manifest(directory, manifest)
            try:
                for number, entry in enumerate(staged.values()):
                    path = confined_path(self.vault, entry["path"], writing=True)
                    if str(path) != entry["resolved"] or read_optional(path) != entry["original"]:
                        raise WorkflowError(f"File changed after staging: {entry['path']}")
                    original, content = entry["original"], entry["content"]
                    backup = f"{number}.old" if original is not None else None
                    if backup:
                        atomic_bytes(directory / backup, original)
                    atomic_bytes(directory / f"{number}.new", content)
                    manifest["files"].append({"path": entry["path"], "resolved": str(path), "old_hash": digest(original),
                        "new_hash": digest(content), "backup": backup, "mode": entry["mode"]})
                manifest["status"] = "prepared"
                self.save_manifest(directory, manifest)
                manifest["status"] = "applying"
                self.save_manifest(directory, manifest)
                for number, entry in enumerate(manifest["files"]):
                    path = confined_path(self.vault, entry["path"], writing=True)
                    if str(path) != entry["resolved"]:
                        raise WorkflowError(f"Target path changed during commit: {entry['path']}")
                    if digest(read_optional(path)) != entry["old_hash"]:
                        raise WorkflowError(f"Concurrent edit detected: {entry['path']}")
                    content = (directory / f"{number}.new").read_bytes()
                    if digest(content) != entry["new_hash"]:
                        raise WorkflowError("Staged content hash mismatch.")
                    atomic_bytes(path, content, entry["mode"])
                manifest["status"] = "committed"
                self.save_manifest(directory, manifest)
                return [entry["path"] for entry in manifest["files"]]
            except Exception as exc:
                if manifest["status"] in {"applying", "committed"}:
                    self.rollback(directory, manifest)
                else:
                    manifest["status"] = "rolled_back"
                    self.save_manifest(directory, manifest)
                raise WorkflowError(f"Commit failed; no new writes were retained: {exc}") from exc


class StagingBuffer:
    def __init__(self, vault):
        self.vault = Path(vault).resolve()
        self.files = {}
        self.mutations = []

    def stage(self, name, mode, text, node_id):
        path = confined_path(self.vault, name, writing=True)
        key = str(path)
        if key not in self.files:
            original = read_optional(path)
            self.files[key] = {"path": name, "resolved": key, "original": original,
                               "content": original or b"", "mode": stat.S_IMODE(path.stat().st_mode) if path.exists() else None}
        entry = self.files[key]
        content = text.encode("utf-8")
        if mode == "APPEND":
            entry["content"] += content
        elif mode == "OVERWRITE":
            entry["content"] = content
        else:
            raise WorkflowError(f"Unknown write mode: {mode}")
        self.mutations.append({"node_id": node_id, "path": name, "mode": mode, "bytes": len(content)})
