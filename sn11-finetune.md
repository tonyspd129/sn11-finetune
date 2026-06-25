# SN11 — Fine-tune Subnet: Evaluation System

How the subnet runs a competition: miners submit a **(harness, model)** pair, it is
screened, fully evaluated against a held-out benchmark, and the winner earns emission for
the next cycle. At the end of each lifecycle **the winning model and all submissions' skills
are published; the rest of the harness stays private. Whether the benchmark is public or
private is still open** — a client-discussion item (§8, §9).

This document is the spec for the **eval system**. The harness miners extend lives in
[base_harness/](base_harness/) (see [base_harness/README.md](base_harness/README.md)).

**Role guides:** [miner.md](miner.md) (how to compete) · [validator.md](validator.md) (how to
evaluate — incl. the integrity audit & verifier controls).

---

## 1. Goals

- Reward the **best agent** — model *and* scaffold together, not one in isolation.
- Make the subnet a **double ratchet**: each cycle the **winning model** *and* **all submissions'
  skills** are published and become the public frontier the next cycle must beat. The rest of the
  harness (tools, prompt builder, compaction, base prompt) stays a **private moat**.
- Keep evaluation **cheap to gate** (screening) and **honest to score** (verifier in the
  same container, no network at verify time, held-out tasks).

---

## 2. What a submission is

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

## 3. Lifecycle & timeline

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
           End of N: PUBLISH winning model + ALL skills (tools/prompt/compaction/base prompt stay
                     PRIVATE; benchmark public-vs-private is TBD — §9)
                                                                               │
                                                                               ▼
  Lifecycle N+1 begins ── scored on a held-out pool; the published winner model + skill commons
                          are the public frontier to beat (by ε).
