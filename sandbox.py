#!/usr/bin/env python3
"""SN11 sandbox — the minimal task-execution primitive.

    run the task image  →  inject + run the agent  →  inject + run the verifier  →  export result

In-container layout:  /app = the TASK (agent + verifier act here) · /workspace = scaffold's home
(the scaffold package + runner + instruction.md + the exported session.json).

Configured EXTERNALLY (validator / DB / infra), NOT here:
  • model serving + endpoint   → LLM_* env (auto-loaded from .env)
  • network policy             → docker default (set at the infra level, not here)
  • image prep                 → this runner ALWAYS preps (installs python3 + openai for the
                                 agent), since the task images are unprepared; in production
                                 that prep is baked into the image at build time instead.

    python sandbox.py        # no args: run EVERY task in scenarios/, one by one

It runs the scaffold agent against every task dir under scenarios/ and writes each run to
output/<timestamp>/<task>/ (result.json incl. the session + work/ = the /app end-state).
LLM_* and the run knobs — including MAX_TURNS — are auto-loaded from `.env` next to this
script (no `source .env` needed); an already-set shell var still wins over the file.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent           # fine-tune/ — this script lives here
SCAFFOLD = HERE / "scaffold"
ENV_FILE = HERE / ".env"
SCENARIOS = HERE / "scenarios"                    # the eval pool: every task dir under here is run
OUTPUT = HERE / "output"                          # results land in output/<timestamp>/<task>/

# Agent entrypoint copied into the container: run scaffold against the configured model (LLM_* env).
_RUNNER = '''import os, sys
sys.path.insert(0, "/workspace")                       # scaffold lives in /workspace (the agent's home)
from scaffold import Harness
task = open("/workspace/instruction.md").read()
# agent acts on the TASK at /app; budgets + sampling come from env (MAX_TURNS,
# MAX_TOKENS_BUDGET, WALL_CLOCK_S, LLM_TEMPERATURE, LLM_MAX_TOKENS), read by Harness/LLMClient.
s = Harness(workdir=os.environ.get("AGENT_WORKDIR", "/app")).run(task)
try:
    s.export("/workspace/session.json")                # trajectory export
except Exception:
    pass
print("STOP_REASON:", s.stop_reason, "TURNS:", s.turns)
'''


def _d(*args, timeout=1800):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def _exec(cid, sh, workdir=None, env=None, timeout=900):
    cmd = ["exec"]
    if workdir:
        cmd += ["-w", workdir]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    cmd += [cid, "bash", "-lc", sh]
    p = _d(*cmd, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def run_task(task_dir, mode="agent", network=None, max_turns=None, work_dir=None, prep=False):
    task = Path(task_dir).resolve()
    # unified season1 layout: instruction.md + environment/ + solution/ + verifier/
    build_ctx = task / "environment" if (task / "environment" / "Dockerfile").exists() else task
    if (task / "verifier" / "run-tests.sh").exists():
        vstyle, ventry = "pytest", "/verifier/run-tests.sh"
    elif (task / "verifier" / "verify.sh").exists():
        vstyle, ventry = "script", "/verifier/verify.sh"
    else:
        return {"task": task.name, "score": 0.0, "passed": False, "error": "no verifier"}
    sol = next((p for p in (task / "solution").iterdir() if p.is_file()), None) \
        if (task / "solution").is_dir() else None

    # run the task image
    img = f"sn11/{task.parent.name}/{task.name}".lower().replace("_", "-")[:120]
    b = _d("build", "-t", img, str(build_ctx))
    if b.returncode:
        return {"task": task.name, "score": 0.0, "passed": False, "error": b.stderr[-800:]}
    cid = "sn11-" + uuid.uuid4().hex[:10]
    run = ["run", "-d", "--name", cid] + (["--network", network] if network else [])
    _d(*run, img, "sleep", "infinity")
    # /app = the TASK (image WORKDIR; agent + verifier act here); /workspace = our scaffold's home
    taskdir = _d("inspect", "-f", "{{.Config.WorkingDir}}", img).stdout.strip() or "/app"
    _exec(cid, f"mkdir -p {taskdir} /workspace")
    try:
        session = None
        # inject + run the agent
        if mode == "gold":
            if not sol:
                agent = "gold: no solution file"
            else:
                _d("cp", str(sol), f"{cid}:/workspace/solution")
                rc, _o = _exec(cid, "bash /workspace/solution", workdir=taskdir)
                agent = f"gold rc={rc}"
        else:
            _d("cp", str(task / "instruction.md"), f"{cid}:/workspace/instruction.md")
            _d("cp", str(SCAFFOLD), f"{cid}:/workspace/scaffold")
            runner = Path("/tmp") / f"_sn11runner_{uuid.uuid4().hex[:6]}.py"
            runner.write_text(_RUNNER)
            _d("cp", str(runner), f"{cid}:/workspace/runner.py")
            runner.unlink(missing_ok=True)
            if prep:   # UNPREPARED images: ensure python3 + openai (normally an infra/image-prep step)
                _exec(cid, "python3 -m pip --version >/dev/null 2>&1 || "
                           "(apt-get update -qq && apt-get install -y -qq python3-pip) || "
                           "python3 -m ensurepip --upgrade >/dev/null 2>&1; "
                           "python3 -m pip install -q --break-system-packages openai 2>/dev/null || "
                           "python3 -m pip install -q openai", timeout=400)
            # forward model + sampling + budget knobs from the host env (e.g. sourced .env)
            env = {"AGENT_WORKDIR": taskdir}
            for k in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "OPENROUTER_API_KEY",
                      "LLM_TEMPERATURE", "LLM_MAX_TOKENS",
                      "MAX_TURNS", "MAX_TOKENS_BUDGET", "WALL_CLOCK_S"):
                if os.environ.get(k):
                    env[k] = os.environ[k]
            if max_turns is not None:                 # explicit override; main() omits it so .env MAX_TURNS wins
                env["MAX_TURNS"] = str(max_turns)
            rc, out = _exec(cid, "python3 /workspace/runner.py", workdir="/workspace", env=env)
            agent = f"agent rc={rc}: {out[-400:]}"
            session = _read_session(cid)        # pull scaffold's LLM conversation out BEFORE teardown

        # export the agent's WORK: the task fs (/app) end-state, BEFORE the verifier mutates it
        if work_dir:
            Path(work_dir).mkdir(parents=True, exist_ok=True)
            _d("cp", f"{cid}:{taskdir}/.", work_dir)

        # inject + run the verifier (runs in /app — checks the task's end state)
        _d("cp", str(task / "verifier"), f"{cid}:/verifier")
        if vstyle == "pytest":
            rc, vout = _exec(cid, f"bash {ventry}", workdir=taskdir, env={"TEST_DIR": "/verifier/tests"})
            score = _pytest_fraction(vout)
        else:
            rc, vout = _exec(cid, f"bash {ventry} {taskdir}", workdir=taskdir, env={"TF_WORKDIR": taskdir})
            score = None
        if score is None:
            score = 1.0 if rc == 0 else 0.0

        # export the result (scaffold's conversation under "session"; the /app end-state at "work_dir")
        return {"task": task.name, "pool": task.parent.name, "mode": mode,
                "passed": rc == 0, "score": score, "agent": agent,
                "session": session, "work_dir": work_dir, "verify": vout[-600:]}
    finally:
        _d("rm", "-f", cid)


def _read_session(cid):
    """Copy scaffold's /workspace/session.json (the full LLM conversation: messages, tool_log,
    usage) out of the container and parse it. Returns the dict, or None if the agent wrote none."""
    tmp = Path("/tmp") / f"_sn11sess_{uuid.uuid4().hex[:6]}.json"
    r = _d("cp", f"{cid}:/workspace/session.json", str(tmp))
    if r.returncode or not tmp.exists():
        return None
    try:
        data = json.loads(tmp.read_text())
    except Exception:
        data = None
    tmp.unlink(missing_ok=True)
    return data


def _pytest_fraction(out):
    p = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    f = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    f += int(m.group(1)) if (m := re.search(r"(\d+) error", out)) else 0
    return (p / (p + f)) if (p + f) else None


def _load_dotenv(path=ENV_FILE):
    """Populate os.environ from a sibling `.env` (KEY=VALUE lines) WITHOUT overriding
    anything already set — so a sourced shell or `FOO=x python sandbox.py` still wins."""
    try:
        text = Path(path).read_text()
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, val = line.partition("=")
        if key.strip():
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _discover_scenarios():
    """Every task dir directly under scenarios/, sorted by name (non-dirs like _index.json skipped)."""
    if not SCENARIOS.is_dir():
        return []
    return sorted((d for d in SCENARIOS.iterdir() if d.is_dir()), key=lambda p: p.name)


def main():
    _load_dotenv()                                   # auto-load .env (shell env, incl. MAX_TURNS, still wins)
    tasks = _discover_scenarios()
    if not tasks:
        print(f"no scenarios found under {SCENARIOS}", file=sys.stderr)
        sys.exit(1)
    out_root = OUTPUT / time.strftime("%Y%m%d-%H%M%S")
    print(f"running {len(tasks)} scenarios → {out_root}", flush=True)
    summary = []
    for i, task in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] {task.name} ...", flush=True)
        out_dir = out_root / task.name
        # agent mode, always prep, MAX_TURNS from env; bundle result.json + work/ under the task dir
        r = run_task(str(task), mode="agent", prep=True, work_dir=str(out_dir / "work"))
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps(r, indent=2))     # full result, incl. session
        s = r.get("session") if isinstance(r.get("session"), dict) else {}
        row = {"task": r.get("task"), "passed": r.get("passed"), "score": r.get("score"),
               "turns": s.get("turns"), "stop_reason": s.get("stop_reason"), "error": r.get("error")}
        summary.append(row)
        print(f"      score={row['score']} passed={row['passed']} turns={row['turns']} "
              f"stop={row['stop_reason']}" + (f" ERROR={row['error']}" if row["error"] else ""),
              flush=True)
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))
    n_pass = sum(1 for r in summary if r["passed"])
    scored = [r["score"] for r in summary if isinstance(r["score"], (int, float))]
    mean = sum(scored) / len(scored) if scored else 0.0
    print(f"\n=== {n_pass}/{len(summary)} passed | mean score {mean:.3f} | {out_root} ===")
    sys.exit(0 if n_pass == len(summary) else 1)


if __name__ == "__main__":
    main()
