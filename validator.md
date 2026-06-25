# SN11 — Validator Guide

Validators turn each miner submission into a **score**, and set on-chain weights from it. The
design is **deterministic**: every honest validator computes the same score, so consensus is
automatic and collusion is hard.

> Full context: eval lifecycle → [sn11-finetune.md](sn11-finetune.md) · miner side →
> [miner.md](miner.md)

---

## 1. What you do per submission

1. **Serve the model** — load the miner's Qwen3.6-35B-A3B weights on a dedicated GPU (vLLM,
   their serving config). **You inject the endpoint** — the harness talks only to your local
   model; the miner's `base_url`/`api_key` are ignored.
2. **Run the harness** — per task, in **Docker**, with **network egress blocked at the network
   layer** (the in-harness allowlist is defense-in-depth only).
3. **Verify** — after the agent finishes, inject the **trusted verifier into the same
   container** and score pass/fail.
4. **Audit integrity** — the integrity-audit checks (below).
5. **Score & set weights.**

---

## 2. The eval pipeline

| Stage | What | Outcome |
|---|---|---|
| **Screening** | 5–10 tasks | cheap gate; broken harness (won't build) or near-zero score → reject before spending full-eval GPU |
| **Full eval** | 50+ **held-out** tasks | per task: `harness.run` → verifier returns a graded score `s_t ∈ [0,1]` (avg over `k` trials) |
| **Integrity audit** | the audit | static audit · model-ablation probe · distribution-of-lift · committee (borderline) |
| **Score** | aggregate | `S = mean(s_t)` over the benchmark (domain-weighted), `S ∈ [0,1]` · **capability-only, no cost/turns/latency** · ε-margin vs public best · earliest-wins tie-break · **winner-take-all** |

---

## 3. Integrity audit — what to enforce

- **Static audit** — scan system prompt, `SKILL.md`, `prompt.py`, tool `metadata.json`
  (descriptions reach the model) and tool/compaction code for embedded answers, lookup
  tables, task-id matching, encoded blobs, over-cap size.
- **Model-ablation probe** — run the harness with a null/weak stand-in model on a held-out
  set; if it still solves materially above chance, the *scaffold* carries answers → disqualify.
- **Distribution-of-lift** — score with the miner's prose+builder vs reverted to baseline;
  broad/modest lift is legitimate, narrow/large (spiky) lift is a cheat → penalize.
- **Committee** — only borderline cases; multi-validator vote, defaults to the stripped score.

---

## 4. Determinism & consensus

- **Fixed sampling** (temperature/seed), **N trials averaged** to remove luck.
- **Deterministic verifier** → any validator reproduces the same verdict.
- **Reproducibility spot-checks** + **Yuma clipping** discount outlier/lazy validators.
- The audit's automated checks (static/ablation/lift) are deterministic; only the committee is human.

---

## 5. Verifier discipline (non-negotiable)

- **Trusted, pinned binaries** by absolute path — never the agent's `PATH`/shims; reset env.
- **Separate user**; ground-truth fixtures outside the agent-writable area.
- **Re-derive** results (run it, hit the service) rather than trusting agent-written artifacts.
- **No network at verify time.** **Crash / can't-verify = fail**, never pass.

---

## 6. Tasks & weights

- **Score on a held-out pool** of tasks the miner couldn't prepare for; decontaminate against
  public corpora + embed a **canary** in every task. *(Whether the pool is also kept
  private/reused vs published fresh each cycle is an open client decision — sn11-finetune.md §10
  #2. The discipline below applies to the **private** branch.)*
- **If the pool is private: protect the tasks — you can see them, so don't leak them.** Its
  secrecy is a validator responsibility: canaries detect leaks, per-validator partitions limit
  blast radius, and leaking is **stake-slashable**.
- **Commit-reveal** submissions during the window (no copying the live leader).
- **Emission** → **winner-take-all**: the single highest-`S` eligible submission earns for the
  next cycle (must beat the published model by ε; earliest-wins tie-break).
- **At cycle end, publish the winning model + ALL submissions' skills** (a public skill commons);
  the **rest of the harness** (tools/`prompt.py`/`compaction.py`/`system.md`) **stays private**.
  The benchmark's public/private status is **TBD** (§10 #2).

---

## 7. Reject / fail conditions
- Harness won't build, or model won't serve under the declared config.
- Any outbound network attempt during eval.
- Ablation probe solves with a dummy model (scaffold carries answers).
- Concentrated (spiky) lift, or a published-task **canary** reproduced in outputs.
- Verifier cannot run / container tampered → score as fail.
