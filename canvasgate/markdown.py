"""Typed YAML frontmatter and deterministic Markdown context extraction."""

import json
import re

from .backends import WorkflowError


def yaml_value(text):
    try:
        import yaml
    except ImportError as exc:
        raise WorkflowError("YAML support requires PyYAML: python -m pip install -e .") from exc

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise WorkflowError("YAML mappings require unique string keys.")
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for token in yaml.scan(text)):
            raise WorkflowError("YAML anchors and aliases are not supported.")
        value = yaml.load(text, Loader=UniqueLoader)
        json.dumps(value, allow_nan=False)
        return value
    except (yaml.YAMLError, TypeError, ValueError) as exc:
        if isinstance(exc, WorkflowError):
            raise
        raise WorkflowError(f"Invalid or unsupported YAML: {exc}") from exc


def frontmatter(text):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((index for index in range(1, len(lines)) if lines[index].strip() in {"---", "..."}), None)
    if end is None:
        raise WorkflowError("Unterminated YAML frontmatter.")
    metadata = yaml_value("".join(lines[1:end]))
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise WorkflowError("Frontmatter must be a YAML mapping.")
    return metadata, "".join(lines[end + 1:])


def lookup(metadata, key):
    value = metadata
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise WorkflowError(f"Missing YAML key: {key}")
        value = value[part]
    return value


def section(text, title):
    _, body = frontmatter(text)
    lines = body.splitlines()
    headings, fence = [], None
    for index, line in enumerate(lines):
        delimiter = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if delimiter:
            token = delimiter.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        match = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            headings.append((index, len(match[1]), match[2].strip()))
    matches = [heading for heading in headings if heading[2].casefold() == title.casefold()]
    if len(matches) != 1:
        raise WorkflowError(f"SECTION requires one unique heading '{title}'; found {len(matches)}.")
    start, level, _ = matches[0]
    end = next((index for index, other_level, _ in headings if index > start and other_level <= level), len(lines))
    return "\n".join(lines[start:end]).strip()


def render(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
