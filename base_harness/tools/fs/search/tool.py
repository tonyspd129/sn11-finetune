"""search — regex search across files (ripgrep if present, else grep). Schema: metadata.json."""
import shutil
import subprocess

from base_harness.toolkit import ToolResult, resolve_path


def run(args, ctx):
    pattern = args.get("pattern", "")
    if not pattern:
        return ToolResult("error: 'pattern' is required", is_error=True)
    path = resolve_path(ctx, args.get("path", ".") or ".")
    maxr = int(args.get("max_results", 50) or 50)
    rg = shutil.which("rg")
    cmd = [rg, "-n", "--no-heading", "-S", "--", pattern, path] if rg \
        else ["grep", "-rnI", "--", pattern, path]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        return ToolResult(f"error: {e}", is_error=True)
    lines = (p.stdout or "").splitlines()
    if not lines:
        return ToolResult("(no matches)")
    more = "" if len(lines) <= maxr else f"\n... [{len(lines) - maxr} more matches] ..."
    return ToolResult("\n".join(lines[:maxr]) + more, metadata={"matches": len(lines)})
