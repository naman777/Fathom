#!/usr/bin/env python3
"""Run the whole Fathom project with one command:  python run.py

What it does, in order:
  1. checks .env (OPENAI_API_KEY, DB_URL)
  2. creates .venv and installs requirements.txt if needed (re-runs itself inside the venv)
  3. runs `npm install` in web/ if node_modules is missing
  4. makes sure the database schema exists (never drops data unless you pass --reset)
  5. optionally seeds the sample corpus (--seed, or automatically answer the prompt when the DB is empty)
  6. starts the API (uvicorn) and the web UI (Next.js), waits until both answer, opens the browser
  7. streams both logs with [api] / [web] prefixes; Ctrl+C stops everything cleanly

Flags:
  --prod        build and serve the web UI (next build + start) instead of the dev server
  --no-web      only run the API
  --no-open     do not open the browser
  --seed        ingest data/corpus if the database has no documents (no prompt)
  --reset       DROP ALL TABLES in the public schema and recreate them (asks for confirmation)
  --test        run the pytest suite and exit
  --eval        run the evaluation harness (python -m eval.run_eval --k 3) and exit
  --api-port N  API port (default 8000)      --web-port N  web port (default 3000)
"""
import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# Child processes (Next.js prints unicode) must never crash our log pump on a cp1252 console.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
IS_WIN = os.name == "nt"
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")

C = {"api": "\033[36m", "web": "\033[35m", "run": "\033[32m", "err": "\033[31m", "off": "\033[0m"}
if IS_WIN:
    os.system("")  # enables ANSI colours in the Windows console


def say(msg, tag="run"):
    print(f"{C.get(tag, '')}[{tag}]{C['off']} {msg}", flush=True)


def die(msg):
    say(msg, "err")
    sys.exit(1)


def read_env() -> dict:
    env = {}
    p = ROOT / ".env"
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            env[k.strip()] = v
    return env


def port_free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_for(url: str, timeout: int, name: str, procs) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        for p in procs:
            if p.poll() is not None:
                return False
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(1)
    return False


def ensure_venv():
    """Create .venv, install requirements, and re-exec inside it."""
    inside = Path(sys.prefix).resolve() == VENV.resolve()
    if inside:
        return
    if not VENV_PY.exists():
        say("creating virtualenv (.venv)...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    stamp = VENV / ".requirements.stamp"
    req = ROOT / "requirements.txt"
    if not stamp.exists() or stamp.stat().st_mtime < req.stat().st_mtime:
        say("installing Python dependencies...")
        subprocess.check_call([str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(req)])
        stamp.write_text("ok")
    # Run inside the venv as a child and stay in the foreground (os.execv would detach on Windows, breaking Ctrl+C).
    cmd = [str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]]
    if IS_WIN:
        signal.signal(signal.SIGBREAK, lambda *_: None)  # the child gets it too; we just wait for it to finish
    while True:
        try:
            sys.exit(subprocess.call(cmd))
        except KeyboardInterrupt:
            continue  # Ctrl+C also reaches the child, which shuts down cleanly; keep waiting for it to exit


def ensure_web_deps():
    if (WEB / "node_modules").exists():
        return
    npm = shutil.which("npm")
    if not npm:
        die("npm not found. Install Node.js 20+ (https://nodejs.org) or run with --no-web.")
    say("installing web dependencies (npm install)...")
    subprocess.check_call([npm, "install"], cwd=WEB, shell=IS_WIN)