```

Key timing rules:

- **Submission window:** first week only. After that the queue is frozen and drained.
- **Evaluation:** begins as soon as submissions arrive in week 1 and runs until the queue
  is empty (may spill into week 2). FIFO — **earliest submission evaluated first**.
- **Winner selection:** once the queue is empty and all scores are in.
- **Emission:** the selected winner earns subnet emission for the **whole next lifecycle**.
- **Publication:** at the end of the lifecycle, **the winning model and all submissions' skills
  are released**. The rest of the **harness** (tools, prompt builder, compaction, base prompt) is
  **not**; the **benchmark**'s public/private status is **TBD** (§8, §9).

---

## 4. Stage 1 — Screening (cheap gate)

Every revealed submission first runs against **5–10 screening tasks** before it is allowed
to consume full-eval compute.

- **Purpose:** reject broken or spam submissions cheaply — model won't load, harness
  crashes, emits invalid tool calls every turn, or fails everything trivially.
- **Pass criteria:** must (a) serve and run end-to-end without crashing, and (b) solve at
  least a minimum fraction of the screening tasks (exact threshold TBD).
- **Screening tasks are disjoint from the full benchmark** so screening never leaks the
  scored set.
- Only submissions that pass screening enter the full-eval queue.

---

## 5. Stage 2 — Full evaluation (benchmark dataset)

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

## 6. Scoring & winner selection

Scoring is **graded and capability-only** — no cost/turns/latency term in this phase. We just
want the model+harness that **solves the problems**.

- **Per-task score** `s_t ∈ [0,1]` — the verifier's weighted fraction of passing checks,
  **averaged over `k` trials** to remove sampling noise (binary tasks = `{0,1}`).
- **Submission score** `S = mean(s_t)` over the benchmark (optionally **domain-weighted** so
  one easy cluster can't dominate). `S ∈ [0,1]`.
- **Winner:** highest `S`, subject to two anti-copy rules:
  - **Improvement margin (ε):** to dethrone the standing public best you must beat it by
    ≥ ε, not merely tie it.
  - **Earliest-wins tie-break:** equal scores resolve to the earliest submission (FIFO
    already orders eval; this makes copying strictly unprofitable).

Emission is **winner-take-all**: the single highest-`S` eligible submission earns the subnet's
emission for the next cycle. The integrity audit ([validator.md](validator.md) §3)
sits on top: `S` is credited only after the ablation gate + lift-test confirm the *model* produced it.

---

## 7. Emission

The selected winner receives the subnet's emission for the **entire next 2-week
lifecycle** while the next competition runs. Mechanically: validators set weights toward
the winning UID; that weighting persists until the next lifecycle's winner is chosen.

---

## 8. Publication policy & the convergence ratchet

**Decision:** at the end of each lifecycle **the winning model and every submission's skills are
published; the rest of the harness is NOT.** The benchmark's public/private status is still
**open** (client-discussion — §9). Four things, four roles:

- **Winning model → published.** It becomes the **public frontier** every cycle. With the
  **ε-margin + earliest-wins**, copying the model can't win — you must *beat* the public model.
  Distilling from / fine-tuning on the published model is the intended ratchet: the subnet's
  product is an ever-improving open model.
- **All skills → published.** Every submission's `SKILL.md` skills become a **public skill
  commons** each cycle (not just the winner's). Skills are **behavior-only** — methodology, not
  answers (§9) — so sharing them is low-risk and creates a *second* public ratchet: the
  community's agent behavior improves in the open. (They're still audited at eval time —
  [validator.md](validator.md) §3.)
- **Rest of the harness → private.** Tools (`tools/`), the prompt builder (`prompt.py`),
  compaction (`compaction.py`), and the base system prompt (`skills/system.md`) are competitive
  IP — never published. The moat is now the **model + these private surfaces**.
- **Benchmark → TBD (public vs private).** *Not yet decided — see §9.* If **private/reused**:
  lower cost, but a **validator-leak risk** (a validator who sees the tasks could pass them to a
  miner) mitigated by canaries, per-validator partitions, stake/slashing, and pool rotation
  ([validator.md](validator.md) §6). If **public/fresh**: no leak risk and a public benchmark, but
  a continuous task-generation cost (§9 #2).

Net: **two public ratchets** — the **model frontier** (publish winner + ε-margin) and the **skill
commons** (publish all skills) — over a **private scaffold moat** (tools + prompt builder +
compaction + base prompt). The benchmark's secrecy is the remaining open lever.

---

## 9. Discussion points (for client review)

Open questions still under discussion, with our **current position** on each.

### 1. Dataset preparation — *how do we build the task pool?*
**Current position:** start by **filtering SWE-bench and Terminal-Bench** and **sampling the
DevOps-flavored tasks** as the seed benchmark (then decontaminate; extend with generated tasks
later). This gives a credible, recognizable base quickly.

### 2. Benchmark — public or private? *(undecided — needs the client's call)*
The harness side is settled (model + all skills public; rest private — §8), but the **benchmark
itself is not**. The two branches:
- **Private / reused** — cheaper (reuse a held-out pool across cycles), but validators *see* the
  tasks, so it carries a **validator-leak risk** and needs the full leak-control kit (canaries,
  per-validator partitions, stake/slashing, rotation — [validator.md](validator.md) §6).
- **Public / fresh** — publish each cycle's tasks after scoring and generate a new set next cycle.
  **No leak risk** and yields a public benchmark, but requires a **continuous task-generation
  pipeline** (the biggest recurring cost).

This couples to item 3 below: a private benchmark makes determinism safe (tasks stay unseen); a
public one re-introduces overfit risk unless tasks are *always* freshly generated. **Decision
deferred to the client.**

### 3. Reducing LLM variance — *how do we rank close models reliably?*
**Current position:** set up a **deterministic environment** (greedy decoding + pinned serving +
deterministic verifier) to remove scoring luck. **Caveat:** a deterministic *and observable*
benchmark lets miners **overfit to it** — so determinism alone isn't enough. The resolution is
determinism **for fairness** + **fresh/secret tasks** **for anti-overfit** (the two are
independent; this couples to the publication decision).

### 4. Skill-development scope — *how much agent should miners build?*
**Current position:** **limit skill development to behavior only** — skills/prompt may steer
*how* the agent acts, but must not encode capability or task knowledge. The intent is to push
miners toward **fine-tuning the model** (where capability belongs) rather than engineering the
scaffold to win. This is reinforced by the publication policy: since **all skills are now
published** (§8), a skill is a shared commons — embedding answers or IP in it is both disallowed
(audited) and self-defeating (handed to every competitor next cycle).

### 5. Economics / burn rate — *is SN11 sustainable at current emission?*
**Current numbers:**

| | TAO/day |
|---|---|
| Network total generated | 3,600 |
| SN11 emission share (0.25%) | 9 |
| Emission paid to miners | 24 |
| **Net** | **≈ −15 (loss)** |

**Current position:** at the current emission share SN11 runs at a **~15 TAO/day deficit**
(9 in − 24 out) — economics/sustainability must be addressed (raise emission share, cut costs, or
adjust the payout). *(Figures to confirm with the client.)*

### 6. Registration cost — *what stops a registration war?*
**Current position:** the subnet's **minimum burn is set to zero**, so a UID costs **only the base
transaction fee** to register — effectively free. Zero-cost registration invites a **registration
war**: Sybil/spam registrations and cheap UID churn (miners cycling identities to farm
earliest-wins, submit lottery-ticket variants, or dodge audits). The standard fix is a **non-zero
minimum burn** — it prices out spam, *and* the recycled burn helps offset the eval deficit in #5.
**Decision needed:** set a burn floor > 0 (flat, or demand-scaled), traded off against keeping
entry open to new miners.
