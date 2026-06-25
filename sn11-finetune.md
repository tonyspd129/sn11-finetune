# SN11 — Fine-tune Subnet: Evaluation System

How the subnet runs a competition: miners submit a **(harness, model)** pair, it is
screened, fully evaluated against a private benchmark, and the winner earns emission for
the next cycle. At the end of each lifecycle **the models are published; the benchmark and
harness contents are not** (§9).

This document is the spec for the **eval system**. The harness miners extend lives in
[base_harness/](base_harness/) (see [base_harness/README.md](base_harness/README.md)).

**Role guides:** [miner.md](miner.md) (how to compete) · [validator.md](validator.md) (how to
evaluate) · [security-and-incentives.md](security-and-incentives.md) (rules, audit, incentives).

---

## 1. Goals

- Reward the **best agent** — model *and* scaffold together, not one in isolation.
- Make the subnet a **ratchet**: each cycle the **winning model is published** and becomes the
  public frontier the next cycle must beat. The benchmark stays **private** so it can't be
  memorized.
- Keep evaluation **cheap to gate** (screening) and **honest to score** (verifier in the
  same container, no network at verify time, private tasks).

---

## 2. Actors

| Actor | Role |
|---|---|
| **Miner** | Fine-tunes Qwen3.6-35B-A3B and extends the base harness (tools / skills / compaction / system prompt). Submits a `(harness, model)` pair. |
| **Validator / Evaluator** | Serves each miner's model on a dedicated GPU, runs the harness in Docker per task, then runs the verifier. Produces a score. |
| **Verifier** | Trusted, pinned checker injected into the agent's container *after* the agent finishes. Returns a graded `[0,1]` score per task. |
| **Chain** | Holds commit-reveal submissions, records scores, sets weights → emission. |

---

## 3. What a submission is

A submission is a **pinned pair**:

1. **Model** — fine-tuned Qwen3.6-35B-A3B weights, referenced by an immutable pointer
   (e.g. HF repo + revision/commit hash) plus the **serving config** the evaluator must
   use: `--tool-call-parser`, `--reasoning-parser`, chat template, max context. The miner
   owns the parser choice (the evaluator serves with vLLM; parsing is a serving-layer
   concern, not per-task).
2. **Harness package** — the miner's copy of [base_harness/](base_harness/), pinned by
   commit/hash. The harness loads everything from the package's own files, which the miner
   **edits** to customize: **tools** (`tools/<name>/{metadata.json, tool.py}`), **skills**
   (`skills/**/SKILL.md`), the **system prompt** (`skills/system.md`), **`compaction.py`**, and
   **`prompt.py`** (the system-prompt builder). A present-but-broken file fails the submission
   at load (fail fast). The harness core (loop, LLM client, loaders, session export) is fixed
   and must not be edited.

Submitted via **commit-reveal**: during the open window only a hash/pointer is committed,
so competitors cannot copy the live leader mid-cycle. Reveal happens when the window closes
(or per the chain's reveal schedule).

---

## 4. Lifecycle & timeline

A lifecycle is **2 weeks**. The winner of each lifecycle earns emission **during the next
one** — a continuous relay.

```
  Lifecycle N  (2 weeks)
  ┌─────────────────────────── Week 1 ───────────────────────────┬────────── Week 2 ──────────┐
  │ Submission window OPEN                                        │ Submission window CLOSED   │
  │ ──────────────────────────────────────────────────────────► │                            │
  │ Evaluation runs continuously, draining the queue (FIFO)      │ Eval continues until queue │
  │ as submissions arrive ─────────────────────────────────────►│ is EMPTY ─────────────────►│
  │                                                              │            ↓ winner chosen │
  └──────────────────────────────────────────────────────────────────────────┬──────────────┘
                                                                               │
   Emission earner DURING lifecycle N = winner of lifecycle N-1                │
                                                                               ▼
                              End of N: PUBLISH models only (harness + benchmark stay PRIVATE)
                                                                               │
                                                                               ▼
  Lifecycle N+1 begins ── scored on a PRIVATE held-out pool (reused, leak-guarded); the
                          published winner model is the public frontier to beat (by ε).
```

Key timing rules:

- **Submission window:** first week only. After that the queue is frozen and drained.
- **Evaluation:** begins as soon as submissions arrive in week 1 and runs until the queue
  is empty (may spill into week 2). FIFO — **earliest submission evaluated first**.
- **Winner selection:** once the queue is empty and all scores are in.
- **Emission:** the selected winner earns subnet emission for the **whole next lifecycle**.
- **Publication:** at the end of the lifecycle, **the models are released**. The **harness
  contents** and the **benchmark dataset** are **not** (§9).

---

## 5. Stage 1 — Screening (cheap gate)

Every revealed submission first runs against **5–10 screening tasks** before it is allowed
to consume full-eval compute.

- **Purpose:** reject broken or spam submissions cheaply — model won't load, harness
  crashes, emits invalid tool calls every turn, or fails everything trivially.
- **Pass criteria:** must (a) serve and run end-to-end without crashing, and (b) solve at
  least a minimum fraction of the screening tasks (threshold TBD — see §10).
- **Screening tasks are disjoint from the full benchmark** so screening never leaks the
  scored set.
- Only submissions that pass screening enter the full-eval queue.

---

## 6. Stage 2 — Full evaluation (benchmark dataset)

Passing submissions are evaluated on the full benchmark (**50+ tasks**).

Per task, in the miner's container:

1. Evaluator serves the miner's model (vLLM, miner's serving config) on a dedicated GPU.
2. Harness runs the task in Docker — network egress restricted at the **network layer**
   (web_fetch allowlist is defense-in-depth, not the boundary).
