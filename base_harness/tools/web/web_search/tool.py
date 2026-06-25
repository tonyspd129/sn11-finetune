"""web_search — pluggable web search (operator wires config['search_fn']). Schema: metadata.json."""
from base_harness.toolkit import ToolResult


def run(args, ctx):
    fn = ctx.config.get("search_fn")            # callable(query: str, num: int) -> str
    if fn is None:
        return ToolResult("web_search is not configured (set config['search_fn']).", is_error=True)
    try:
        return ToolResult(str(fn(args.get("query", ""), int(args.get("num", 5) or 5))))
    except Exception as e:
        return ToolResult(f"error: {e}", is_error=True)
