# SN11 — Miner Guide

You compete by submitting a **fine-tuned Qwen3.6-35B-A3B model + an agent harness**. Each
cycle they are scored on a fresh, private benchmark of coding & DevOps tasks. Beat the standing
public best and you earn the subnet's emission for the next cycle.

> Full context: eval lifecycle → [sn11-finetune.md](sn11-finetune.md) · rules & audit →
> [security-and-incentives.md](security-and-incentives.md) · harness → [base_harness/README.md](base_harness/README.md)

---

## 1. What you submit

A pinned pair (commit/hash), committed via **commit-reveal** during the submission window:

1. **Model** — fine-tuned Qwen3.6-35B-A3B weights (HF repo + revision) **+ serving config**
   (`--tool-call-parser`, `--reasoning-parser`, chat template, max context). You own the
   parser; the validator serves your weights with vLLM.
2. **Harness** — your edited copy of [base_harness/](base_harness/). The agent loop, LLM
   client, loaders, and session export are **fixed**; you customize the five surfaces below.

---

## 2. What you control — the five surfaces

Edit these files in your harness copy. Nothing to wire up — the harness loads its own files.

| Surface | File(s) | Contract |
|---|---|---|
| **System prompt** | `skills/system.md` | the base prose |
| **Skills** | `skills/<name>/SKILL.md` | frontmatter (name/description/triggers/always_on) + body; loaded on demand via `load_skill`, or `always_on` to inject every turn |
| **Tools** | `tools/<name>/{metadata.json, tool.py}` | `metadata.json` = JSON schema; `tool.py` exports `run(args, ctx)` |
| **Compaction** | `compaction.py` | exports `make_compaction()` → a `Compaction` |
| **Prompt builder** | `prompt.py` | exports `build_system_prompt(ctx)` → the system message |

**Fail fast:** a missing/broken file (won't import, invalid JSON, missing the expected export)
**rejects your submission at load**. Test `Harness()` builds before you submit.

---

## 3. The rules — what wins, what gets you flagged

**Capability, not answers.** Your scaffold (prompt, skills, tools, compaction, prompt builder)
may encode **general, transferable capability** — how to use tools, methodology, domain best
practice. It may **not** encode **task-specific answers** — solution lookups, canned commands,
memorized outputs. That isn't fine-tuning; it's cheating, and it's caught:

- **The model must do the work** — a *model-ablation probe* runs your harness with a dummy
  model; if it still solves, your scaffold is carrying answers → disqualified.
- **General, not narrow** — a *distribution-of-lift test* compares your scaffold to the
  baseline; broad modest lift is rewarded, a spiky lift on a few tasks is penalized.
- **Fresh tasks** — scoring tasks are private and new each cycle; memorizing published tasks
  is worthless (they're never re-scored).
- **Static audit** — system prompt, skills, `prompt.py`, tool descriptions, and code are
  scanned for embedded answers / task-pattern matching.

---

## 4. How to actually improve (the real levers)

1. **Fine-tune the model** — agentic coding/DevOps trajectories (rejection-sampling on
   verifier-passing rollouts; distillation for tasks pass@k≈0). This is where capability lives.
2. **Improve the scaffold generally** — sharper tools, better skills + descriptions, smarter
   compaction, a stronger prompt builder. Must help an *open* class of tasks.
3. **Serving config** — a clean tool-call parser so the model never emits invalid calls.
4. **Train/serve consistency** — assemble `system.md` + skills the same way your fine-tuning
   data did (format match matters more than markdown-vs-XML in the abstract).

---

## 5. The cycle (2 weeks)

```
Week 1: submit (commit-reveal)  →  screening (5–10 tasks, cheap gate)
        →  full eval (50+ FRESH private tasks)  →  integrity audit  →  score
Winner earns emission for the NEXT cycle.
Cycle end: benchmark + all solutions are PUBLISHED.
```

Publication is your advantage *and* your bar: study last cycle's winners, then **beat the public
best by a margin on tasks you've never seen**. Ties/copies don't win (earliest-wins + ε-margin).

**Scoring:** each task is graded `s_t ∈ [0,1]` (partial credit — half-solving counts), your
submission score is `S = mean(s_t)` over the benchmark, and it is **capability-only** — tokens,
turns, and latency do **not** affect your score this phase. Just solve the tasks.

---

## 6. Pre-submit checklist
- [ ] Model loads & serves under your declared vLLM config.
- [ ] `Harness()` builds (no broken surface) and runs a sample task end-to-end.
- [ ] No task-specific answers in prompt / skills / tool descriptions / code.
- [ ] Skill descriptions are specific (they drive on-demand loading).
- [ ] Capability is in the **weights** — your harness still needs a real model to perform.
