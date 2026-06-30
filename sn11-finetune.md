# SN11 — New Mechanism Design

**SN11's current live mechanism is [trajectoryRL](../trajectoryRL/).** This document specifies the
**new mechanism**, and only what **changes**. Everything not listed here is inherited from
trajectoryRL unchanged.

The new mechanism evaluates the agent harness in [scaffold/](scaffold/) (see
[scaffold/README.md](scaffold/README.md)); the task pool is built per
[dataset-pipeline.md](dataset-pipeline.md).

The change in one line: trajectoryRL competes on a **`SKILL.md` pack over a fixed shared model**;
SN11 competes on a **fine-tuned model + a full harness**, evaluated by **serving each miner's own
model deterministically**. The incentive engine around it is untouched.

---

## 1. What stays the same (inherited from trajectoryRL)

The whole incentive / consensus engine is reused as-is:

- **King-of-the-hill** ("seated winner") — one challenger per challenge-epoch; beat the incumbent by
  the **winner-protection margin δ** to take the seat.
- **Winner protection δ** — 3% flat, decaying toward 0 as the seated score nears the ceiling.
- **Winner-take-all + burn** — 100% of miner emission to the seated winner; otherwise burned to the
  owner UID.
- **Bittensor weights** — validators `set_weights(winner, owner)`, tempo-gated.
- **Continuous loop** — challenge-epochs back-to-back; **no fixed cycle**.
- **Web-submission + pack ownership lock** — the first hotkey to submit a pack owns it (anti-copy /
  earliest-wins).
- **Server-managed queue** — one challenger evaluated at a time.
- **Graded verifier scoring** — per task `passed/total ∈ [0,1]`; the incumbent's score is **cached**
  (only the challenger is run).
- **Docker sandbox eval** — scenario container → agent → fresh verifier container; verifier
  discipline (trusted/pinned binaries, no network at verify, re-derive results).

The new mechanism changes **two things** — what is submitted (§2) and how it is evaluated (§3) —
plus the consequences those force (§4).

---

## 2. Change #1 — submission is a **model + harness**, not a skill pack

| | trajectoryRL (now) | SN11 (new) |
|---|---|---|
| Submitted | a `SKILL.md` pack (~32 KB) | a **fine-tuned model + full harness** |
| Model | fixed shared LLM (OpenRouter) | the **miner's own** Qwen3.6-35B-A3B |
| Scaffold | `SKILL.md` only | tools, skills, system prompt, compaction, prompt builder |

A submission is a **pinned pair**, delivered in two channels:

1. **Model** — fine-tuned Qwen3.6-35B-A3B weights **uploaded to Hugging Face**, pinned by
   **`repo_id` + `commit_hash`** (HF revision SHA) so the validator serves the exact snapshot and
   the miner can't swap weights afterward. Plus the **serving config** the evaluator must use
   (`--tool-call-parser`, `--reasoning-parser`, chat template, max context). **Public on upload**
   (§4a).
2. **Harness** — the miner's edited copy of [scaffold/](scaffold/), sent via the
   **trajectoryRL web-submission** (held private until the challenge runs). Miners customize five
   surfaces by editing the package files — **tools** (`tools/<name>/{metadata.json, tool.py}`),
   **skills** (`skills/**/SKILL.md`), the **system prompt** (`skills/system.md`), **`compaction.py`**,
   and **`prompt.py`** (the prompt builder). The harness core (loop, LLM client, loaders, session
   export) is fixed. A present-but-broken file fails the submission at load (**fail fast**).

---

## 3. Change #2 — evaluation serves the **miner's own model, deterministically**

| | trajectoryRL (now) | SN11 (new) |
|---|---|---|
| Serving | shared OpenRouter LLM | validator serves the **miner's weights** on a **dedicated GPU** (vLLM) |
| Sampling | non-zero temperature | **greedy, temperature 0** → deterministic |
| Cross-validator variance | Winsorized mean | **not needed** — runs reproduce |

Per task: fetch the miner's weights from HF at the pinned `repo_id`+`commit_hash` (resolve that
exact revision — never `main`) and serve on a dedicated GPU → run the harness in Docker (egress
blocked at the network layer) → inject the **trusted verifier into the same container** → graded
score `s_t ∈ [0,1]`. Submission score `S = mean(s_t)`, capability-only (no cost/turns/latency).

**The king's score is cached, exactly.** Greedy + pinned serving + deterministic verifier + a fixed
task set ⇒ `S_king` is a constant; store it at coronation and **never recompute it per challenger**.
Re-evaluate the king only when the substrate changes — **task-pool rotation**, **verifier/core
version bump**, or **serving-stack change**. **Borderline guard:** vLLM + MoE routing aren't
bitwise-identical across GPUs, so when a challenger lands inside the margin
(`S_challenger ∈ [S_king, S_king + δ]`), re-run **king + challenger together on the same hardware**
to settle it. Re-eval compute is then spent only on genuine contenders.

---

## 4. Consequences of submitting a model

### 4a. Publication — model public on upload, harness public after the challenge
The **model is public the instant it's uploaded** to HF — the whole field, including the king's
model, is open, so challengers distill the public frontier and must **beat it by δ**. The **harness
is published after the submission challenges the king** (win or lose); it's held privately in
web-submission storage until then, so a queued scaffold can't be copied before its turn. The moat is
**temporal**, not categorical. *(A copy window remains on the public model — covered by the existing
ownership-lock + δ.)*

### 4b. Integrity — add a model-ablation probe
There's now a model **and** a rich scaffold, so extend trajectoryRL's pre-eval integrity gate:

- **Static audit** — scan system prompt / `SKILL.md` / `prompt.py` / tool descriptions / code for
  embedded answers, lookup tables, task-id matching, encoded blobs.
- **Model-ablation probe** *(new)* — run the harness with a null/weak stand-in model; if it still
  solves materially above chance, the *scaffold* carries answers → disqualify. The model must do the
  work.
- **Distribution-of-lift** — broad, modest lift (scaffold vs baseline) is legitimate; spiky lift on
  a few tasks is a cheat → penalize.

### 4c. Benchmark — bigger, held-out pool
trajectoryRL runs **12 public scenarios**. The new mechanism scores on **50+ held-out tasks**,
scaling to hundreds–thousands via [dataset-pipeline.md](dataset-pipeline.md). Public-vs-private is
still an open client decision. Determinism makes scoring reproducible, but a deterministic *and
observable* benchmark invites overfit — so tasks must stay **held-out** (the anti-overfit half).

### 4d. Eval economics — the real new cost
Serving a **distinct 35B per challenger on a GPU** is far heavier than trajectoryRL's shared API
call. This is the main new operating cost the new mechanism introduces.
