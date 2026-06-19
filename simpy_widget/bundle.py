#!/usr/bin/env python3
"""
bundle.py  —  Generate a ThingsBoard widget bundle JSON for import.

Usage:
    python bundle.py

Output:
    simpy_widget_bundle.json   (import in ThingsBoard → Widget Library)
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def read(widget_dir: str, filename: str) -> str:
    p = HERE / widget_dir / filename
    if not p.exists():
        print(f"[ERROR] File not found: {p}", file=sys.stderr)
        sys.exit(1)
    return p.read_text(encoding="utf-8")


def make_settings_schema(fields: list[dict]) -> str:
    properties = {}
    form = []
    required = []
    for f in fields:
        properties[f["key"]] = {
            "title": f["title"],
            "type": "string",
            "default": f.get("default", ""),
        }
        form.append(f["key"])
        if f.get("required"):
            required.append(f["key"])
    schema_obj = {
        "schema": {
            "type": "object",
            "title": "Settings",
            "properties": properties,
        },
        "form": form,
    }
    if required:
        schema_obj["schema"]["required"] = required
    return json.dumps(schema_obj)


ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"

DEFAULT_SETTINGS = {
    "serverBaseUrl": "http://localhost:9000",
}

SETTINGS_FIELDS = [
    {
        "key": "serverBaseUrl",
        "title": "Config API Base URL",
        "default": "http://localhost:9000",
        "required": True,
    },
]

# ── Widget 1: Simulation Runner ────────────────────────────────────────────────
widget1 = {
    "alias": "simpy_line2_runner",
    "name": "SimPy — Line 2 Runner",
    "descriptor": {
        "type": "static",
        "sizeX": 12,
        "sizeY": 10,
        "resources": [{"url": ECHARTS_CDN, "isModule": False}],
        "templateHtml": read("widget1_runner", "html.html"),
        "templateCss": read("widget1_runner", "css.css"),
        "controllerScript": read("widget1_runner", "js.js"),
        "settingsSchema": make_settings_schema(SETTINGS_FIELDS),
        "dataKeySettingsSchema": "{}",
        "defaultConfig": json.dumps(
            {
                "title": "SimPy \u2014 Line 2 Runner",
                "showTitle": False,
                "padding": "0px",
                "widgetStyle": {},
                "datasources": [],
                "settings": DEFAULT_SETTINGS,
            }
        ),
    },
}

# ── Widget 2: Config Parameters ────────────────────────────────────────────────
widget2 = {
    "alias": "simpy_line2_params",
    "name": "SimPy — Line 2 Parameters",
    "descriptor": {
        "type": "static",
        "sizeX": 10,
        "sizeY": 8,
        "resources": [],
        "templateHtml": read("widget2_params", "html.html"),
        "templateCss": read("widget2_params", "css.css"),
        "controllerScript": read("widget2_params", "js.js"),
        "settingsSchema": make_settings_schema(SETTINGS_FIELDS),
        "dataKeySettingsSchema": "{}",
        "defaultConfig": json.dumps(
            {
                "title": "SimPy \u2014 Line 2 Parameters",
                "showTitle": False,
                "padding": "0px",
                "widgetStyle": {},
                "datasources": [],
                "settings": DEFAULT_SETTINGS,
            }
        ),
    },
}

LITEGRAPH_CDN = "https://cdn.jsdelivr.net/npm/litegraph.js@0.7.18/build/litegraph.js"

# ── Widget 3: Network Editor ───────────────────────────────────────────────────
widget3 = {
    "alias": "simpy_network_editor",
    "name": "SimPy — Network Editor",
    "descriptor": {
        "type": "static",
        "sizeX": 16,
        "sizeY": 12,
        "resources": [{"url": LITEGRAPH_CDN, "isModule": False}],
        "templateHtml": read("widget3_network", "html.html"),
        "templateCss": read("widget3_network", "css.css"),
        "controllerScript": read("widget3_network", "js.js"),
        "settingsSchema": make_settings_schema(SETTINGS_FIELDS),
        "dataKeySettingsSchema": "{}",
        "defaultConfig": json.dumps(
            {
                "title": "SimPy \u2014 Network Editor",
                "showTitle": False,
                "padding": "0px",
                "widgetStyle": {},
                "datasources": [],
                "settings": DEFAULT_SETTINGS,
            }
        ),
    },
}

# ── Bundle ─────────────────────────────────────────────────────────────────────
bundle = {
    "widgetsBundle": {
        "title": "SimPy Widgets",
        "alias": "simpy_widgets",
        "description": "SimPy Line 2 discrete-event simulation runner and config viewer for ThingsBoard.",
    },
    "widgetTypes": [widget1, widget2, widget3],
}

out = HERE / "simpy_widget_bundle.json"
out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"[OK] Written: {out}")
print("     Import in ThingsBoard → Widget Library → Import widgets bundle")
