"""web_fetch — fetch a URL's readable text. Allowlist + internal-IP + redirect guarded.
Schema: metadata.json.

NOTE: this is defense-in-depth only. Real egress control must be enforced at the
network layer, because the agent has a full shell via execute_command."""
import re
import urllib.request
from urllib.parse import urlparse

from base_harness.toolkit import GuardedRedirect, ToolResult, is_internal_host, truncate


def run(args, ctx):
    url = args.get("url", "")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ToolResult("error: only http/https URLs are allowed", is_error=True)
    host = (parsed.hostname or "").lower()
    if not host:
        return ToolResult("error: invalid url", is_error=True)
    allow = ctx.config.get("web_allowlist")     # None = allow (dev); list = allowed hosts
    if allow is not None and not any(host == d or host.endswith("." + d) for d in allow):
        return ToolResult(f"error: host '{host}' not in allowlist", is_error=True)
    if is_internal_host(host):
        return ToolResult("error: refusing to fetch internal/loopback/metadata address", is_error=True)
    try:
        opener = urllib.request.build_opener(GuardedRedirect(allow))
        req = urllib.request.Request(url, headers={"User-Agent": "base-harness/0.1"})
        with opener.open(req, timeout=30) as r:  # noqa: S310 (scheme+host+redirect guarded)
            raw = r.read(2_000_000).decode("utf-8", "replace")
    except Exception as e:
        return ToolResult(f"error: {e}", is_error=True)
    text = re.sub(r"<(script|style).*?</\1>", " ", raw, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    out, trunc = truncate(text, max_chars=6000, max_lines=10_000)
    return ToolResult(out, truncated=trunc)
