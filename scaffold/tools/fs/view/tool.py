"""view — read a windowed slice of a text file with line numbers. Schema: metadata.json.
Reads via ctx.shell, so it views the file wherever the shell targets (the container)."""
from scaffold.toolkit import ToolResult, resolve_path


def run(args, ctx):
    path = resolve_path(ctx, args.get("path", ""))
    content = ctx.shell.read_text(path)
    if content is None:
        return ToolResult(f"error: no such file: {path}", is_error=True)
    offset = max(1, int(args.get("offset", 1) or 1))
    limit = int(args.get("limit", 100) or 100)
    lines = content.splitlines(keepends=True)
    chunk = lines[offset - 1: offset - 1 + limit]
    body = "".join(f"{i:>6}\t{ln.rstrip(chr(10))}\n" for i, ln in enumerate(chunk, start=offset))
    remaining = len(lines) - (offset - 1 + limit)
    more = "" if remaining <= 0 else f"... [{remaining} more lines; use offset={offset + limit}] ..."
    return ToolResult((body + more) or "(empty file)", metadata={"total_lines": len(lines)})
