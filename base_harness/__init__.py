"""base_harness — a pure, extensible agent harness.

The harness manages the conversation between an OpenAI-compatible LLM and a set of tools,
and exports the full session at the end (no `submit`). Verification lives outside it.

The harness loads everything from THIS package's own files (no override args):
    tools/<name>/{metadata.json, tool.py}   the tools
    skills/**/SKILL.md  +  skills/system.md  the skills + system prompt
    compaction.py                            the compaction module
    prompt.py                                the system-prompt builder
To customize, EDIT those files (a miner ships their own copy of the package). Build with
`Harness()`. A present-but-broken file RAISES (fail fast).
"""
from .context import Compaction, ContextManager, NoOpCompaction
from .harness import Harness
from .llm import LLMClient
from .loader import discover_skills, discover_tools, load_system_prompt
from .promptkit import PromptContext
from .session import Session
from .skill import Skill, SkillManager
from .toolkit import (
    FunctionTool,
    GuardedRedirect,
    RunContext,
    Shell,
    Tool,
    ToolManager,
    ToolResult,
    is_internal_host,
    resolve_path,
    truncate,
)

__all__ = [
    "Harness", "LLMClient", "Session",
    "Tool", "FunctionTool", "ToolResult", "ToolManager", "RunContext", "Shell",
    "truncate", "resolve_path", "is_internal_host", "GuardedRedirect",
    "Compaction", "NoOpCompaction", "ContextManager",
    "Skill", "SkillManager", "PromptContext",
    "discover_tools", "discover_skills", "load_system_prompt",
]
