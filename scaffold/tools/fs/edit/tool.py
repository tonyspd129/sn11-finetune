"""edit — replace a unique string in a file, or create a file. Schema: metadata.json."""
import os

from scaffold.toolkit import ToolResult, resolve_path


def run(args, ctx):
    path = resolve_path(ctx, args.get("path", ""))
    new = args.get("new", "")
    old = args.get("old")
    if not path:
        return ToolResult("error: 'path' is required", is_error=True)
    if old in (None, ""):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        return ToolResult(f"created {path} ({len(new)} bytes)")
    if not os.path.isfile(path):
        return ToolResult(f"error: no such file: {path}", is_error=True)
    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    n = content.count(old)
    if n == 0:
        return ToolResult("error: 'old' not found", is_error=True)
    if n > 1:
        return ToolResult(f"error: 'old' matches {n} times; make it unique", is_error=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.replace(old, new, 1))
    return ToolResult(f"edited {path}")
