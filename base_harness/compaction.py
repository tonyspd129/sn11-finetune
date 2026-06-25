"""DEFAULT compaction — no-op (returns the conversation unchanged).

The harness imports `make_compaction` from this module. To customize, edit this file:
implement `compact()` to shrink long conversations and keep a `make_compaction()` that
returns your Compaction.
"""
from .context import Compaction


class DefaultCompaction(Compaction):
    def compact(self, messages):
        return messages          # no-op: keep the whole conversation


def make_compaction() -> Compaction:
    return DefaultCompaction()
