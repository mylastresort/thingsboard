#!/usr/bin/env python3
"""
deploy.py — Build + deploy the SimPy widget bundle to ThingsBoard.

Finds any existing bundle with alias "simpy_widgets", deletes it,
then re-imports the freshly-generated bundle.

Usage:
    python deploy.py
    python deploy.py --url http://192.168.1.10:8080 --user tenant@thingsboard.org --password tenant
"""

import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
BUNDLE_ALIAS = "simpy_widgets"

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://localhost:8080", help="ThingsBoard base URL")
p.add_argument("--user", default="tenant@thingsboard.org")
p.add_argument("--password", default="tenant")
args = p.parse_args()
BASE = args.url.rstrip("/")

# ── install requests if missing ────────────────────────────────────────────────
if importlib.util.find_spec("requests") is None:
    print("Installing requests…")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
import requests  # noqa: E402

# ── step 1: build bundle ───────────────────────────────────────────────────────
print("Building bundle…")
subprocess.check_call([sys.executable, str(HERE / "bundle.py")])
bundle_path = HERE / "simpy_widget_bundle.json"
bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

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
print("  Authenticated ✓")

# ── step 3: find & delete existing bundle ─────────────────────────────────────
print(f"Looking for existing bundle '{BUNDLE_ALIAS}'…")
r = requests.get(
    f"{BASE}/api/widgetsBundles?pageSize=100&page=0", headers=hdrs, timeout=10
)
if r.ok:
    for b in r.json().get("data", []):
        if b.get("alias") == BUNDLE_ALIAS:
            bid = b["id"]["id"]
            print(f"  Deleting existing bundle {bid}…")
            dr = requests.delete(
                f"{BASE}/api/widgetsBundle/{bid}", headers=hdrs, timeout=10
            )
            if dr.ok:
                print("  Deleted ✓")
            else:
                print(f"  [WARN] Delete returned {dr.status_code}")

# ── step 4: import new bundle ──────────────────────────────────────────────────
print("Importing bundle…")
r = requests.post(
    f"{BASE}/api/widgetsBundle/import",
    json=bundle,
    headers=hdrs,
    timeout=30,
)
if not r.ok:
    print(f"[ERROR] Import failed {r.status_code}: {r.text}")
    sys.exit(1)

imported = r.json()
print(
    f"[OK] Bundle imported: '{imported.get('title')}' (alias: {imported.get('alias')})"
)
print(f"     Open ThingsBoard → Widget Library → SimPy Widgets")
