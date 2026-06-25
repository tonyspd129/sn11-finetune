# SN11 — Security Vulnerabilities & Open Decisions

The real attack surface of the decided design ([sn11-finetune.md](sn11-finetune.md)), and the
gaps that still need your call. (Incentive mechanics — graded `[0,1]` scoring, winner-take-all,
ε-margin — are **decided**; see sn11 §7–§9.)

**Decided context:** models published · **benchmark + harness PRIVATE** · graded capability-only
scoring · winner-take-all (beat the public model by ε) · miners edit the harness (audited) ·
trusted in-container verifier · fail-fast harness load.

---

## The rule the audit enforces

The scaffold (system prompt, skills, tools, compaction, prompt builder) may encode **general,
transferable capability** — never **task-specific answers**. The **integrity audit** enforces it:

1. **Ablation probe** — run the harness with a dummy/weak model. If it still solves, the
   *scaffold* is carrying the answers → disqualify.
2. **Lift-test** — score with the miner's scaffold vs reverted to baseline. Broad, modest lift
   is legitimate; a narrow, large (spiky) lift is a cheat → penalize.
3. **Static scan** — system prompt + `SKILL.md` + `prompt.py` + tool `metadata.json`
   (descriptions reach the model) + tool/compaction code, for embedded answers / lookup tables
   / task-id matching / encoded blobs / over-cap size.

The validator **has** the harness (it runs it), so it audits privately even though the harness
is never published.

---

## 1. Vulnerabilities the system contains

| # | Vulnerability | Containment | Residual / gap |
|---|---|---|---|
| 1 | **Verifier tampering** — the agent runs in the container *before* the verifier and can shim binaries / poison env to fake a passing score (the "fake-curl" class). | Verifier uses **trusted, pinned binaries by absolute path** (not the agent's PATH), runs as a **separate user**, **re-derives** results (runs it / probes it) instead of trusting agent artifacts, **no network at verify**, **crash = fail**. | Verifier not built — **engineering gap**. |
| 2 | **Answer-injection into the scaffold** — a miner edits prompt/skills/tools/compaction to embed task-specific answers instead of fine-tuning (the cost of letting miners edit the harness). | Private **unseen** tasks (can't pre-bake) + the **integrity audit** above. | Lift threshold needs calibration → **G3**. |
| 3 | **Harness avoids the served model** — calls an external LLM, ships a non-Qwen model, or a hardcoded solver. | Evaluator **serves the weights itself** and **injects the endpoint** (miner's `base_url` ignored); **no network egress**; **architecture/param check** on load; **ablation probe**. | — |
| 4 | **Task exfiltration during eval** — the agent ships the live task to an external server so a colluder can memorize it. | **Egress blocked at the network layer**; any outbound attempt → red flag / DQ. | Isolation rigor → **G5**. |
| 5 | **Container escape** — the agent breaks out of Docker to read the verifier, other tasks, or other miners' data. | **Hardened sandbox** (gVisor/Kata, seccomp, no-privileged); verifier injected read-only post-hoc. | Sandbox tech not chosen → **G5**. |
| 6 | **Validator leak of the private benchmark** *(NEW — from the publish decision)* — a validator sees the private, reused tasks and passes them to a miner who memorizes. | **Canaries** (leak tripwire — a leaked task shows up in a miner's model/output), **per-validator task partitions** (limit blast radius), validator **stake/slashing**, **pool rotation**. | The whole control is unspecified → **G1**. |
| 7 | **Benchmark contamination** — a scored task overlaps the model's public pretraining, so it's solved by recall, not capability. | **Decontaminate the pool** against public corpora/benchmarks before a task can score. | Pipeline staffing → **G2**. |
| 8 | **Chain: lazy / colluding / score-copying validators.** | **Deterministic eval** (every validator recomputes the same score) + **reproducibility spot-checks** + **Yuma consensus clipping** + **commit-reveal**. | — (standard Bittensor) |
| 9 | **Sybil / distribution-probing / spam-DoS** — many submissions to probe the hidden task distribution, raise odds, or exhaust eval GPU. | **Registration/stake cost** + **per-UID submission cap** + **screening gate** + per-task **wall-clock / cgroup budgets** (crash = fail). | Cost/cap values → **G6**. |

---

## 2. Gaps that need your decision

- **G1 — Validator-leak control** *(the big one)*. Pick the mitigation mix and parameters:
  canary scheme, per-validator task **partitioning**, validator **stake/slashing** for a proven
  leak, and the **pool-rotation cadence**. Without this, vulnerability #6 is open.
- **G2 — Task-pool pipeline** *(the top build)*. Who generates/validates tasks; the **task
  rubric format** (how a task declares its `[0,1]` checks — this also makes the verifier
  buildable); decontamination; rotation cadence. The biggest recurring cost.
- **G3 — Lift-test calibration.** The spiky-vs-broad **concentration threshold** (needs a
  hand-labeled set of general-vs-cheat scaffolds), and **credit-mode** (score = stripped +
  general lift, *recommended*) vs **gate-mode** (revert to stripped on concentrated lift).
- **G4 — Scoring knobs.** ε **value & schedule** (flat % vs decaying), and **sampling** —
  trials `k` per task and fixed-seed vs declared-range-averaged.
- **G5 — Sandbox & network rigor.** Sandbox tech (gVisor / Kata / plain Docker) and how egress
  is actually enforced (the boundary for #3/#4/#5).
- **G6 — Sybil economics.** Registration/stake cost and the per-UID submission cap.
- **G7 — Screening threshold.** The pass criteria for the 5–10-task gate.
- **G8 — Borderline-cheat review.** Keep a human committee for ambiguous audit cases? If so,
  who sits on it and the quorum.
