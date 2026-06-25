"""Example: build and inspect the harness.

The harness loads its tools / skills / system.md / compaction.py / prompt.py from the
base_harness package itself — there are **no override arguments**. To customize, EDIT those
files in your copy of the package:

    base_harness/tools/<name>/{metadata.json, tool.py}
    base_harness/skills/<name>/SKILL.md   and   base_harness/skills/system.md
    base_harness/compaction.py
    base_harness/prompt.py

`examples/miner_plugins/` holds reference versions of each (a terraform tool, a skill, a custom
system.md, a SlidingWindow compaction, an XML-framing prompt builder) — copy them into the
package locations above to use them.

Run:  OPENROUTER_API_KEY=... python -m base_harness.example_miner
"""
from __future__ import annotations

from base_harness import Harness


if __name__ == "__main__":
    h = Harness()
    print("tools     :", h.tools.names())
    print("skills    :", [s.name for s in h.skills.skills])
    print("compaction:", type(h.compaction).__name__)
    print("builder   :", h.prompt_builder.__name__)
    print("prompt len:", len(h.system_prompt), "chars")
    # session = h.run("Fix /app so `make` succeeds, then run the tests.")
    # session.export("session.json")
