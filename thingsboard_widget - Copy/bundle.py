#!/usr/bin/env python3
"""
bundle.py  —  Generate a ThingsBoard widget bundle JSON for import.

Usage:
    python bundle.py

Output:
    flexsim_widget_bundle.json   (import this file into TB → Widget Library)

Bundle format follows the ThingsBoard export schema:
  {
    "widgetsBundle": { "title":..., "alias":... },
    "widgetTypes":   [ { "alias":..., "name":..., "descriptor": {...} } ]
  }

settingsSchema uses the JSON Schema + Angular Schema Form format that
ThingsBoard's widget settings editor expects.
"""

import json, pathlib, sys

HERE = pathlib.Path(__file__).parent


# ── read source files ──────────────────────────────────────────────────────────
def read(widget_dir: str, filename: str) -> str:
    p = HERE / widget_dir / filename
    if not p.exists():
        print(f"[ERROR] File not found: {p}", file=sys.stderr)
        sys.exit(1)
    return p.read_text(encoding="utf-8")


# ── settings schema builder ────────────────────────────────────────────────────
def make_settings_schema(fields: list[dict]) -> str:
    """
    ThingsBoard 3.7 renders the Settings tab from a JSON Schema + form descriptor.
    The simple array shown in TB docs is only for the visual editor's
    "Import from JSON" convenience button — the stored/bundle format must be:
      { "schema": { "type":"object", "properties":{...} }, "form": [...] }
    """
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


# ── widget descriptors ─────────────────────────────────────────────────────────
ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"

widget1 = {
    "alias": "flexsim_simulations_list",
    "name": "FlexSim \u2013 Simulations List",
    "descriptor": {
        "type": "static",
        "sizeX": 8,
        "sizeY": 7,
        "resources": [],
        "templateHtml": read("widget1_list", "html.html"),
        "templateCss": read("widget1_list", "css.css"),
        "controllerScript": read("widget1_list", "js.js"),
        "settingsSchema": make_settings_schema(
            [
                {
                    "key": "serverBaseUrl",
                    "title": "Server Base URL",
                    "default": "http://localhost:8000",
                    "required": True,
                },
                {
                    "key": "apiToken",
                    "title": "API Token",
                    "default": "jessica",
                    "required": True,
                },
                {
                    "key": "detailStateId",
                    "title": "Detail Dashboard State ID",
                    "default": "simulation",
                    "required": True,
                },
            ]
        ),
        "dataKeySettingsSchema": "{}",
        "defaultConfig": json.dumps(
            {
                "title": "FlexSim \u2013 Simulations List",
                "showTitle": False,
                "padding": "0px",
                "widgetStyle": {},
                "datasources": [],
                "settings": {
                    "serverBaseUrl": "http://localhost:8000",
                    "apiToken": "jessica",
                    "detailStateId": "simulation",
                },
            }
        ),
    },
}

widget2 = {
    "alias": "flexsim_simulation_detail",
    "name": "FlexSim \u2013 Simulation Detail",
    "descriptor": {
        "type": "static",
        "sizeX": 20,
        "sizeY": 16,
        "resources": [{"url": ECHARTS_CDN, "isModule": False}],
        "templateHtml": read("widget2_detail", "html.html"),
        "templateCss": read("widget2_detail", "css.css"),
        "controllerScript": read("widget2_detail", "js.js"),
        "settingsSchema": make_settings_schema(
            [
                {
                    "key": "serverBaseUrl",
                    "title": "Server Base URL",
                    "default": "http://localhost:8000",
                    "required": True,
                },
                {
                    "key": "apiToken",
                    "title": "API Token",
                    "default": "jessica",
                    "required": True,
                },
            ]
        ),
        "dataKeySettingsSchema": "{}",
        "defaultConfig": json.dumps(
            {
                "title": "FlexSim \u2013 Simulation Detail",
                "showTitle": False,
                "padding": "0px",
                "widgetStyle": {},
                "datasources": [],
                "settings": {
                    "serverBaseUrl": "http://localhost:8000",
                    "apiToken": "jessica",
                },
            }
        ),
    },
}

widget3 = {
    "alias": "flexsim_opt_config_builder",
    "name": "FlexSim \u2013 Optimization Config Builder",
    "descriptor": {
        "type": "latest",
        "sizeX": 14,
        "sizeY": 14,
        "resources": [],
        "templateHtml": read("widget3_opt_config", "html.html"),
        "templateCss": read("widget3_opt_config", "css.css"),
        "controllerScript": read("widget3_opt_config", "js.js"),
        "settingsSchema": make_settings_schema(
            [
                {
                    "key": "serverBaseUrl",
                    "title": "Server Base URL (FastAPI)",
                    "default": "http://localhost:8000",
                    "required": True,
                },
                {
                    "key": "apiToken",
                    "title": "API Token (FastAPI)",
                    "default": "jessica",
                    "required": True,
                },
            ]
        ),
        "dataKeySettingsSchema": "{}",
        "defaultConfig": json.dumps(
            {
                "title": "FlexSim \u2013 Optimization Config Builder",
                "showTitle": False,
                "padding": "0px",
                "widgetStyle": {},
                "datasources": [],
                "settings": {
                    "serverBaseUrl": "http://localhost:8000",
                    "apiToken": "jessica",
                },
            }
        ),
    },
}

# ── assemble bundle (TB root-level format) ─────────────────────────────────────
# ThingsBoard expects widgetsBundle + widgetTypes at the TOP level,
# NOT wrapped inside a "widgetsBundleWidget" key.
bundle = {
    "widgetsBundle": {
        "title": "FlexSim Widgets",
        "alias": "flexsim_widgets",
        "description": "FlexSim simulation list + detail widgets for ThingsBoard.",
    },
    "widgetTypes": [widget1, widget2, widget3],
}

out = HERE / "flexsim_widget_bundle.json"
out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"[OK] Written: {out}")
print("     Import this file in ThingsBoard → Widget Library → Import widgets bundle")
