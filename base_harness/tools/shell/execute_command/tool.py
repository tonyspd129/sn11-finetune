"""execute_command — run a shell command in the persistent workspace shell. Schema: metadata.json."""
from base_harness.toolkit import ToolResult, truncate


def run(args, ctx):
    cmd = args.get("command", "")
    if not isinstance(cmd, str) or not cmd.strip():
        return ToolResult("error: 'command' is required", is_error=True)
    timeout = min(int(args.get("timeout", 120) or 120), 600)
    out, code, timed_out = ctx.shell.run(cmd, timeout=timeout)
    out, trunc = truncate(out)
    return ToolResult((out or "(no output)") + f"\n[exit_code={code}]",
                      is_error=(code != 0), truncated=trunc,
                      metadata={"exit_code": code, "timed_out": timed_out})
