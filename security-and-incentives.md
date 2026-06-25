# SN11 — Security & Incentive Design

The detailed design behind [sn11-finetune.md](sn11-finetune.md): **how we stop cheating**,
**how we keep miners participating**, and **why the result is genuine convergence to the
capability frontier** rather than convergence to copying, memorization, or reward-hacking.

The whole design rests on one principle:

> **Score must equal real, general task capability of the *model*, measured on inputs no
> one could have prepared for, by a checker no one can tamper with.**

Every defense below exists to protect one of those four words: **real**, **general**,
**model**, **untamperable**.

---

## 1. Threat model (attack surface map)

| # | Surface | The cheat | Section |
|---|---|---|---|
| A | **Tasks** | Memorize published tasks; exfiltrate the live task; probe the hidden distribution | §2 |
| B | **Verifier** | Tamper the env so the checker reports a false pass; learn & game the check | §3 |
| C | **Submission** | The *harness* (not the model) solves it; call an external LLM; ship a non-Qwen model | §4 |
| D | **Chain / mechanism** | Copy the winner; Sybil many entries; collude; lazy validators copy scores | §5 |
| E | **Eval economics** | Spam/hang to exhaust eval GPU | §6 |

Defenses are layered — no single control is trusted alone.

---

## 2. Task integrity — protect **real** and **general**

The fine-tune subnet's signature risk: tasks publish at cycle end, so a naive design lets
miners train on the test.

**Defenses**

1. **Fresh private benchmark every cycle.** The scored set is *never* a set that has ever
   been public. Drawn fresh from a large/generated pool each cycle.
2. **Pool ≫ sample.** Maintain a pool of **hundreds–thousands** of tasks; sample the cycle's
   50+ at reveal time. A miner can't memorize what isn't drawn yet, and can't probe which
   will be drawn.
3. **Decontamination gate.** Before a task can score, semantic-dedup it against the entire
   public corpus (all previously published tasks + their solutions + common training sets).
   Reject near-duplicates. This is the **standing operational cost** of the subnet — own it.
4. **Canary strings.** Embed unique canaries in every published task. If a future
   submission reproduces a canary, that miner trained on published data in a way that
   leaked → flag/penalize.
5. **No exfiltration during eval.** Tasks can't leak out mid-cycle if the agent has no
   network (see §4) — block egress at the **network layer**, log all connection/DNS
   attempts, treat any outbound attempt as a red flag.
6. **Trap tasks.** Seed a few tasks whose "obvious" solution is a known contamination
   shortcut; passing via the shortcut (rather than solving) flags a contaminated model.

**Result:** the score is earned on inputs the miner *could not have prepared for* → it
measures **real** capability that **generalizes**, not recall.

---

## 3. Verifier integrity — protect **untamperable**

The verifier is the scoring oracle. The agent runs in the same container *before* it (so
its real fixes count), which means the agent can try to corrupt the checker. This is the
Terminal-Bench "fake-curl" class of exploit (shim a binary the checker calls and report
success without doing the work).

**Defenses**

1. **Trusted, pinned binaries.** The verifier calls tools by **absolute path** from a
   read-only, post-hoc-injected mount — never the agent's `PATH`, aliases, shims, or
   functions. Reset `PATH`/env to a known-good value before verifying.
2. **Separate user / least privilege.** Verifier runs as a different (e.g. root-owned,
   agent = non-root) user; ground-truth fixtures live in a directory the agent cannot write.
