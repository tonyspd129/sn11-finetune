"""DEFAULT system-prompt builder.

The harness imports `build_system_prompt` from this module. To customize, edit this file:
keep a `build_system_prompt(ctx) -> str` that assembles prose + skills into the system message.

`ctx` is a PromptContext: `task`, `base_system`, `skills`, `tool_specs`. Runs ONCE at run
start, so keep the output STABLE across turns (KV-cache friendly).
"""
from __future__ import annotations


def build_system_prompt(ctx) -> str:
    system = ctx.base_system                    # only system.md goes into the system prompt
    # --- skills intentionally kept OUT of the system prompt (system.md only) ---
    # system += ctx.skills.render_always_on()    # always-on skill bodies
    # index = ctx.skills.index()                 # progressive disclosure: catalog only; bodies via load_skill
    # if index:
    #     system += "\n\n" + index
    return system
