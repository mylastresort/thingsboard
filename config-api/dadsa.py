src = open("./optimize_line2.py").read()

# 1. Replace adjust_param_bounds signature + body to use synced_values pivot
old_fn = '''def adjust_param_bounds(cfg: dict, base_config: Line2Config) -> dict:
    """
    Narrow or shift each sensor decision-variable bound before the study starts.

    The YAML values act as hard outer limits; this function tightens them
    dynamically around the base config\'s current sensor values using a
    symmetric margin.  Set MARGIN = 1.0 to leave bounds unchanged.

    Override the per-sensor logic below for asymmetric or sensor-specific rules.
    """
    import copy

    MARGIN = 0.25  # ±25 % around the current base value

    cfg = copy.deepcopy(cfg)
    dvars = cfg["decision_variables"]

    current_sensors: dict[str, dict[str, list[float]]] = {
        "pdm1_sensors": {k: list(v) for k, v in base_config.pdm1_sensors.items()},
        "pdm2_sensors": {k: list(v) for k, v in base_config.pdm2_sensors.items()},
    }

    for param_name, spec in dvars.items():
        parts = param_name.split(".")
        if len(parts) != 3:
            continue  # scalar param — leave untouched
        grp, sensor_name, bound = parts
        if grp not in current_sensors or sensor_name not in current_sensors[grp]:
            continue

        idx = 0 if bound == "min" else 1
        base_val = current_sensors[grp][sensor_name][idx]

        if base_val == 0.0:
            continue  # avoid zero-pivot; keep YAML range as-is

        new_low  = base_val * (1.0 - MARGIN)
        new_high = base_val * (1.0 + MARGIN)

        # Respect hard outer limits from the YAML.
        spec["low"]  = max(spec["low"],  new_low)
        spec["high"] = min(spec["high"], new_high)

        # Guard against low >= high after clamping.
        if spec["low"] >= spec["high"]:
            spec["low"]  = min(new_low,  spec["high"] * 0.9)
            spec["high"] = max(new_high, spec["low"]  * 1.1)

    return cfg'''

new_fn = '''def adjust_param_bounds(
    cfg: dict,
    base_config: Line2Config,
    synced_values: dict[str, float] | None = None,
) -> dict:
    """
    Narrow or shift each sensor decision-variable bound before the study starts.

    If `synced_values` is provided (keys like ``\'pdm1_sensors.vibration.min\'``),
    those live telemetry values are used as the pivot instead of base_config.
    The YAML values act as hard outer limits.  Set MARGIN = 1.0 to leave bounds
    unchanged.
    """
    import copy

    MARGIN = 0.25  # ±25 % around the pivot value

    cfg = copy.deepcopy(cfg)
    dvars = cfg["decision_variables"]

    # Build pivot: dotted param name -> current value.
    # Priority: synced_values (live TB data) > base_config defaults.
    if synced_values is not None:
        pivot_map: dict[str, float] = synced_values
    else:
        pivot_map = {}
        for grp, sensors in [
            ("pdm1_sensors", base_config.pdm1_sensors),
            ("pdm2_sensors", base_config.pdm2_sensors),
        ]:
            for sensor_name, (lo, hi) in sensors.items():
                pivot_map[f"{grp}.{sensor_name}.min"] = lo
                pivot_map[f"{grp}.{sensor_name}.max"] = hi

    for param_name, spec in dvars.items():
        if len(param_name.split(".")) != 3:
            continue  # scalar param — leave untouched

        base_val = pivot_map.get(param_name)
        if base_val is None or base_val == 0.0:
            continue  # no pivot available; keep YAML range as-is

        new_low  = base_val * (1.0 - MARGIN)
        new_high = base_val * (1.0 + MARGIN)

        # Respect hard outer limits from the YAML.
        spec["low"]  = max(spec["low"],  new_low)
        spec["high"] = min(spec["high"], new_high)

        # Guard against low >= high after clamping.
        if spec["low"] >= spec["high"]:
            spec["low"]  = min(new_low,  spec["high"] * 0.9)
            spec["high"] = max(new_high, spec["low"]  * 1.1)

    return cfg'''

assert old_fn in src, "adjust_param_bounds not found"
src = src.replace(old_fn, new_fn, 1)

# 2. Add synced_values param to run_opt signature and pass it through
old_sig = """def run_opt(
    cfg_path: Path,
    args: argparse.Namespace,
    base_config: Line2Config,
) -> tuple[optuna.Study, dict]:
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    print(f"[config] Loaded: {cfg_path}")
    cfg = adjust_param_bounds(cfg, base_config)"""

new_sig = """def run_opt(
    cfg_path: Path,
    args: argparse.Namespace,
    base_config: Line2Config,
    synced_values: dict[str, float] | None = None,
) -> tuple[optuna.Study, dict]:
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    print(f"[config] Loaded: {cfg_path}")
    cfg = adjust_param_bounds(cfg, base_config, synced_values)"""

assert old_sig in src, "run_opt signature not found"
src = src.replace(old_sig, new_sig, 1)

open("./optimize_line2.py", "w").write(src)
print("done")
