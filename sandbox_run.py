#!/usr/bin/env python
"""
ERPlora Hub - Sandbox Runner

Wipes sandbox directories (before Django loads to avoid SystemCheckErrors),
then runs migrate + gunicorn with --reload.

Usage:
    HUB_ENV=sandbox python sandbox_run.py          # wipe + migrate + gunicorn :8000
    HUB_ENV=sandbox python sandbox_run.py 8080     # custom port
    HUB_ENV=sandbox python sandbox_run.py --no-run # wipe + migrate only
"""

import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Step 1: Wipe sandbox (NO Django imports — avoids SystemCheckError)
# ---------------------------------------------------------------------------

if sys.platform == "darwin":
    SANDBOX_BASE = Path.home() / "Library" / "Application Support" / "ERPloraHub-sandbox"
else:
    SANDBOX_BASE = Path.home() / ".erplora-hub-sandbox"

for subdir in ['db', 'modules']:
    d = SANDBOX_BASE / subdir
    if d.exists():
        shutil.rmtree(d)
        print(f'[SANDBOX] Wiped {d}')
    d.mkdir(parents=True, exist_ok=True)

for subdir in ['media', 'logs', 'module_data']:
    (SANDBOX_BASE / subdir).mkdir(parents=True, exist_ok=True)

print('[SANDBOX] Clean environment ready')

# ---------------------------------------------------------------------------
# Step 2: Exec manage.py sandbox (Django loads with clean module dir)
# ---------------------------------------------------------------------------

args = sys.argv[1:]  # Forward port, --no-run, etc.
cmd = [sys.executable, 'manage.py', 'sandbox'] + args

env = os.environ.copy()
env['HUB_ENV'] = 'sandbox'

os.execve(sys.executable, cmd, env)
