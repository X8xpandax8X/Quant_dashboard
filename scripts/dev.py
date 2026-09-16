#!/usr/bin/env python3
"""Start local demo API and Vite; no external provider calls or cloud services."""
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
python = root / ".venv/bin/python"
if not python.exists():
    raise SystemExit("Create .venv and install requirements.lock.txt first (see README).")
node = shutil.which("node")
if node is None:
    bundled = Path.home()/".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    node = str(bundled) if bundled.exists() else None
if not node:
    raise SystemExit("Node.js 22.12+ or 24 is required.")
vite = root/"frontend/node_modules/vite/bin/vite.js"
if not vite.exists():
    raise SystemExit("Run npm ci in frontend first.")
task_env=os.environ.copy()
task_env.update(QS_MODE="demo",QS_STORAGE_DIR=str(root/".state/demo"),QS_PUBLIC_ORIGIN="http://127.0.0.1:5173")
processes=[]
def stop(*_):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    raise SystemExit(0)
signal.signal(signal.SIGINT,stop)
signal.signal(signal.SIGTERM,stop)
processes.append(subprocess.Popen([str(python),"-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000","--no-access-log"],cwd=root,env=task_env))
processes.append(subprocess.Popen([node,str(vite),"--host","127.0.0.1","--port","5173","--strictPort"],cwd=root/"frontend",env=task_env))
print("Quant Stock demo: http://127.0.0.1:5173 — press Ctrl+C to stop.",flush=True)
try:
    while all(p.poll() is None for p in processes):
        time.sleep(1)
finally:
    stop()
