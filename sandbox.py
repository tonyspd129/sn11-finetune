#!/usr/bin/env python3
"""SN11 sandbox — run every scenario; agent on the HOST, tool calls INSIDE the container.

For each task under scenarios/:
    build image → start container → run the scaffold agent ON THE HOST (its tools exec into
    the container) → run the verifier in the container → export result.

Host-side execution: the agent loop + the LLM client run in THIS process. Only the agent's
tool calls (execute_command / view / edit / write / grep) cross into the container, through a
`DockerShell` (docker exec / docker cp). So the container needs NO python/openai/prep, and the
agent reaches the model from the host regardless of the task's own (possibly broken) network.

    python sandbox.py        # no args: run EVERY task in scenarios/, one by one

Each run lands in output/<timestamp>/<task>/ (result.json incl. the session + work/ = the
/app end-state). LLM_* and the run knobs (incl. MAX_TURNS) auto-load from `.env` next to this
script (no `source .env`); an already-set shell var still wins. Optional env:
  • SANDBOX_PARALLEL — max tasks to run concurrently (default 1 = sequential)
  • SANDBOX_NETWORK — docker network for the task container (default = docker default)
  • BUILD_TIMEOUT   — per-image build timeout in seconds (default 1800)
  • VERIFY_TIMEOUT  — verifier timeout in seconds (default 900); on timeout the task scores 0
                      but the agent's session is still exported

Requires on the HOST: docker + python with `openai` installed (the agent runs here now).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"
SCENARIOS = HERE / "scenarios"                    # the eval pool: every task dir under here is run
OUTPUT = HERE / "output"                          # results land in output/<timestamp>/<task>/
VLIB = HERE / ".verifier-lib"                     # pytest (+deps) injected into the container via PYTHONPATH
_VLIB_DEPS = ["pytest==8.4.1", "requests", "pyyaml"]   # expand if a task's test needs more pure-python deps
sys.path.insert(0, str(HERE))                     # so `import scaffold` works regardless of cwd


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


def run_task(task_dir, mode="agent", network=None, max_turns=None, work_dir=None,
             build_timeout=1800, verify_timeout=900):
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

    # build the task image (bounded — a runaway build must not hang the batch)
    img = f"sn11/{task.parent.name}/{task.name}".lower().replace("_", "-")[:120]
    try:
        b = _d("build", "-t", img, str(build_ctx), timeout=build_timeout)
    except subprocess.TimeoutExpired:
        return {"task": task.name, "score": 0.0, "passed": False,
                "error": f"build timeout after {build_timeout}s"}
    if b.returncode:
        return {"task": task.name, "score": 0.0, "passed": False, "error": b.stderr[-800:]}

    cid = "sn11-" + uuid.uuid4().hex[:10]
    run = ["run", "-d", "--name", cid] + (["--network", network] if network else [])
    _d(*run, img, "sleep", "infinity")
    taskdir = _d("inspect", "-f", "{{.Config.WorkingDir}}", img).stdout.strip() or "/app"
    _exec(cid, f"mkdir -p {taskdir}")
    try:
        session = None
        if mode == "gold":
            if not sol:
                agent = "gold: no solution file"
            else:
                _d("cp", str(sol), f"{cid}:/tmp/solution")
                rc, _o = _exec(cid, "bash /tmp/solution", workdir=taskdir)
                agent = f"gold rc={rc}"
        else:
            # HOST-SIDE agent: the scaffold loop + LLMClient run HERE; tool calls exec into the
            # container via DockerShell. The container needs no python/openai/prep, and the LLM
            # is reached from the host (LLM_* + budgets come from env, loaded by _load_dotenv).
            from scaffold import Harness
            from scaffold.llm import LLMClient
            from scaffold.toolkit import DockerShell
            instruction = (task / "instruction.md").read_text()
            shell = DockerShell(cid, cwd=taskdir)
            hk = {"max_turns": max_turns} if max_turns is not None else {}
            sess = Harness(shell=shell, llm=LLMClient(), **hk).run(instruction)
            try:
                session = json.loads(sess.to_json())     # full transcript + raw llm_calls
            except Exception:
                session = {"stop_reason": sess.stop_reason, "turns": sess.turns,
                           "error": "session not JSON-serializable"}
            agent = f"agent stop={sess.stop_reason} turns={sess.turns}"

        # export the agent's WORK: the /app end-state, BEFORE the verifier mutates it
        if work_dir:
            Path(work_dir).mkdir(parents=True, exist_ok=True)
            _d("cp", f"{cid}:{taskdir}/.", work_dir)

        # inject + run the verifier (in the SAME container — checks the task end state).
        # A verifier hang/timeout/error must NOT discard the already-captured session, so it's
        # caught here and turned into a score-0 result instead of raising past the return.
        _d("cp", str(task / "verifier"), f"{cid}:/verifier")
        try:
            if vstyle == "pytest":
                # Inject pytest (+ common deps) as a PYTHONPATH lib and run it with the CONTAINER's own
                # python — offline, no uv/pip bootstrap, and the task's installed packages stay visible
                # (so env tasks like broken-python test the system python being fixed). Replaces the
                # network-dependent run-tests.sh bootstrap.
                _d("cp", str(_ensure_verifier_lib()), f"{cid}:/opt/vlib")
                cmd = "PY=$(command -v python3 || command -v python); $PY -m pytest /verifier/tests -rA"
                rc, vout = _exec(cid, cmd, workdir=taskdir, timeout=verify_timeout,
                                 env={"TEST_DIR": "/verifier/tests", "PYTHONPATH": "/opt/vlib"})
                score = _pytest_fraction(vout)
            else:
                rc, vout = _exec(cid, f"bash {ventry} {taskdir}", workdir=taskdir,
                                 timeout=verify_timeout, env={"TF_WORKDIR": taskdir})
                score = None
            if score is None:
                score = 1.0 if rc == 0 else 0.0
        except subprocess.TimeoutExpired:
            rc, vout, score = -1, f"verifier timed out after {verify_timeout}s", 0.0
        except Exception as e:
            rc, vout, score = -1, f"verifier error: {type(e).__name__}: {e}", 0.0

        # export the result (session is preserved even when the verifier above failed)
        return {"task": task.name, "pool": task.parent.name, "mode": mode,
                "passed": rc == 0, "score": score, "agent": agent,
                "session": session, "work_dir": work_dir, "verify": vout[-600:]}
    finally:
        _d("rm", "-f", cid)


def _pytest_fraction(out):
    p = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    f = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    f += int(m.group(1)) if (m := re.search(r"(\d+) error", out)) else 0
    return (p / (p + f)) if (p + f) else None


def _ensure_verifier_lib():
    """Build once: a flat dir of pure-python test deps (pytest + common libs) that gets injected
    into the container via PYTHONPATH, so the verifier runs OFFLINE against the container's OWN
    python — no `uv` download / `pip` bootstrap, and the task's installed packages stay visible.
    Needs the host online ONCE to populate it (like `pip install openai`); containers stay offline."""
    if (VLIB / "pytest").exists():
        return VLIB
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("need `uv` on the host to build the verifier lib (pip install uv)")
    VLIB.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([uv, "pip", "install", "--target", str(VLIB), *_VLIB_DEPS],
                       capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"verifier lib build failed: {(p.stderr or p.stdout)[-400:]}")
    return VLIB


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
    network = os.environ.get("SANDBOX_NETWORK") or None
    build_timeout = int(os.environ.get("BUILD_TIMEOUT") or "1800")
    verify_timeout = int(os.environ.get("VERIFY_TIMEOUT") or "900")
    parallel = max(1, int(os.environ.get("SANDBOX_PARALLEL") or "1"))
    out_root = OUTPUT / time.strftime("%Y%m%d-%H%M%S")
    print(f"running {len(tasks)} scenarios → {out_root}  (parallel={parallel}, "
          f"net={network or 'default'}, build_timeout={build_timeout}s, verify_timeout={verify_timeout}s)",
          flush=True)
    try:                                             # build the injected pytest lib ONCE, before the pool
        _ensure_verifier_lib()                       # (avoids a build race across worker threads)
    except Exception as e:
        print(f"warning: verifier lib unavailable ({e}); pytest tasks will score 0", file=sys.stderr)

    def _one(task):                                  # runs in a worker thread: own container, own out_dir
        out_dir = out_root / task.name
        try:                                         # one task must never abort the batch
            r = run_task(str(task), mode="agent", network=network, work_dir=str(out_dir / "work"),
                         build_timeout=build_timeout, verify_timeout=verify_timeout)
        except Exception as e:
            r = {"task": task.name, "pool": task.parent.name, "passed": False, "score": 0.0,
                 "error": f"{type(e).__name__}: {e}"}
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps(r, indent=2))     # full result, incl. session
        return r

    summary, done = [], 0
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = [ex.submit(_one, t) for t in tasks]   # submit all; pool runs `parallel` at a time
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            s = r.get("session") if isinstance(r.get("session"), dict) else {}
            row = {"task": r.get("task"), "passed": r.get("passed"), "score": r.get("score"),
                   "turns": s.get("turns"), "stop_reason": s.get("stop_reason"), "error": r.get("error")}
            summary.append(row)
            print(f"[{done}/{len(tasks)}] {row['task']} score={row['score']} passed={row['passed']} "
                  f"turns={row['turns']} stop={row['stop_reason']}"
                  + (f" ERROR={row['error']}" if row["error"] else ""), flush=True)
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))
    n_pass = sum(1 for r in summary if r["passed"])
    scored = [r["score"] for r in summary if isinstance(r["score"], (int, float))]
    mean = sum(scored) / len(scored) if scored else 0.0
    print(f"\n=== {n_pass}/{len(summary)} passed | mean score {mean:.3f} | {out_root} ===")
    sys.exit(0 if n_pass == len(summary) else 1)


if __name__ == "__main__":
    main()
