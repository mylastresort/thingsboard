"""
Optuna-based optimization of Line 2 simulation — mirrors OptQuest in FlexSim.

The YAML config defines decision variables (search space), objectives, optional
constraints, and sampler settings.  Each Optuna trial runs the SimPy model with
a suggested parameter set; the sampler (TPE by default) learns to improve the
objective across trials, exactly as OptQuest does in FlexSim.

Usage
─────
    python optimize_line2.py                            # optuna_config.yaml + DB
    python optimize_line2.py --no-db                    # built-in defaults
    python optimize_line2.py --config custom.yaml       # custom YAML
    python optimize_line2.py --no-db --trials 200       # override trial count
    python optimize_line2.py --no-db --output best.json # save best trial(s)
    python optimize_line2.py --no-db --quiet            # suppress progress bar
    python optimize_line2.py --no-db \
        --study-db sqlite:///study.db                   # persist / resume study
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
import requests
import asyncio

try:
    import yaml
except ImportError:
    print("[error] PyYAML not installed.  Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    import optuna
    import optuna.trial
except ImportError:
    print("[error] Optuna not installed.  Run: pip install optuna", file=sys.stderr)
    sys.exit(1)

import sim_model
from sim_model import Line2Config

DEFAULT_CONFIG_PATH = Path(__file__).parent / "optuna_config.yaml"

# RUN_SIMULATION_TEMPLATE_PATH = (
#     Path(__file__).resolve().parents[3] / "run_simulation_tp.fs"
# )

# Hardcoded database URL for exporting results
DATABASE_URL = "sqlite:///./results.db"
THINGSBOARD_HOST = "localhost"
THINGSBOARD_USERNAME = "tenant@thingsboard.org"
THINGSBOARD_PASSWORD = "tenant"
THINGSBOARD_SYNC_PROFILES = {
    "pdm1": {
        "entity_type": "DEVICE",
        "entity_id": "9f45fd90-0b66-11f1-add6-958e4a75fa7a",
        "telemetry_keys": ["vibration", "pressure", "volt", "rotate"],
        "parameter_prefix": "pdm1_sensors",
    },
}
THINGSBOARD_PRIVATE_SYNC_PROFILE = "pdm1"
THINGSBOARD_PRIVATE_INTERVAL_MS: int = 60_000

# ──────────────────────────────────────────────────────────────────────────────
#  In-memory aggregation config
# ──────────────────────────────────────────────────────────────────────────────

_DEFAULT_AGGREGATION: dict = {"mode": "range", "method": None}


def _init_aggregation_config() -> dict[str, dict]:
    """Seed every sensor key from THINGSBOARD_SYNC_PROFILES with range defaults."""
    cfg: dict[str, dict] = {}
    for profile in THINGSBOARD_SYNC_PROFILES.values():
        prefix = profile["parameter_prefix"]
        for key in profile["telemetry_keys"]:
            cfg[f"{prefix}.{key}"] = dict(_DEFAULT_AGGREGATION)
    return cfg


AGGREGATION_CONFIG: dict[str, dict] = _init_aggregation_config()


def get_param_aggregation(param_key: str) -> dict:
    return AGGREGATION_CONFIG.get(param_key, _DEFAULT_AGGREGATION)


def set_param_aggregation(updates: dict[str, dict]) -> None:
    AGGREGATION_CONFIG.update(updates)


# ──────────────────────────────────────────────────────────────────────────────
#  Parameter helpers
# ──────────────────────────────────────────────────────────────────────────────


def suggest_param(trial: optuna.Trial, name: str, spec: dict) -> Any:
    vtype = spec["type"]
    if vtype == "float":
        return trial.suggest_float(name, spec["low"], spec["high"])
    if vtype == "log_float":
        return trial.suggest_float(name, spec["low"], spec["high"], log=True)
    if vtype == "int":
        return trial.suggest_int(
            name, spec["low"], spec["high"], step=spec.get("step", 1)
        )
    if vtype == "categorical":
        return trial.suggest_categorical(name, spec["choices"])
    raise ValueError(f"Unknown parameter type: {vtype!r}")


def build_config(params: dict, base: Line2Config) -> Line2Config:
    """
    Overlay `params` onto a base Line2Config.

    Scalar keys:  iat_mean, pdm1_cycle_time, pdm2_cycle_time, final_cycle_time
    Sensor keys:  pdm1_sensors.<name>  or  pdm2_sensors.<name>

    Sensor bounds are auto-sorted so min <= max regardless of how Optuna
    samples the two endpoints (they are independent suggest calls).
    """
    scalar = {
        "iat_mean": base.iat_mean,
        "pdm1_cycle_time": base.pdm1_cycle_time,
        "pdm2_cycle_time": base.pdm2_cycle_time,
        "final_cycle_time": base.final_cycle_time,
    }
    sensors = {
        "pdm1_sensors": {k: list(v) for k, v in base.pdm1_sensors.items()},
        "pdm2_sensors": {k: list(v) for k, v in base.pdm2_sensors.items()},
    }

    for name, value in params.items():
        parts = name.split(".")
        if len(parts) == 1:
            if name not in scalar:
                raise ValueError(f"Unknown scalar parameter: {name!r}")
            scalar[name] = value
        elif len(parts) == 2 and parts[0] in sensors:
            grp, sensor_name = parts
            if sensor_name not in sensors[grp]:
                sensors[grp][sensor_name] = [0.0, 1.0]
            sensors[grp][sensor_name] = [value, value]
        else:
            raise ValueError(
                f"Cannot map parameter {name!r}. "
                "Expected a scalar key or dotted sensor path "
                "(e.g. 'pdm1_sensors.pressure.max')."
            )

    # Optuna samples min/max independently — enforce ordering so the sim
    # never receives an inverted range.
    for grp in sensors:
        for sname in sensors[grp]:
            lo, hi = sensors[grp][sname]
            if lo > hi:
                sensors[grp][sname] = [hi, lo]

    return Line2Config(
        iat_mean=scalar["iat_mean"],
        pdm1_cycle_time=scalar["pdm1_cycle_time"],
        pdm2_cycle_time=scalar["pdm2_cycle_time"],
        final_cycle_time=scalar["final_cycle_time"],
        pdm1_sensors={k: tuple(v) for k, v in sensors["pdm1_sensors"].items()},
        pdm2_sensors={k: tuple(v) for k, v in sensors["pdm2_sensors"].items()},
    )


# ──────────────────────────────────────────────────────────────────────────────
#  Metric / constraint helpers
# ──────────────────────────────────────────────────────────────────────────────


def extract_metric(result: dict, metric: str) -> float:
    # Check nested sink dicts first, then top-level result.
    for key in ("sink2", "sink1"):
        sub = result.get(key, {})
        if metric in sub:
            return float(sub[metric])
    if metric in result:
        return float(result[metric])
    nested = {k: v for k, v in result.items() if isinstance(v, dict)}
    nested_keys = [k for sub in nested.values() for k in sub]
    available = nested_keys + [k for k in result if k not in nested]
    raise KeyError(
        f"Metric {metric!r} not found in simulation output.\n"
        f"  Available keys: {available}"
    )


def eval_constraints(result: dict, constraints: list[dict]) -> list[float]:
    """
    Return violation values for each constraint.
    <=0  →  satisfied
    > 0  →  infeasible (magnitude = how far outside the bound)
    """
    violations = []
    for c in constraints:
        val = extract_metric(result, c["metric"])
        bound = float(c["value"])
        op = c["operator"]
        if op in ("<=", "<"):
            violations.append(val - bound)
        elif op in (">=", ">"):
            violations.append(bound - val)
        else:
            raise ValueError(f"Unknown constraint operator: {op!r}  (use <=, >=, <, >)")
    return violations


# ──────────────────────────────────────────────────────────────────────────────
#  Sampler factory
# ──────────────────────────────────────────────────────────────────────────────


def make_sampler(
    name: str, seed: int | None, constraints_func
) -> optuna.samplers.BaseSampler:
    name = name.lower()
    if name == "tpe":
        return optuna.samplers.TPESampler(seed=seed, constraints_func=constraints_func)
    if name == "cmaes":
        if constraints_func is not None:
            print("[warn] CMA-ES does not support constraints; they will be ignored.")
        return optuna.samplers.CmaEsSampler(seed=seed)
    if name == "random":
        return optuna.samplers.RandomSampler(seed=seed)
    if name in ("nsga2", "nsgaii"):
        return optuna.samplers.NSGAIISampler(
            seed=seed, constraints_func=constraints_func
        )
    if name in ("nsga3", "nsgaiii"):
        return optuna.samplers.NSGAIIISampler(seed=seed)
    raise ValueError(
        f"Unknown sampler {name!r}.  Valid choices: tpe, cmaes, random, nsga2, nsga3"
    )


# ──────────────────────────────────────────────────────────────────────────────
#  Objective function
# ──────────────────────────────────────────────────────────────────────────────


def make_objective(cfg: dict, base_config: Line2Config):
    decision_vars = cfg["decision_variables"]
    objectives = cfg["objectives"]
    constraints = cfg.get("constraints", [])
    sim_cfg = cfg.get("simulation", {})
    sim_time = float(sim_cfg.get("sim_time", sim_model.DEFAULT_SIM_TIME))
    n_reps = int(sim_cfg.get("n_replications", 1))
    base_seed = int(sim_cfg.get("seed", sim_model.DEFAULT_RANDOM_SEED))
    is_multi = len(objectives) > 1

    def objective(trial: optuna.Trial):
        params = {n: suggest_param(trial, n, s) for n, s in decision_vars.items()}
        config = build_config(params, base_config)

        metric_sums = {obj["metric"]: 0.0 for obj in objectives}
        constr_sums = [0.0] * len(constraints)

        for rep in range(n_reps):
            result = sim_model.run(
                sim_time=sim_time,
                random_seed=base_seed + rep,
                verbose=False,
                config=config,
            )
            for obj in objectives:
                metric_sums[obj["metric"]] += extract_metric(result, obj["metric"])
            if constraints:
                for i, v in enumerate(eval_constraints(result, constraints)):
                    constr_sums[i] += v

        # Store averaged constraint violations so the sampler can learn feasibility
        if constraints:
            trial.set_user_attr("constraints", [v / n_reps for v in constr_sums])

        values = [metric_sums[obj["metric"]] / n_reps for obj in objectives]
        return tuple(values) if is_multi else values[0]

    return objective


# ──────────────────────────────────────────────────────────────────────────────
#  Results printer
# ──────────────────────────────────────────────────────────────────────────────


def print_results(study: optuna.Study, cfg: dict, base_config: Line2Config) -> None:
    objectives = cfg["objectives"]
    is_multi = len(objectives) > 1
    perf_measures = cfg.get("performance_measures", [])
    sim_cfg = cfg.get("simulation", {})
    sim_time = float(sim_cfg.get("sim_time", sim_model.DEFAULT_SIM_TIME))
    seed = int(sim_cfg.get("seed", sim_model.DEFAULT_RANDOM_SEED))
    W = 66

    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]

    print(f"\n{'═' * W}")
    print(f"  Optuna Optimization Results  —  Line 2")
    print(f"{'═' * W}")
    print(f"  Trials completed : {len(completed)} / {len(study.trials)}")
    print(f"  Sampler          : {type(study.sampler).__name__}")

    if is_multi:
        pareto = study.best_trials
        print(f"  Pareto front     : {len(pareto)} solutions")
        for i, t in enumerate(pareto):
            print(f"\n  ── Pareto #{i + 1}  (trial #{t.number})")
            for j, obj in enumerate(objectives):
                print(
                    f"    {obj['metric']:<36} {t.values[j]:.6g}  [{obj['direction']}]"
                )
            print(f"    Decision variables:")
            for k, v in t.params.items():
                fmt = (
                    f"      {k:<34} {v:.4g}"
                    if isinstance(v, float)
                    else f"      {k:<34} {v}"
                )
                print(fmt)
    else:
        t = study.best_trial
        obj = objectives[0]
        print(f"  Objective        : {obj['direction']} {obj['metric']}")
        print(f"  Best value       : {t.value:.6g}")
        print(f"  Best trial #     : {t.number}")
        print(f"{'─' * W}")
        print(f"  Best decision variables:")
        for k, v in t.params.items():
            fmt = f"    {k:<36} {v:.4g}" if isinstance(v, float) else f"    {k:<36} {v}"
            print(fmt)

        if perf_measures:
            print(f"{'─' * W}")
            print(f"  All performance measures (best config, 1 run):")
            best_config = build_config(t.params, base_config)
            result = sim_model.run(
                sim_time=sim_time,
                random_seed=seed,
                verbose=False,
                config=best_config,
            )
            for m in perf_measures:
                try:
                    val = extract_metric(result, m)
                    print(f"    {m:<36} {val}")
                except KeyError:
                    pass

    print(f"{'═' * W}")


def _coerce_parameter_value(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return value
    lower_value = stripped.lower()
    if lower_value in {"true", "false"}:
        return lower_value == "true"
    try:
        if any(marker in lower_value for marker in (".", "e")):
            return float(stripped)
        return int(stripped)
    except ValueError:
        return value


def _extract_series_value(payload: dict[str, Any], key: str) -> Any:
    entries = payload.get(key, [])
    if not entries:
        raise ValueError(f"No telemetry values found for key '{key}'")
    value = entries[0].get("value")
    # Parse string values to appropriate types
    if isinstance(value, str):
        value = _coerce_parameter_value(value)
    return value


def _validate_min_max_parameters(parameters: dict[str, Any]) -> list[str]:
    """
    Validate that min/max parameter counterparts are valid.
    Returns a list of validation errors (empty if all valid).
    """
    errors = []
    for key, value in parameters.items():
        if key.endswith("_min"):
            base_key = key[:-4]  # Remove '_min' suffix
            max_key = f"{base_key}_max"
            if max_key in parameters:
                min_val = value
                max_val = parameters[max_key]
                # Ensure both are numeric
                if not isinstance(min_val, (int, float)):
                    errors.append(
                        f"Min parameter '{key}' has non-numeric value: {min_val}"
                    )
                elif not isinstance(max_val, (int, float)):
                    errors.append(
                        f"Max parameter '{max_key}' has non-numeric value: {max_val}"
                    )
                # Ensure min <= max
                elif min_val > max_val:
                    errors.append(
                        f"Min parameter '{key}' ({min_val}) exceeds max parameter '{max_key}' ({max_val})"
                    )
    return errors


def _fetch_timeseries(
    token: str, entity_type: str, entity_id: str, params: dict[str, Any],
    host = THINGSBOARD_HOST
) -> dict[str, Any]:
    response = requests.get(
        f"http://{host}:8080/api/plugins/telemetry/{entity_type}/{entity_id}/values/timeseries",
        params=params,
        headers={
            "X-Authorization": token,
            "Content-Type": "application/json",
            "accept": "application/json",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# def _build_synced_parameters(
#     prefix: str,
#     telemetry_keys: list[str],
#     min_payload: dict[str, Any],
#     max_payload: dict[str, Any],
# ) -> dict[str, Any]:
#     synced_parameters: dict[str, Any] = {}
#     for telemetry_key in telemetry_keys:
#         synced_parameters[f"{prefix}.{telemetry_key}.min"] = _extract_series_value(
#             min_payload, telemetry_key
#         )
#         # synced_parameters[f"{prefix}{telemetry_key}_min"] = 100000
#         synced_parameters[f"{prefix}.{telemetry_key}.max"] = _extract_series_value(
#             max_payload, telemetry_key
#         )

#     # Validate min/max counterparts
#     validation_errors = _validate_min_max_parameters(synced_parameters)
#     if validation_errors:
#         raise ValueError(f"Invalid parameter values: {'; '.join(validation_errors)}")

#     return synced_parameters

def _build_synced_parameters(
    prefix: str,
    telemetry_keys: list[str],
    min_payload: dict[str, Any],
    max_payload: dict[str, Any],
    avg_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    synced_parameters: dict[str, Any] = {}

    for telemetry_key in telemetry_keys:
        param_key = f"{prefix}.{telemetry_key}"
        agg = get_param_aggregation(param_key)

        min_val = _extract_series_value(min_payload, telemetry_key)
        max_val = _extract_series_value(max_payload, telemetry_key)

        if agg["mode"] == "constant":
            method = agg.get("method") or "average"
            if method == "min":
                lo = hi = min_val
            elif method == "max":
                lo = hi = max_val
            elif method == "median":
                # TB has no native MEDIAN — approximate as midpoint of [min, max]
                lo = hi = (min_val + max_val) / 2.0
            else:  # "average"
                lo = hi = (
                    _extract_series_value(avg_payload, telemetry_key)
                    if avg_payload
                    else (min_val + max_val) / 2.0
                )
            print(f"[agg] {param_key}: constant/{method} → {lo}")
        else:  # "range" — default
            lo, hi = min_val, max_val
            print(f"[agg] {param_key}: range → [{lo}, {hi}]")

        synced_parameters[f"{param_key}.min"] = lo
        synced_parameters[f"{param_key}.max"] = hi

    validation_errors = _validate_min_max_parameters(synced_parameters)
    if validation_errors:
        raise ValueError(f"Invalid parameter values: {'; '.join(validation_errors)}")

    return synced_parameters

def _authenticate_thingsboard(
    username: str = THINGSBOARD_USERNAME, password: str = THINGSBOARD_PASSWORD,
    host = THINGSBOARD_HOST
) -> str:
    response = requests.post(
        f"http://{host}:8080/api/auth/login",
        headers={"accept": "application/json", "Content-Type": "application/json"},
        json={"username": username, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    return f"Bearer {response.json()['token']}"


# ──────────────────────────────────────────────────────────────────────────────
#  Param-bound adjustment (called once before optimization starts)
# ──────────────────────────────────────────────────────────────────────────────


def _extract_latest_ts(payload: dict[str, Any], keys: list[str]) -> int | None:
    latest_ts = None
    for key in keys:
        entries = payload.get(key, [])
        for entry in entries:
            ts = entry.get("ts")
            if ts is None:
                continue
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
    return latest_ts


# async def sync_model_parameters_from_thingsboard(
#         host = THINGSBOARD_HOST
# ) -> dict[str, float] | None:
#     sync_profile = THINGSBOARD_PRIVATE_SYNC_PROFILE
#     interval_ms = THINGSBOARD_PRIVATE_INTERVAL_MS
#     profile = THINGSBOARD_SYNC_PROFILES.get(sync_profile)
#     if profile is None:
#         raise ValueError(f"Unknown sync profile: {sync_profile}")

#     telemetry_keys = profile["telemetry_keys"]
#     token = _authenticate_thingsboard(host=host)
#     latest_payload = _fetch_timeseries(
#         token,
#         profile["entity_type"],
#         profile["entity_id"],
#         {
#             "keys": ",".join(telemetry_keys),
#             "useStrictDataTypes": "false",
#         },
#         host
#     )
#     latest_ts = _extract_latest_ts(latest_payload, telemetry_keys)
#     if latest_ts is None:
#         raise ValueError(f"No telemetry found for profile '{sync_profile}'")

#     interval_start = latest_ts - interval_ms
#     interval_end = latest_ts + 1
#     min_payload = _fetch_timeseries(
#         token,
#         profile["entity_type"],
#         profile["entity_id"],
#         {
#             "keys": ",".join(telemetry_keys),
#             "startTs": interval_start,
#             "endTs": interval_end,
#             "interval": interval_ms,
#             "agg": "MIN",
#             "orderBy": "ASC",
#             "useStrictDataTypes": "false",
#         },
#         host
#     )
#     max_payload = _fetch_timeseries(
#         token,
#         profile["entity_type"],
#         profile["entity_id"],
#         {
#             "keys": ",".join(telemetry_keys),
#             "startTs": interval_start,
#             "endTs": interval_end,
#             "interval": interval_ms,
#             "agg": "MAX",
#             "orderBy": "ASC",
#             "useStrictDataTypes": "false",
#         },
#         host
#     )

#     synced_parameters = _build_synced_parameters(
#         profile["parameter_prefix"], telemetry_keys, min_payload, max_payload
#     )

#     return synced_parameters

async def sync_model_parameters_from_thingsboard(
        host = THINGSBOARD_HOST
) -> dict[str, float] | None:
    sync_profile = THINGSBOARD_PRIVATE_SYNC_PROFILE
    interval_ms = THINGSBOARD_PRIVATE_INTERVAL_MS
    profile = THINGSBOARD_SYNC_PROFILES.get(sync_profile)
    if profile is None:
        raise ValueError(f"Unknown sync profile: {sync_profile}")

    telemetry_keys = profile["telemetry_keys"]
    token = _authenticate_thingsboard(host=host)
    latest_payload = _fetch_timeseries(
        token,
        profile["entity_type"],
        profile["entity_id"],
        {
            "keys": ",".join(telemetry_keys),
            "useStrictDataTypes": "false",
        },
        host
    )
    latest_ts = _extract_latest_ts(latest_payload, telemetry_keys)
    if latest_ts is None:
        raise ValueError(f"No telemetry found for profile '{sync_profile}'")

    interval_start = latest_ts - interval_ms
    interval_end = latest_ts + 1

    base_params = {
        "keys": ",".join(telemetry_keys),
        "startTs": interval_start,
        "endTs": interval_end,
        "interval": interval_ms,
        "orderBy": "ASC",
        "useStrictDataTypes": "false",
    }

    min_payload = _fetch_timeseries(token, profile["entity_type"], profile["entity_id"],
                                    {**base_params, "agg": "MIN"}, host)
    max_payload = _fetch_timeseries(token, profile["entity_type"], profile["entity_id"],
                                    {**base_params, "agg": "MAX"}, host)
    avg_payload = _fetch_timeseries(token, profile["entity_type"], profile["entity_id"],
                                    {**base_params, "agg": "AVG"}, host)

    synced_parameters = _build_synced_parameters(
        profile["parameter_prefix"], telemetry_keys,
        min_payload, max_payload, avg_payload
    )
    return synced_parameters


def adjust_param_bounds(
    cfg: dict,
    base_config: Line2Config,
    synced_values: dict[str, float] | None = None,
) -> dict:
    """
    Narrow or shift each sensor decision-variable bound before the study starts.

    If `synced_values` is provided (keys like ``'pdm1_sensors.vibration.min'``),
    those live telemetry values are used as the pivot instead of base_config.
    The YAML values act as hard outer limits.  Set MARGIN = 1.0 to leave bounds
    unchanged.
    """
    import copy

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
            print(f"[base config] Processing group '{grp}' for pivot values:")
            for sensor_name, (lo, hi) in sensors.items():
                print(f"[base config] {grp}.{sensor_name}: min={lo}, max={hi}")
                pivot_map[f"{grp}.{sensor_name}.min"] = lo
                pivot_map[f"{grp}.{sensor_name}.max"] = hi

    print(f"[adjust] Adjusting parameter bounds based on pivot values:")
    for param_name, spec in dvars.items():
        print(f"[adjust] Processing parameter '{param_name}' with original spec: {spec}")
        if len(param_name.split(".")) != 2:
            continue  # scalar param — leave untouched

        print(f"[adjust] Found sensor parameter '{param_name}'. Checking for pivot value...")

        edge_name = param_name.split(".")[-1]

        print(f"[adjust] Looking for pivot value for '{param_name}' (edge: {edge_name})...")

        base_val_min = pivot_map.get(param_name + ".min")
        base_val_max = pivot_map.get(param_name + ".max")
        if base_val_min is None or base_val_min == 0.0:
            continue  # no pivot available; keep YAML range as-is

        print(f"[adjust] Pivot value for '{param_name}': {base_val_min}. Adjusting bounds...")

        print(f"Prev YAML range for min {param_name}: {spec['low']} = {base_val_min} = {spec['high']}")
        spec["low"] = base_val_min
        print(f"Prev YAML range for max {param_name}: {spec['high']} = {base_val_max}")
        spec["high"] = base_val_max

    return cfg


# ──────────────────────────────────────────────────────────────────────────────
#  Optimization runner
# ──────────────────────────────────────────────────────────────────────────────

import sys

async def run_opt(
    cfg_path: Path,
    base_config: Line2Config,
    quiet: bool = False,
    trials: int | None = 100,
    synced_values: dict[str, float] | None = None,
    study_db: str | None = None,
    study_name: str = "line2_optimization",
    host = THINGSBOARD_HOST
) -> tuple[optuna.Study, dict]:
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    print(f"[config] Loaded: {cfg_path}")
    synced_values = await sync_model_parameters_from_thingsboard(
        host
    )

    print(f"[sync] Synced parameters from ThingsBoard ({THINGSBOARD_HOST}):")
    print(json.dumps(synced_values, indent=2))

    cfg = adjust_param_bounds(cfg, base_config, synced_values)
    # sys.exit(0)  # TEMP: skip optimization and just print synced values

    settings = cfg.get("settings", {})
    n_trials = trials or int(settings.get("n_trials", 100))
    objectives = cfg["objectives"]
    is_multi = len(objectives) > 1
    has_constr = bool(cfg.get("constraints"))
    sampler_name = settings.get("sampler", "tpe")
    sampler_seed = settings.get("seed", None)
    directions = [obj["direction"] for obj in objectives]

    constraints_func = (
        (lambda t: t.user_attrs.get("constraints", [])) if has_constr else None
    )
    sampler = make_sampler(sampler_name, sampler_seed, constraints_func)

    create_kwargs: dict[str, Any] = dict(
        sampler=sampler,
        storage=study_db,
        study_name=study_name,
        load_if_exists=bool(study_db),
    )
    if is_multi:
        create_kwargs["directions"] = directions
    else:
        create_kwargs["direction"] = directions[0]

    study = optuna.create_study(**create_kwargs)

    objective_fn = make_objective(cfg, base_config)
    show_progress = settings.get("show_progress", True) and not quiet

    obj_summary = ", ".join(f"{o['direction']} {o['metric']}" for o in objectives)
    print(
        f"[optuna] {n_trials} trials  |  sampler: {sampler_name.upper()}  |  objective: {obj_summary}"
    )
    study.optimize(objective_fn, n_trials=n_trials, show_progress_bar=show_progress)

    return study, cfg


# ──────────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Optuna optimization of Line 2 simulation (mirrors OptQuest).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML optimization config file.",
    )
    p.add_argument(
        "--trials",
        type=int,
        default=None,
        help="Override n_trials from the YAML config.",
    )
    p.add_argument(
        "--no-db",
        action="store_true",
        help="Use built-in defaults instead of loading config from DB.",
    )
    p.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save best trial(s) as JSON (e.g. best.json).",
    )
    p.add_argument(
        "--study-db",
        type=str,
        default=None,
        help="Optuna storage URL for a persistent study "
        "(e.g. sqlite:///study.db).  Supports resume.",
    )
    p.add_argument(
        "--study-name",
        type=str,
        default="line2_optimization",
        help="Study name — used with --study-db to resume an existing study.",
    )
    p.add_argument(
        "--quiet", action="store_true", help="Suppress Optuna logs and progress bar."
    )
    return p.parse_args()


async def main() -> None:
    args = parse_args()

    # ── Config path ───────────────────────────────────────────────────────────
    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"[error] Config file not found: {cfg_path}", file=sys.stderr)
        sys.exit(1)

    # ── Base sim config ───────────────────────────────────────────────────────
    if args.no_db:
        base_config = Line2Config()
        print("[config] Using built-in defaults for base sim config (--no-db).")
    else:
        if "DATABASE_URL" not in os.environ:
            print(
                "[error] DATABASE_URL is not set.  Pass --no-db to use built-in defaults.",
                file=sys.stderr,
            )
            sys.exit(1)
        from run_line2 import load_config_from_db

        base_config = load_config_from_db()

    # ── Optuna setup ──────────────────────────────────────────────────────────
    if args.quiet:
        optuna.logging.set_verbosity(optuna.logging.WARNING)

    study, cfg = await run_opt(
        cfg_path,
        base_config,
        quiet=args.quiet,
        trials=args.trials,
        study_db=args.study_db,
        study_name=args.study_name,
        )

    print(f"\n[optuna] Optimization completed. Best trial(s):")
    # ── Print results ─────────────────────────────────────────────────────────
    print_results(study, cfg, base_config)

    # ── Save JSON ─────────────────────────────────────────────────────────────
    if args.output:
        objectives = cfg["objectives"]
        is_multi = len(objectives) > 1
        if is_multi:
            data = [
                {
                    "trial": t.number,
                    "values": {
                        objectives[j]["metric"]: t.values[j]
                        for j in range(len(objectives))
                    },
                    "params": t.params,
                }
                for t in study.best_trials
            ]
        else:
            t = study.best_trial
            data = {"trial": t.number, "value": t.value, "params": t.params}
        Path(args.output).write_text(json.dumps(data, indent=2))
        print(f"\n[output] Best trial(s) saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