def db_state():
    """Returns number of documents (creating the schema if needed)."""
    code = (
        "from core import db\n"
        "db.init()\n"
        "c = db.connect()\n"
        "print(c.execute('SELECT count(*) FROM documents').fetchone()[0])\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        tail = (r.stderr.strip().splitlines() or ["unknown error"])[-1]
        die(f"cannot reach the database: {tail}\n      Check DB_URL in .env (the DB must allow your IP and have the pgvector extension).")
    return int(r.stdout.strip().splitlines()[-1])


def confirm(prompt):
    if not sys.stdin.isatty():
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


def seed_corpus():
    corpus = ROOT / "data" / "corpus"
    if not corpus.exists() or not any(corpus.iterdir()):
        say("data/corpus is empty; nothing to seed. Upload documents from the UI instead.")
        return
    say("ingesting data/corpus (this calls the OpenAI embeddings API)...")
    subprocess.check_call([sys.executable, "-m", "ingest.pipeline", str(corpus)], cwd=ROOT)


def stream(proc, tag):
    def pump():
        for line in iter(proc.stdout.readline, ""):
            print(f"{C[tag]}[{tag}]{C['off']} {line.rstrip()}", flush=True)
    t = threading.Thread(target=pump, daemon=True)
    t.start()
    return t


def spawn(cmd, cwd, tag, env=None, shell=False):
    kw = {}
    if IS_WIN:
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    p = subprocess.Popen(cmd, cwd=cwd, env=env, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", bufsize=1, **kw)
    stream(p, tag)
    return p


def kill_tree(p):
    if p.poll() is not None:
        return
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        else:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except Exception:
        p.terminate()


def main():
    ap = argparse.ArgumentParser(description="Run Fathom (API + web) with one command.")
    ap.add_argument("--prod", action="store_true")
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--web-port", type=int, default=3000)
    a = ap.parse_args()

    if sys.version_info < (3, 10):
        die("Python 3.10+ is required.")

    env = read_env()
    for key in ("OPENAI_API_KEY", "DB_URL"):
        if not (env.get(key) or os.environ.get(key)):
            die(f"{key} is missing. Copy .env.example to .env and fill it in.")

    ensure_venv()  # re-launches inside .venv, everything below runs there

    if a.test:
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT))

    if a.reset:
        say("--reset DROPS every table in the configured database's public schema.", "err")
        if not confirm("Really reset the database?"):
            die("aborted (reset needs an interactive 'y').")
        subprocess.check_call([sys.executable, "-m", "core.db", "--reset"], cwd=ROOT)

    docs = db_state()
    say(f"database OK ({docs} documents)")
    if docs == 0:
        if a.seed or confirm("Database has no documents. Ingest the sample corpus now?"):
            seed_corpus()
        else:
            say("skipping seed (use --seed to ingest data/corpus, or upload files in the UI).")

    if a.eval:
        sys.exit(subprocess.call([sys.executable, "-m", "eval.run_eval", "--k", "3"], cwd=ROOT))

    if not port_free(a.api_port):
        die(f"port {a.api_port} is already in use. Stop the other process or use --api-port.")
    if not a.no_web and not port_free(a.web_port):
        die(f"port {a.web_port} is already in use. Stop the other process or use --web-port.")

    web_env = None
    if not a.no_web:
        ensure_web_deps()
        web_env = {**os.environ, "NEXT_PUBLIC_API_URL": f"http://localhost:{a.api_port}", "PORT": str(a.web_port)}
        if a.prod:
            say("building the web UI (next build)...")
            npm = shutil.which("npm") or "npm"
            if subprocess.call([npm, "run", "build"], cwd=WEB, env=web_env, shell=IS_WIN) != 0:
                die("web build failed.")

    procs = []

    def shutdown(*_):
        say("stopping...")
        for p in procs:
            kill_tree(p)

    signal.signal(signal.SIGINT, lambda *_: (shutdown(), sys.exit(0)))
    if IS_WIN:
        signal.signal(signal.SIGBREAK, lambda *_: (shutdown(), sys.exit(0)))  # Ctrl+Break / console close
    else:
        signal.signal(signal.SIGTERM, lambda *_: (shutdown(), sys.exit(0)))

    try:
        api_env = {**os.environ}
        api_origin = f"http://localhost:{a.web_port}"
        if "CORS_ORIGINS" not in env and "CORS_ORIGINS" not in os.environ:
            api_env["CORS_ORIGINS"] = f"{api_origin},http://127.0.0.1:{a.web_port}"
        say(f"starting API on :{a.api_port}")
        api = spawn([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(a.api_port)],
                    ROOT, "api", env=api_env)
        procs.append(api)
        if not wait_for(f"http://127.0.0.1:{a.api_port}/api/health", 60, "api", procs):
            shutdown()
            die("API did not become healthy (see [api] logs above).")
        say(f"API ready: http://localhost:{a.api_port}/api/health")

        url = f"http://localhost:{a.web_port}"
        if not a.no_web:
            npm = shutil.which("npm") or "npm"
            cmd = [npm, "run", "start" if a.prod else "dev", "--", "-p", str(a.web_port)]
            say(f"starting web UI on :{a.web_port} ({'production' if a.prod else 'dev'})")
            web = spawn(cmd, WEB, "web", env=web_env, shell=IS_WIN)
            procs.append(web)
            if not wait_for(url, 120, "web", procs):
                shutdown()
                die("web UI did not start (see [web] logs above).")
            say(f"web ready: {url}")
            if not a.no_open:
                webbrowser.open(url)
        else:
            url = f"http://localhost:{a.api_port}/docs"

        print(f"\n{C['run']}Fathom is running{C['off']}  ->  {url}   (Ctrl+C to stop)\n", flush=True)
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        dead = next(p for p in procs if p.poll() is not None)
        say(f"a process exited with code {dead.returncode}; shutting down.", "err")
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()