3. Agent finishes → the **trusted verifier is injected into the same container** and run.
   - Same container so the verifier sees the real end state (the agent may have installed
     deps or fixed a broken environment — that work must count).
   - Verifier binaries are **pinned/trusted**, not the agent's; **no network at verify
     time**; probe externally where possible.
4. Verifier emits a **graded score in `[0,1]`** for the task — the weighted fraction of the
   task's checks that pass (binary tasks are the `{0,1}` special case).

The harness exports the full session (messages, tool log, usage) for audit — there is no
`submit`; verification is entirely outside the harness.

---

## 7. Scoring & winner selection

Scoring is **graded and capability-only** — no cost/turns/latency term in this phase. We just
want the model+harness that **solves the problems**.

- **Per-task score** `s_t ∈ [0,1]` — the verifier's weighted fraction of passing checks,
  **averaged over `k` trials** to remove sampling noise (binary tasks = `{0,1}`).
- **Submission score** `S = mean(s_t)` over the benchmark (optionally **domain-weighted** so
  one easy cluster can't dominate). `S ∈ [0,1]`.
- **Winner:** highest `S`, subject to two anti-copy rules (§10):
  - **Improvement margin (ε):** to dethrone the standing public best you must beat it by
    ≥ ε, not merely tie it.
  - **Earliest-wins tie-break:** equal scores resolve to the earliest submission (FIFO
    already orders eval; this makes copying strictly unprofitable).

Emission is **winner-take-all**: the single highest-`S` eligible submission earns the subnet's
emission for the next cycle (see §10). The integrity audit (security doc) sits on top: `S` is
credited only after the ablation gate + lift-test confirm the *model* produced it.

---

## 8. Emission

The selected winner receives the subnet's emission for the **entire next 2-week
lifecycle** while the next competition runs. Mechanically: validators set weights toward
the winning UID; that weighting persists until the next lifecycle's winner is chosen.

---

## 9. Publication policy & the convergence ratchet

**Decision:** at the end of each lifecycle **the models are published; the benchmark and the
harness contents are NOT.** Three things, three roles:

- **Models → published.** The winner's model becomes the **public frontier** every cycle. With
  the **ε-margin + earliest-wins**, copying the model can't win — you must *beat* the public
  model. Distilling from / fine-tuning on the published model is the intended ratchet: the
  subnet's product is an ever-improving open model.
- **Harness → private.** Each miner's scaffold (tools/skills/prompt/compaction) is competitive
  IP — never published, so it can't be copied. (Validators still *audit* it privately at eval
  time — the integrity audit in [security-and-incentives.md](security-and-incentives.md).)
- **Benchmark → private (reused).** Tasks never go public, so there is no memorization-from-
  public risk and a held-out pool can be **reused** across cycles (lower cost). The trade is a
  **validator-leak risk** — a validator who sees the tasks could pass them to a miner —
  mitigated by canaries (leak tripwires), per-validator partitions, stake/slashing, and pool
  rotation (security doc G1).

Net: the **model frontier ratchets up publicly** (publish + ε-margin), while the **harness stays
a private moat** and the **benchmark stays unmemorizable** (private + reused, leak-guarded).

---

## 10. Anti-gaming mechanics & open decisions

> Full threat model + the gaps that need decisions: **[security-and-incentives.md](security-and-incentives.md)**.

Baked-in:

- **Commit-reveal** during the submission window — no copying the live leader.
- **Earliest-wins / FIFO** eval order and tie-break — copying is strictly unprofitable.
- **ε improvement margin** over the standing best — ties/marginal copies don't dethrone.
- **Private, reused benchmark** — drawn from a decontaminated, canary-tagged pool; **never
  published** (leak-guarded — see the security doc).
- **Verifier in-container, trusted/pinned, no network at verify** — agent's environment
  fixes count, but the checker can't be tampered with.
- **Screening gate** — protects full-eval compute from broken/spam submissions.

Open decisions to lock down:

1. **Screening threshold** — pass = "runs + solves ≥ k of 5–10"? exact k?
2. **Benchmark size & stability** — 50 is statistically noisy; sample 50 *fresh* from a
   pool of hundreds–thousands per cycle, and/or run multiple trials and average.
3. **ε value / schedule** — flat % (Dippy-style ~3%) vs decaying epsilon (SN9-style).
4. ~~**Winner-take-all vs top-k**~~ — **DECIDED: winner-take-all** (single highest `S` earns).
5. ~~**Partial credit vs binary**~~ — **DECIDED: graded per-task `[0,1]`** (avg over trials).
6. ~~**Cost/efficiency weighting**~~ — **DECIDED: none this phase** (capability-only).
7. ~~**Publication policy**~~ — **DECIDED: models published; benchmark + harness PRIVATE** (§9).
8. **Private-benchmark leak control** *(new, from #7)* — validators see the private tasks, so
   specify: canaries (leak tripwires), per-validator task partitions, validator stake/slashing,
   and a pool rotation cadence.
9. **Pool replenishment** — who generates/validates the (reused, private) task pool, the task
   rubric format, and how decontamination is enforced. The biggest recurring cost.
