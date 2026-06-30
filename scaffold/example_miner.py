"""Example: build and inspect the harness.

The harness loads its tools / skills / system.md / compaction.py / prompt.py from the
scaffold package itself — there are **no override arguments**. To customize, EDIT those
files in your copy of the package:

    scaffold/tools/<name>/{metadata.json, tool.py}
    scaffold/skills/<name>/SKILL.md   and   scaffold/skills/system.md
    scaffold/compaction.py
    scaffold/prompt.py

`examples/miner_plugins/` holds reference versions of each (a terraform tool, a skill, a custom
system.md, a SlidingWindow compaction, an XML-framing prompt builder) — copy them into the
package locations above to use them.

Run:  OPENROUTER_API_KEY=... python -m scaffold.example_miner
"""
from __future__ import annotations

from scaffold import Harness


if __name__ == "__main__":
    h = Harness()
    print("tools     :", h.tools.names())
    print("skills    :", [s.name for s in h.skills.skills])
    print("compaction:", type(h.compaction).__name__)
    print("builder   :", h.prompt_builder.__name__)
    print("prompt len:", len(h.system_prompt), "chars")
    # session = h.run("Fix /app so `make` succeeds, then run the tests.")
    # session.export("session.json")
