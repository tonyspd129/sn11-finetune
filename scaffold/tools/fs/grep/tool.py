"""grep — regex search across file CONTENTS (ripgrep if present, else grep). Schema: metadata.json.
Runs via ctx.shell, so the search executes wherever the shell targets (the container)."""
import shlex

from scaffold.toolkit import ToolResult, resolve_path


def run(args, ctx):
    pattern = args.get("pattern", "")
    if not pattern:
        return ToolResult("error: 'pattern' is required", is_error=True)
    path = resolve_path(ctx, args.get("path", ".") or ".")
    maxr = int(args.get("max_results", 50) or 50)
    q, pq = shlex.quote(pattern), shlex.quote(path)
    # rg-vs-grep availability is decided INSIDE the shell's target (the container), not here
    cmd = (f"if command -v rg >/dev/null 2>&1; then rg -n --no-heading -S -- {q} {pq}; "
           f"else grep -rnI -- {q} {pq}; fi 2>/dev/null")
    out, _code, _to = ctx.shell.run(cmd, timeout=60)
    lines = (out or "").splitlines()
    if not lines:
        return ToolResult("(no matches)")
    more = "" if len(lines) <= maxr else f"\n... [{len(lines) - maxr} more matches] ..."
    return ToolResult("\n".join(lines[:maxr]) + more, metadata={"matches": len(lines)})