3. **Re-derive, don't trust artifacts.** The verifier recomputes results from first
   principles (run the program, hit the service, diff the real output) rather than reading
   a file the agent could have hand-written. Probe **externally** where possible (e.g. curl
   the service from outside the agent's process namespace).
4. **Hidden + randomized checks.** Test cases the model never sees; property-based /
   differential checks; multiple held-out assertions per task. Defeats "hardcode the
   expected output" reward-hacking.
5. **Crash = fail.** Fork-bombs, disk-fill, OOM → verifier under cgroup limits with its own
   reserved resources; any inability to verify scores as **fail**, never as pass/ambiguous.
6. **Determinism.** The verifier is deterministic so **any validator can reproduce the same
   verdict** (this is also the anti-lazy-validator control, §5).

**Result:** a pass means the task was actually solved, in the real end-state of the
container — the checker can't be fooled and the check can't be pre-learned.

---

## 4. Submission integrity — protect **model**

This is the deepest issue and the one that decides whether the subnet measures what it
claims. The harness is arbitrary Turing-complete code. A miner could put the intelligence
in the *harness* (a hardcoded solver, a task→solution lookup table) or call an *external*
LLM — and the fine-tuned model would be irrelevant. For a **fine-tune** subnet, the model
must do the work.

**Defenses**

1. **Evaluator serves the weights itself.** Miners submit *weights*, not an endpoint. The
   evaluator loads them on its own GPU with vLLM. The harness talks **only** to the
   evaluator-controlled local endpoint — `base_url`/`api_key` are injected by the evaluator
   and the miner's values are ignored.
2. **No network from the harness.** Egress blocked at the network layer (§2.5). A harness
   physically cannot reach an external GPT/Claude. Any outbound attempt → disqualify.
3. **Architecture / identity check on load.** Verify the loaded model is Qwen3.6-35B-A3B
   (param count, config, architecture signature) — reject a swapped or oversized model.
4. **Model-ablation probe — the key control.** On a small held-out probe set, run the
   submitted harness with the model **swapped for a null/weak stand-in** (returns empty or
   a generic 1B model). If the harness still solves materially above chance, the harness —
   not the model — is doing the work → **disqualify or heavily penalize.** This directly
   measures model-dependence and kills hardcoded-solver harnesses.
5. **Harness static audit + sandbox.** All submissions publish, so audit them: forbid
   outbound network, filesystem access outside the workspace, embedded large data blobs /
   lookup tables (cap harness payload size), and external-API client code. Scan for
   bundled solution corpora.
6. **Fresh tasks (again).** Even a clever task-specific harness can't generalize to tasks
   drawn from a pool it never saw → §2 backstops this control.

**Policy to lock down:** scaffold *improvement* (better tools, context management, skills)
is **legitimate and encouraged** — it's an agent competition. Task-specific *answer
encoding* is cheating. The ablation probe + fresh tasks together draw that line: a general
scaffold helps any task; a cheat only helps the ones it memorized.

---

## 4a. Scope — what may live in the **scaffold** (system prompt, skills, tools, compaction, prompt builder) vs the **weights**

Miners co-design **five** scaffold surfaces alongside the weights: the **system prompt**
(`system.md`), **skills** (`SKILL.md`), **tools**, **compaction**, and the **prompt builder**
(`prompt.py`). Two are *prose channels* loaded straight into the model's context — the **system
prompt** and **`SKILL.md`** — and they are the easiest cheat vectors: a miner who learns the
benchmark's domain can paste solutions, playbooks, or lookup tables into the prompt or a skill
instead of (or alongside) fine-tuning. The other three are *code channels* (tools, compaction,
and the task-aware prompt builder) that can inject the same way. This is the *same* attack as a
solver-harness (§4) — capability that isn't in the weights — so the rule is unified across **all
five**.

**The principle — capability, not answers:**

> The scaffold (system prompt, skills, tools, compaction, prompt builder) may encode **general,
> transferable capability** that helps an *open* class of tasks. It may **not** encode
> **task-specific answers** — solutions, lookup tables, or memorized data for a *closed* set of
> tasks. Specific knowledge must live in the **weights** (where fresh tasks, §2, ensure it's
> real ability, not recall).

**Decision rule (the generalization test):** content is legitimate iff it would help on
tasks the author has *never seen*. If removing it only hurts a narrow set of *known* tasks,
it's a cheat.

*(The table below applies equally to the **system prompt** and **`SKILL.md`** — both are prose
channels.)*

| ✅ Allowed in prompt / skill.md — *general capability* | ❌ Forbidden in prompt / skill.md — *specific answers* |
|---|---|
| How to use a tool; its args & pitfalls | Exact command sequences for a specific task |
| Methodology / checklists (explore → act → verify) | Lookup tables keyed on task id / fingerprint |
| Domain *concepts* & best practice ("TLS needs cert+key; verify with `openssl s_client`") | Full solution code / configs as the answer |
| Diagnosis heuristics; where to look | Expected outputs / hidden-test answers |
| Output & format conventions | `if task mentions X → emit canned Y` logic |
| Reusable patterns that transfer across tasks | Encoded / obfuscated blobs (base64, etc.) |

**Enforcement stack (defense in depth):**

1. **Fresh tasks (§2)** — the backstop. A skill encoding answers to known tasks is dead
   weight on a fresh draw.
2. **Skill/harness ablation (extends §4.4)** — swap the model for a weak/null stand-in. If a
   skill literally contains the answer, the weak model parrots it and still solves → flagged.
3. **Distribution-of-lift test** — score each submission *with* the miner's prose + prompt
   builder (system prompt + skills + `prompt.py`) and *with them reverted to the baseline*.
   Legitimate general scaffold gives a **broad, modest** lift across all tasks; a cheat gives a
   **narrow, large** lift on a few. A spiky, concentrated lift → penalize.
4. **Static audit** — every submission publishes, so scan the system prompt + SKILL.md +
   prompt.py + tool `metadata.json` (descriptions reach the model) + tool/compaction code for:
   over-cap size, task-id/fingerprint conditionals, embedded data, encoded
   blobs, lookup structures.
5. **Size cap** — prose is prose, not a dataset. Cap the system prompt, each SKILL.md, and
   the total prose payload (KB-scale). A megabyte "prompt" or "skill" is data, not knowledge.

**Where to enforce the line — structural choice (pick one, §10 #6):**

- **(A) Fixed scaffold.** Subnet owns tools + skills; miners *only* fine-tune. The skill
  vector is eliminated entirely. Cost: no miner scaffold innovation.
- **(B) Skill-strip — eval on the base scaffold; miner skills are *training-time only*.**
  Miners may use any skills/scaffold to **train** the model (generate trajectories, distill,
  self-play), but **evaluation runs the model on the subnet's fixed, audited scaffold**, with
  miner skills stripped. Capability that matters must end up **in the weights**. Cleanest for
  a *fine-tune* subnet: it kills the vector outright and still lets miners build any
  scaffolding they like to train. The subnet can periodically absorb the best community
  scaffold into the shared one. **← recommended.**
- **(C) Allow miner skills, enforce scope.** Run the full enforcement stack above at eval.
  Most expressive, but the largest attack surface and a permanent audit cost.

Under **(B)** the question "what may be in skill.md vs fine-tuned" answers itself: skills are
a *training aid*, the **weights are the submission**. Under (A)/(C) the scope table above is
the contract.

> **DECISION: policy (C) — miners submit skills/harness; the §4a scope table is the binding
> contract, enforced at eval by the pipeline in §4b.**

---

## 4b. Enforcing policy C — the audit pipeline

Under C the scope table is not advisory; it's enforced on every submission as a **4-phase
gate** that runs after screening and before its full-eval score is credited. Two hard
requirements make it safe in a decentralized validator set:

- **Deterministic & reproducible.** Phases 1–3 are fully deterministic given fixed seeds, so
  *every validator computes the same verdict* — no validator can collude to wave a cheat
  through. Only Phase 4 (borderline) is human, and it's a multi-validator vote, never one.
- **Default-deny on the cheap checks, default-credit on the judgment calls.** Clear
  violations auto-fail; gray-zone cases fall back to the stripped-scaffold score (so a false
  positive costs the miner their skill bonus, not their whole submission).

### Phase 1 — Static audit (cheap, first, deterministic)

Parse every `SKILL.md`, `tool.py`, and harness file. **Auto-disqualify** on any hard
violation; **flag for Phase 4** on a soft signal.

| Hard violation → DQ | Soft signal → flag |
|---|---|
| Skill payload over cap (per-skill / total) | Long literal command sequences |
| Encoded/compressed/binary blobs (base64/hex runs) | Big dict/list literals that look like tables |
| Network egress code beyond sanctioned `web_fetch` | Conditionals pattern-matching on input text |
| Filesystem access outside the workspace | Task-id-like string constants |
| Bundled data files over cap | Unusual entropy in "prose" skills |

### Phase 2 — Model-ablation probe (medium cost)

On a **held-out probe set** (≈10 tasks, disjoint from screening & benchmark), run the full
submission (harness + skills) with the model **replaced by a stand-in** — both a *null*
model (empty/refusal) and a *weak* generic small model.

- **Metric:** pass rate with the stand-in.
- **Verdict:** if a dummy model still solves materially **above chance** (default: > 10%, or
  > the measured base rate of the stand-in on the base scaffold), the *scaffold* carries the
  answers → **disqualify.** A legitimate scaffold is inert without a capable model.

### Phase 3 — Distribution-of-lift test (the core control; expensive)

Run the **full benchmark twice**: (a) with the miner's prose active (their system prompt +
skills), (b) with that prose **reverted to the core baseline** (core system prompt + built-in
skills, miner tools/compaction still present). Per task `t`, with trials averaged:
`lift_t = score_a(t) − score_b(t)`.

- **Legitimate** general prose → lift is **broad & modest**: many tasks improve a little.
- **Cheat** prose → lift is **narrow & large**: a few tasks flip fail→pass, the rest flat.

**Concentration metric** (deterministic): e.g. the share of total positive lift contributed
by the top-k tasks, or a Gini coefficient over positive lifts, with special weight on
*binary flips* (stripped ≈ 0 → skilled ≈ 1).

- **Credit-mode scoring (recommended):** the official score is **`score_b` (stripped) + the
  *general* component of the lift**, discarding the spiky top tail. Legitimate skills are
  fully credited; concentrated cheat-lift is neutralized — no DQ needed, the score just
  doesn't reward it.
- **Gate-mode (fallback):** concentration over threshold → revert to `score_b` (skills
  credited at zero) or flag for Phase 4 if egregious.

**Free byproduct:** run (b) *is* the policy-B "skill-strip" number — it's the model's
base-scaffold capability, which doubles as the **fallback floor** for every submission.

### Phase 4 — Human review (borderline only)

The irreducible cost of C: the gray zone between "general" and "specific." Only
Phase-1-flagged or Phase-3-borderline cases reach here; resolved by a **multi-validator
vote / committee**, defaulting to the stripped score until resolved.

### Cost of C — be honest

- **Phase 3 doubles full-eval GPU** (with-skills + stripped runs). This is the price of
  rewarding co-design; budget for ~2× the eval compute of policy A/B plus audit overhead.
- Phase 2 adds a small probe run; Phase 1 is cheap; Phase 4 is human time on a small tail.
- Mitigation: only submissions that pass screening reach Phases 2–3, so spam never pays the
  2× cost.

### Penalty ladder

| Trigger | Consequence |
|---|---|
| Hard static violation / ablation-pass | Disqualify submission |
| Repeat hard violation (same UID) | Slash stake / ban UID |
| Concentrated lift (Phase 3) | Credit only `score_b` + general lift (cheat-lift earns nothing) |
| Borderline (Phase 1/3 flag) | Phase-4 committee vote; default to stripped score |

---

## 5. Chain / mechanism integrity — Bittensor-specific

| Attack | Defense |
|---|---|
| **Copy the winning submission** (solutions publish at cycle end) | **ε-improvement margin** (must *beat* the public best, not tie) + **earliest-wins** tie-break (FIFO eval order). Copying is strictly unprofitable. |
| **Copy live leader mid-cycle** | **Commit-reveal**: only a hash is on-chain during the window; reveal at close. Nothing to copy in-flight. |
| **Weight-copying validators** | Commit-reveal of *weights* + only works because tasks/scores change each cycle (a static copy decays). |
| **Sybil / many entries** | Registration cost (burn/recycle TAO) per UID; **per-UID submission cap** per cycle; **near-duplicate dedup** of submissions; screening gate spends a Sybil's budget. |
| **Collusion (validator ↔ miner)** | **Deterministic eval** → every validator recomputes the same score; **Yuma consensus clipping** (κ≈0.5) discounts outlier validators; reproducibility spot-checks. |
| **Lazy validators copy scores** | Determinism + **reproducibility audits**: re-run a random submission, compare; divergent validators lose vtrust. |
| **Timing games** | Commit-reveal + a fixed reveal schedule bound them; earliest-wins makes "snipe at the buzzer" pointless for ties. |

**Result:** the only profitable strategy on-chain is to **submit a genuinely better
agent** — copying, Sybil, and collusion are dominated.

---

## 6. Eval economics — anti-DoS

- **Screening gate (5–10 tasks)** before full eval — broken/spam submissions die cheap.
- **Per-task wall-clock + per-submission total budget** — hanging harness is killed, scores
  the unfinished tasks as fail.
- **Registration/stake cost** makes spam expensive.
- **FIFO with bounded concurrency** — predictable GPU spend; queue drains deterministically.

---

## 7. Incentive design — winner-take-all

**Emission is winner-take-all:** the single highest-scoring eligible submission earns the
subnet's emission for the next cycle; everyone else earns nothing that cycle. It's the simplest,
hardest-to-game rule — there is exactly one prize, so there is nothing to split, dilute, or
collude over.

1. **Eligibility floor.** To win, a submission must (a) pass screening, (b) pass the §4b
   integrity audit, and (c) **beat the standing public best by ≥ ε** (copies/ties never win,
   by construction).
2. **Earliest-wins tie-break.** Within ε, the earliest submission wins — copying is strictly
   unprofitable.
3. **Incumbent reign.** If no challenger beats the public best by ε, the incumbent keeps
   earning (they are genuinely still the best).

**Why this doesn't kill participation.** The usual objection to winner-take-all is that a close
2nd earns nothing and leaves. Two design choices absorb that:

- **Open publication is the payoff for the field.** Every cycle the benchmark + all solutions
  publish, so a strong-but-losing miner's work *raises the public frontier they build on next
  cycle* — losing isn't wasted, it's a down payment on the next attempt.
- **You only have to be #1, not dominate.** The ε-margin means a marginal edge wins outright,
  so the incentive to push for the top is sharp and clear.

**Lower the barrier (so newcomers can reach the top):**

- Ship the **base harness** + starter skills (done — [base_harness/](base_harness/)).
- Provide **starter trajectories** / a small SFT seed set so newcomers aren't cold-starting.
- **Screening feedback**: tell a failed submission *why* (crashed / invalid tool calls /
  low score) so miners improve instead of giving up.
- Publish everything at cycle end → newcomers stand on the frontier, not behind it.

---

## 8. Why this is **real convergence**

Convergence has two flavors; the design forces the good one.

| | Bad convergence (what we prevent) | Good convergence (what we get) |
|---|---|---|
| **Tasks** | memorize the public test → saturate | fresh private tasks → score = real ability |
| **Solutions** | copy the winner → stagnate | ε-margin → must *beat* → ratchet up |
| **Where intelligence lives** | hardcode it in the harness | ablation probe → it must be the model |
| **Score meaning** | reward-hack the checker | untamperable verifier → score = task solved |
| **Field shape** | permanent lock-in / monoculture | ε-margin + open publication + low barrier → frontier keeps moving |

The **invariants** that guarantee it:

- **I1 — Unpredictable inputs:** nothing scored was ever public (fresh pool + decontam +
  canaries). → kills memorization.
- **I2 — Profitable only by improving:** ε-margin + earliest-wins + commit-reveal. → kills
  copying; turns publication into a rising floor.
- **I3 — The model does the work:** evaluator-served weights + no network + ablation probe.
  → keeps the *fine-tune* the thing that wins.
- **I4 — The oracle is honest:** trusted/pinned, re-deriving, deterministic verifier. →
  score = real task success.
- **I5 — The frontier keeps moving:** winner-take-all + ε-margin + open publication + low
  barrier. → losers build on the published frontier next cycle; no permanent lock-in.

Hold I1–I5 and "everything becomes public" stops being a leak and becomes the **engine**:
each cycle the whole field absorbs the published frontier, then must beat it on inputs it
can't prepare for, with the model carrying the load, judged by an honest oracle. That is
convergence **to genuine capability**, and it ratchets every two weeks.

---

## 9. Parameters to lock down (recommended defaults)

| Knob | Meaning | Recommended default |
|---|---|---|
| Screening size | tasks in the gate | 8, must run + solve ≥ 3 |
| Benchmark size | scored tasks/cycle | 50+, sampled fresh from a ≥500 pool |
| Trials per task | de-noise sampling luck | 3, evaluator-fixed sampling params |
| ε margin | beat-the-best threshold | decaying epsilon (SN9-style) or flat 3% (Dippy-style) |
| Emission | recipients per cycle | **winner-take-all** (single highest `S`) |
| Submission cap | anti-Sybil | N per UID per cycle |
| Harness payload cap | anti-lookup-table | small (MB-scale); audited |
| Per-task wall-clock | anti-hang | task-dependent; kill→fail |
| Skill size cap (§4b) | anti-answer-injection | ~10 KB/skill, ~50 KB total payload |
| Ablation pass threshold (§4b P2) | dummy-model solve rate that DQs | > 10% (or > base-rate of stand-in) |
| Lift concentration threshold (§4b P3) | spiky-lift cutoff | top-k lift share / Gini; tune on a labeled set |
| Ablation probe set | held-out tasks for P2 | ~10, disjoint from screening & benchmark |

---

## 10. Still-open decisions

1. **Sampling control** — evaluator fully fixes temperature/seed, or allows a declared
   range averaged over trials? (Affects pass@k gaming.)
2. ~~**Partial credit**~~ — **DECIDED: graded per-task `[0,1]`** (weighted fraction of checks,
   averaged over trials). Submission score = mean over tasks.
3. ~~**Cost/efficiency weighting**~~ — **DECIDED: none this phase.** Score is capability-only;
   tokens/turns/latency do not affect it.
4. **Pool generation ownership** — who authors/validates the fresh task pool each cycle, and
   how is the decontam/canary pipeline staffed? (The recurring cost of the subnet.)
5. ~~**Winner-take-all vs top-k**~~ — **DECIDED: winner-take-all** (single highest `S` earns
   next cycle; §7).
6. ~~**Scaffold-vs-model policy**~~ — **DECIDED: (C) allow miner skills + full scope
   enforcement** (§4a contract, §4b pipeline). Remaining sub-decisions under C:
   - **Lift scoring mode** — credit-mode (score = stripped + general lift) *(recommended)*
     vs gate-mode (revert to stripped score on concentrated lift).
   - **Concentration threshold** — needs calibration on a hand-labeled set of
     general-vs-cheat skills before launch.
   - **Phase-4 committee** — who sits on the borderline-review vote, and quorum rules.
