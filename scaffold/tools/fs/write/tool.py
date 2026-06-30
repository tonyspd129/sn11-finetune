"""write — create or overwrite a file with the given content (parent dirs created).
Writes via ctx.shell, so it acts wherever the shell targets (the container). Schema: metadata.json."""
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
        ctx.shell.write_text(path, content)
    except Exception as e:
        return ToolResult(f"error: {e}", is_error=True)
    nlines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    return ToolResult(f"wrote {path} ({len(content)} bytes, {nlines} lines)")
