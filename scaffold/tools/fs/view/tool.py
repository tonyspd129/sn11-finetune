"""view — read a windowed slice of a text file with line numbers. Schema: metadata.json."""
import os

from scaffold.toolkit import ToolResult, resolve_path


def run(args, ctx):
    path = resolve_path(ctx, args.get("path", ""))
    if not os.path.isfile(path):
        return ToolResult(f"error: no such file: {path}", is_error=True)
    offset = max(1, int(args.get("offset", 1) or 1))
    limit = int(args.get("limit", 100) or 100)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return ToolResult(f"error: {e}", is_error=True)
    chunk = lines[offset - 1: offset - 1 + limit]
    body = "".join(f"{i:>6}\t{ln.rstrip(chr(10))}\n" for i, ln in enumerate(chunk, start=offset))
    remaining = len(lines) - (offset - 1 + limit)
    more = "" if remaining <= 0 else f"... [{remaining} more lines; use offset={offset + limit}] ..."
    return ToolResult((body + more) or "(empty file)", metadata={"total_lines": len(lines)})
