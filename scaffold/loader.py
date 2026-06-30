"""Discovery for the directory-based surfaces (tools and skills).

Conventions
-----------
Tools:   <dir>/<tool>/  with `metadata.json` (name/description/parameters/version) + `tool.py`
         exporting `run(args, ctx)`. (Schema is data; code is separate.)
Skills:  <dir>/**/SKILL.md  with optional `---` frontmatter (name, description, triggers)
         followed by the markdown body.
System:  <dir>/system.md    the system-prompt prose (read as text).

(The single-file surfaces — compaction.py and prompt.py — are NOT loaded here; they are normal
package modules the harness imports directly.)

These are path-based utilities: the caller passes the directories to load. When more than one
dir is passed, LATER dirs override earlier ones by name. A present-but-broken plugin RAISES
(fail fast) — never silently skipped.
"""
from __future__ import annotations

import importlib.util
import json
import os
import uuid
from glob import glob
from pathlib import Path
from typing import Any

from .skill import Skill
from .toolkit import FunctionTool, Tool

DEFAULT_SYSTEM_FILE = "system.md"
DEFAULT_TOOL_METADATA_FILE = "metadata.json"


def load_system_prompt(*dirs: str, filename: str = DEFAULT_SYSTEM_FILE) -> str | None:
    """Read the base system prompt from `<dir>/system.md`. Later dirs OVERRIDE earlier ones
    (so a later dir's system.md overrides an earlier one). Returns None if absent."""
    text: str | None = None
    for d in dirs:
        if not d:
            continue
        p = os.path.join(d, filename)
        if os.path.isfile(p):
            text = Path(p).read_text(encoding="utf-8").strip()
    return text


def _import_path(path: str):
    name = f"_bh_plugin_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import plugin: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def discover_tools(*dirs: str) -> list[Tool]:
    """Discover tools from `<dir>/**/tool.py`. Each tool is a directory holding a SCHEMA file
    `metadata.json` (name / description / parameters / version) and a `tool.py` exporting
    `run(args, ctx)`. Later dirs override by name. A missing metadata.json, invalid JSON, or a
    tool.py without `run` RAISES (fail fast). Wrap the result in a ToolManager."""
    found: dict[str, Tool] = {}
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for path in sorted(glob(os.path.join(d, "**", "tool.py"), recursive=True)):
            meta_path = os.path.join(os.path.dirname(path), DEFAULT_TOOL_METADATA_FILE)
            if not os.path.isfile(meta_path):
                raise FileNotFoundError(f"tool missing {DEFAULT_TOOL_METADATA_FILE}: {path}")
            metadata = json.loads(Path(meta_path).read_text(encoding="utf-8"))   # bad JSON RAISES
            run = getattr(_import_path(path), "run", None)                       # broken tool.py RAISES
            if not callable(run):
                raise ValueError(f"tool.py missing run(args, ctx): {path}")
            tool = FunctionTool(metadata, run)
            found[tool.name] = tool                                             # override by name
    return list(found.values())


def discover_skills(*dirs: str) -> list[Skill]:
    found: dict[str, Skill] = {}
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for path in sorted(glob(os.path.join(d, "**", "SKILL.md"), recursive=True)):
            meta, body = _parse_frontmatter(Path(path).read_text(encoding="utf-8"))   # broken skill RAISES
            name = meta.get("name") or Path(path).parent.name
            found[name] = Skill(
                name=name,
                content=body.strip(),
                description=meta.get("description", ""),
                triggers=meta.get("triggers") or None,
                always_on=str(meta.get("always_on", "")).strip().lower() in ("true", "1", "yes"),
            )
    return list(found.values())


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Minimal frontmatter parser (no YAML dependency): `key: value`, plus list syntax
    `triggers: [a, b]` or `triggers: a, b`."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm, body = text[3:end].strip(), text[end + 4:]
    meta: dict[str, Any] = {}
    for line in fm.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k] = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
        elif k == "triggers" and "," in v:
            meta[k] = [x.strip() for x in v.split(",") if x.strip()]
        else:
            meta[k] = v.strip("\"'")
    return meta, body
