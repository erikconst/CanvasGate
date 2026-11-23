"""Per-node backend selection with shared accounting and explicit capabilities."""

from pathlib import Path

from .backends import ApiBackend, CodexBackend, MockBackend, WorkflowError


def normalize_usage(raw):
    if not isinstance(raw, dict):
        return None
    cached = raw.get("cached_input_tokens", raw.get("input_tokens_details", {}).get("cached_tokens"))
    incoming, outgoing = raw.get("input_tokens"), raw.get("output_tokens")
    if any(type(value) is not int or value < 0 for value in (incoming, outgoing, cached)) or cached > incoming:
        return None
    return {"input_tokens": incoming, "cached_input_tokens": cached, "output_tokens": outgoing,
            "total_tokens": incoming + outgoing, "uncached_input_tokens": incoming - cached}


def sum_usage(usages):
    if any(value is None for value in usages):
        return None
    keys = ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens", "uncached_input_tokens")
    return {key: sum(value[key] for value in usages) for key in keys}


class BackendRouter:
    def __init__(self, default, session=None, policy=None):
        self.default = default
        self.session = session
        self.policy = policy
        self.instances = {}
        self.calls = []

    def select(self, config):
        if self.session and self.session.replay:
            return self.default
        if isinstance(self.default, MockBackend):
            return self.default
        model = config.get("model")
        if not model and "max_tokens" not in config:
            return self.default
        provider = "api" if isinstance(self.default, ApiBackend) else "codex"
        name = model
        if model == "codex":
            provider, name = "codex", getattr(self.default, "model", None) if isinstance(self.default, CodexBackend) else None
        elif model and model.startswith("codex/"):
            provider, name = "codex", model[6:]
        elif model and model.startswith("openai/"):
            provider, name = "api", model[7:]
        elif model and "/" in model:
            raise WorkflowError(f"Unsupported model provider: {model}")
        if provider == "codex" and "max_tokens" in config:
            raise WorkflowError("Codex CLI cannot enforce max_tokens; use an openai/ API node for a hard output cap.")
        key = (provider, name, config.get("max_tokens"))
        if key not in self.instances:
            timeout = getattr(self.default, "timeout", 120)
            if provider == "api":
                name = name or getattr(self.default, "model", None)
                cap = min(config.get("max_tokens", 1000), getattr(self.default, "max_output_tokens", 1000))
                events = getattr(self.default, "event_dir", None)
                if events:
                    events = Path(events) / f"provider-{len(self.instances) + 1}"
                self.instances[key] = ApiBackend(name, timeout, cap, getattr(self.default, "reasoning_effort", None), events)
            else:
                events = getattr(self.default, "event_dir", None)
                if events:
                    events = Path(events) / f"provider-{len(self.instances) + 1}"
                self.instances[key] = CodexBackend(name, timeout, getattr(self.default, "reasoning_effort", None), events)
        return self.instances[key]

    def generate(self, config, context, feedback, *, node_id=None, attempt=1):
        backend = self.select(config)
        if self.policy:
            self.policy.check_backend(backend)
        entry = {"model": getattr(backend, "model", None), "backend": type(backend).__name__, "usage": None}
        self.calls.append(entry)
        previous = len(getattr(backend, "runs", []))
        try:
            if self.session:
                return self.session.execute(node_id, attempt, config, context, feedback,
                    lambda: backend.generate(config["prompt"], context, feedback))
            return backend.generate(config["prompt"], context, feedback)
        finally:
            runs = getattr(backend, "runs", [])
            if len(runs) > previous:
                entry["usage"] = normalize_usage(runs[-1].get("usage"))
            elif isinstance(backend, MockBackend):
                entry["usage"] = sum_usage([])
            if self.session:
                effect = self.session.last_effect
                entry.update({key: effect[key] for key in ("idempotency_key", "cached", "replayed") if key in effect})
                if effect.get("cached") or effect.get("replayed"):
                    entry["usage"] = sum_usage([])
                    entry["original_usage"] = effect.get("original_usage")
                else:
                    self.session.record_usage(entry["usage"])

    def usage(self):
        return sum_usage([call["usage"] for call in self.calls])
