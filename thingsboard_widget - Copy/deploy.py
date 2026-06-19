#!/usr/bin/env python3
"""
deploy.py — Build + deploy the FlexSim widget bundle to ThingsBoard.

Finds any existing bundle with alias "flexsim_widgets", deletes it,
then re-imports the freshly-generated bundle — so there is always
exactly one up-to-date copy.

Usage:
    python deploy.py
    python deploy.py --url http://192.168.1.10:8080 --user tenant@thingsboard.org --password tenant

Requires: pip install requests   (or: uv add requests)
"""

import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
BUNDLE_ALIAS = "flexsim_widgets"

# ── parse args ─────────────────────────────────────────────────────────────────
p = argparse.ArgumentParser()
p.add_argument("--url", default="http://localhost:8080", help="ThingsBoard base URL")
p.add_argument("--user", default="tenant@thingsboard.org", help="ThingsBoard username")
p.add_argument("--password", default="tenant", help="ThingsBoard password")
args = p.parse_args()
BASE = args.url.rstrip("/")

# ── import requests ─────────────────────────────────────────────────────────────
if importlib.util.find_spec("requests") is None:
    print("Installing requests…")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
import requests  # noqa: E402

# ── step 1: regenerate bundle ──────────────────────────────────────────────────
print("Building bundle…")
subprocess.check_call([sys.executable, str(HERE / "bundle.py")])
bundle = json.loads((HERE / "flexsim_widget_bundle.json").read_text(encoding="utf-8"))

# ── step 2: authenticate ───────────────────────────────────────────────────────
print(f"Authenticating with {BASE}…")
r = requests.post(
    f"{BASE}/api/auth/login",
    json={"username": args.user, "password": args.password},
    timeout=10,
)
if not r.ok:
    print(f"[ERROR] Login failed {r.status_code}: {r.text}")
    sys.exit(1)

hdrs = {
    "X-Authorization": f"Bearer {r.json()['token']}",
    "Content-Type": "application/json",
}

# ── step 3: delete existing bundle(s) with same alias ─────────────────────────
print("Checking for existing bundle…")
r = requests.get(
    f"{BASE}/api/widgetsBundles",
    params={"pageSize": 200, "page": 0},
    headers=hdrs,
    timeout=10,
)
r.raise_for_status()

data = r.json()
# TB 3.x wraps list in {"data": [...]}; older versions return a plain list
bundles = data.get("data", data) if isinstance(data, dict) else data

deleted = 0
for b in bundles:
    if b.get("alias") == BUNDLE_ALIAS:
        bid = b["id"]["id"]
        dr = requests.delete(
            f"{BASE}/api/widgetsBundle/{bid}", headers=hdrs, timeout=10
        )
        if dr.ok:
            print(f"  Deleted bundle {bid}")
            deleted += 1
        else:
            print(f"  [WARN] Could not delete {bid}: {dr.status_code}")

if deleted == 0:
    print("  No existing bundle found — will create fresh.")

# ── step 4: import new bundle ──────────────────────────────────────────────────
print("Importing bundle…")
r = requests.post(
    f"{BASE}/api/widgetsBundle/import", json=bundle, headers=hdrs, timeout=30
)
if r.ok:
    bid = r.json().get("widgetsBundle", {}).get("id", {}).get("id", "?")
    print(f"[OK] Bundle deployed (id: {bid})")
    print("     Refresh the ThingsBoard page to pick up the changes.")
else:
    print(f"[ERROR] Import failed {r.status_code}: {r.text}")
    sys.exit(1)
