"""write — create or overwrite a file with the given content (parent dirs created). Schema: metadata.json."""
import os

from scaffold.toolkit import ToolResult, resolve_path


def run(args, ctx):
    path = resolve_path(ctx, args.get("path", ""))
    if not path:
        return ToolResult("error: 'path' is required", is_error=True)
    content = args.get("content")
    if content is None:
        return ToolResult("error: 'content' is required", is_error=True)
    if not isinstance(content, str):
        content = str(content)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        return ToolResult(f"error: {e}", is_error=True)
    nlines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    return ToolResult(f"wrote {path} ({len(content)} bytes, {nlines} lines)")
