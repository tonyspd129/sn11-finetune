"""load_skill — pull the full body of an available skill into context on demand.
Schema: metadata.json.

The system prompt carries a one-line INDEX of every skill; the model calls this tool to
read the full body of the one(s) it decides it needs (progressive disclosure)."""
from scaffold.toolkit import ToolResult


def run(args, ctx):
    name = args.get("name", "")
    lookup = getattr(ctx, "skill_lookup", None)
    if lookup is None:
        return ToolResult("error: skills are not available in this run", is_error=True)
    body = lookup(name)
    if body is None:
        return ToolResult(f"error: no skill named '{name}'", is_error=True)
    return ToolResult(f"# Skill: {name}\n\n{body}")
