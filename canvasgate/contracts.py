"""Fail-closed, explicit input/output contracts; no inferred semantic completeness."""

import json
import re

from .backends import WorkflowError
from .security import relative_name


def walk_schema(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef"} and (not isinstance(item, str) or not item.startswith("#")):
                raise WorkflowError("Contracts permit only local JSON Schema references.")
            walk_schema(item)
    elif isinstance(value, list):
        for item in value:
            walk_schema(item)


def validate_contract(contract):
    if not isinstance(contract, dict) or set(contract) - {"input", "output", "description"}:
        raise WorkflowError("A contract contains input, output and optional description.")
    for direction in ("input", "output"):
        rules = contract.get(direction, {})
        if not isinstance(rules, dict) or set(rules) - {"required_sources", "allowed_sources", "required_fields", "required_text", "schema"}:
            raise WorkflowError("Unknown context contract rule.")
        for key in ("allowed_sources", "required_fields", "required_text"):
            if key in rules and (not isinstance(rules[key], list) or any(not isinstance(item, str) or not item for item in rules[key])):
                raise WorkflowError(f"Contract {key} must be a list of nonempty strings.")
        sources = rules.get("required_sources", [])
        if not isinstance(sources, list):
            raise WorkflowError("required_sources must be an array.")
        for source in sources:
            if not isinstance(source, dict) or set(source) - {"path", "sha256", "version", "role"} or not isinstance(source.get("path"), str):
                raise WorkflowError("Source requirements need path and optional sha256/version/role.")
            relative_name(source["path"])
            if "sha256" in source and not re.fullmatch(r"[0-9a-f]{64}", str(source["sha256"])):
                raise WorkflowError("Contract source SHA-256 must have 64 lowercase hexadecimal characters.")
            if "version" in source and (not isinstance(source["version"], dict) or set(source["version"]) != {"key", "equals"} or not isinstance(source["version"]["key"], str)):
                raise WorkflowError("Source version needs key and equals.")
        for name in rules.get("allowed_sources", []):
            relative_name(name)
        if "schema" in rules:
            from jsonschema import Draft202012Validator
            walk_schema(rules["schema"])
            try:
                Draft202012Validator.check_schema(rules["schema"])
            except Exception as exc:
                raise WorkflowError("Invalid contract JSON Schema.") from exc


def field(value, name):
    parts = name.split(".")
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            raise KeyError(name)
        value = value[part]
    return value


def check_contract(rules, value):
    if not rules:
        return {"passed": True, "checks": [], "specified": False}
    checks, errors = [], []
    text, lineage = value.text, value.lineage
    for required in rules.get("required_sources", []):
        path = required["path"]
        actual = lineage.get(path)
        checks.append(f"source:{path}")
        if actual is None:
            errors.append(f"Missing required source: {path}")
            continue
        if "sha256" in required and actual["sha256"] != required["sha256"]:
            errors.append(f"Source hash mismatch: {path}")
        if "version" in required:
            version = required["version"]
            try:
                actual_version = field(actual.get("metadata", {}), version["key"])
                if type(actual_version) is not type(version["equals"]) or actual_version != version["equals"]:
                    raise KeyError(version["key"])
            except KeyError:
                errors.append(f"Source version mismatch: {path}")
        if "role" in required and actual.get("metadata", {}).get("role") != required["role"]:
            errors.append(f"Source role mismatch: {path}")
    if "allowed_sources" in rules:
        extra = set(lineage) - set(rules["allowed_sources"])
        if extra:
            errors.append("Unauthorized input sources: " + ", ".join(sorted(extra)))
        checks.append("authorized_sources")
    for fragment in rules.get("required_text", []):
        checks.append("essential_text")
        if fragment not in text:
            errors.append("Essential text is missing: " + fragment[:80])
    structured = []
    for part in value.context.values():
        try:
            structured.append(json.loads(part["text"]))
        except (ValueError, TypeError):
            pass
    try:
        full = json.loads(text)
        structured.append(full)
    except ValueError:
        full = None
    for name in rules.get("required_fields", []):
        checks.append("field:" + name)
        found = False
        for candidate in structured:
            try:
                field(candidate, name)
                found = True
                break
            except KeyError:
                pass
        if not found:
            errors.append("Required JSON field missing: " + name)
    if "schema" in rules:
        from jsonschema import Draft202012Validator
        data = full if full is not None else {key: json.loads(part["text"]) if part["text"].lstrip().startswith(("{", "[")) else part["text"] for key, part in value.context.items()}
        failures = list(Draft202012Validator(rules["schema"]).iter_errors(data))
        checks.append("json_schema")
        if failures:
            errors.append("JSON Schema failed at " + ", ".join(".".join(map(str, error.absolute_path)) or "root" for error in failures[:5]))
    if errors:
        raise WorkflowError("Context contract failed: " + "; ".join(errors))
    return {"passed": True, "specified": True, "checks": checks}
