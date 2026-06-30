"""edit — replace a unique string in a file, or create a file. Schema: metadata.json.
Reads/writes via ctx.shell, so it acts wherever the shell targets (the container)."""
from scaffold.toolkit import ToolResult, resolve_path


def run(args, ctx):
    path = resolve_path(ctx, args.get("path", ""))
    new = args.get("new", "")
    old = args.get("old")
    if not path:
        return ToolResult("error: 'path' is required", is_error=True)
    if old in (None, ""):
        ctx.shell.write_text(path, new)
        return ToolResult(f"created {path} ({len(new)} bytes)")
    content = ctx.shell.read_text(path)
    if content is None:
        return ToolResult(f"error: no such file: {path}", is_error=True)
    n = content.count(old)
    if n == 0:
        return ToolResult("error: 'old' not found", is_error=True)
    if n > 1:
        return ToolResult(f"error: 'old' matches {n} times; make it unique", is_error=True)
    ctx.shell.write_text(path, content.replace(old, new, 1))
    return ToolResult(f"edited {path}")
