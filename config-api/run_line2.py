"""
Standalone Line 2 simulation runner.

Loads Line 2 object configs from the database and runs the SimPy PdM model.
Results are printed as formatted text and also saved as JSON.

Usage
─────
    # With a live database (DATABASE_URL env var required):
    DATABASE_URL=postgresql://config_user:config_pass@localhost:5432/config_db \
        python run_line2.py

    # Override sim time / seed:
    python run_line2.py --sim-time 5000 --seed 7

    # Use built-in defaults without a database:
    python run_line2.py --no-db

    # Save results to a file:
    python run_line2.py --output results.json

    # Verbose (prints resource utilisation every 5 000 s):
    python run_line2.py --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime
from pathlib import Path

import sim_model
from sim_model import Line2Config

# ──────────────────────────────────────────────────────────────────────────────
#  DB loader  (mirrors _build_line2_config in main.py)
# ──────────────────────────────────────────────────────────────────────────────


def load_config_from_db() -> Line2Config:
    """Read Line 2 configs from the database and build a Line2Config."""
    # Import here so the script is still runnable with --no-db (no DB env needed)
    from database import SessionLocal
    from models import Config

    with SessionLocal() as db:

        def _get(name: str) -> dict:
            obj = db.query(Config).filter(Config.name == name).first()
            if obj is None:
                print(
                    f"[error] Config '{name}' not found in database. Run seed.py first.",
                    file=sys.stderr,
                )
                sys.exit(1)
            return obj.data

        source2 = _get("source2")
        pdm1 = _get("pdm1_proc")
        pdm2 = _get("pdm2_proc")
        final = _get("final_proc")

        def _sensor_ranges(sensors: dict) -> dict[str, tuple[float, float]]:
            return {k: (float(v["min"]), float(v["max"])) for k, v in sensors.items()}

        config = Line2Config(
            iat_mean=float(source2["inter_arrival_time_mean"]),
            pdm1_cycle_time=float(pdm1["cycle_time"]),
            pdm2_cycle_time=float(pdm2["cycle_time"]),
            final_cycle_time=float(final["cycle_time"]),
            pdm1_sensors=_sensor_ranges(pdm1["sensors"]),
            pdm2_sensors=_sensor_ranges(pdm2["sensors"]),
        )

    print("[config] Loaded Line 2 config from database.")
    return config


# ──────────────────────────────────────────────────────────────────────────────
#  Pretty-print result
# ──────────────────────────────────────────────────────────────────────────────


def _bar(label: str, value: float, max_value: float, width: int = 30) -> str:
    filled = int(round(value / max_value * width)) if max_value > 0 else 0
    bar = "█" * filled + "░" * (width - filled)
    return f"  {label:<22} [{bar}]  {value:.4g}"


def print_results(result: dict, config: Line2Config) -> None:
    W = 62
    sink2 = result["sink2"]
    rs = result["final_resource_state"]

    print(f"\n{'═' * W}")
    print(f"  Line 2 Simulation Results")
    print(f"{'═' * W}")
    print(
        f"  Sim time       : {result['sim_time']:.0f} s  ({result['sim_time']/3600:.3f} h)"
    )
    print(f"  Random seed    : {result['random_seed']}")
    print(f"  Config source  : {result['config_source']}")
    print(f"{'─' * W}")
    print(f"  IAT mean       : {config.iat_mean} s")
    print(f"  PdM1 cycle     : {config.pdm1_cycle_time} s")
    print(f"  PdM2 cycle     : {config.pdm2_cycle_time} s")
    print(f"  Final cycle    : {config.final_cycle_time} s")
    print(f"{'─' * W}")
    print(f"  Sink2 arrivals : {sink2['arrivals']}")

    if sink2["arrivals"] == 0:
        print("  (no entities arrived — check sim_time / IAT settings)")
        return

    print(f"  Throughput     : {sink2.get('throughput_per_hour', 'n/a')} entities/h")
    print(f"{'─' * W}")
    print("  Cycle time")
    ct_max = sink2.get("cycle_time_max", 1.0)
    for key, label in [
        ("cycle_time_avg", "avg"),
        ("cycle_time_min", "min"),
        ("cycle_time_max", "max"),
        ("cycle_time_stdev", "stdev"),
    ]:
        if key in sink2:
            print(_bar(label, sink2[key], ct_max))
    print(f"{'─' * W}")
    print("  Power usage (model units)")
    pw_max = sink2.get("power_max", 1.0)
    for key, label in [
        ("power_avg", "avg"),
        ("power_min", "min"),
        ("power_max", "max"),
    ]:
        if key in sink2:
            print(_bar(label, sink2[key], pw_max))
    print(f"{'─' * W}")
    print("  Final resource state")
    for name, state in rs.items():
        print(f"    {name:<14}  busy={state['busy']}  queue={state['queue']}")
    print(f"{'═' * W}")


# ──────────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the Line 2 SimPy PdM simulation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--sim-time",
        type=float,
        default=sim_model.DEFAULT_SIM_TIME,
        help="Simulation duration in seconds.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=sim_model.DEFAULT_RANDOM_SEED,
        help="Random seed for reproducibility.",
    )
    p.add_argument(
        "--no-db",
        action="store_true",
        help="Skip database load; use built-in defaults.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print resource utilisation every 5 000 s during the run.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all progress messages; print only the final results table.",
    )
    p.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to save the JSON result (e.g. results.json).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # ── Load config ──────────────────────────────────────────────────────────
    log = (lambda *a, **kw: None) if args.quiet else print

    if args.no_db:
        config = Line2Config()
        log("[config] Using built-in defaults (--no-db).")
    else:
        if "DATABASE_URL" not in os.environ:
            print(
                "[error] DATABASE_URL environment variable is not set.\n"
                "        Set it or pass --no-db to use built-in defaults.",
                file=sys.stderr,
            )
            sys.exit(1)
        config = load_config_from_db()

    # ── Run ──────────────────────────────────────────────────────────────────
    log(
        f"[run] Starting simulation  (sim_time={args.sim_time:.0f} s, seed={args.seed}) …"
    )
    started = datetime.now()

    result = sim_model.run(
        sim_time=args.sim_time,
        random_seed=args.seed,
        verbose=args.verbose and not args.quiet,
        config=config,
    )

    elapsed = (datetime.now() - started).total_seconds()
    log(f"[run] Finished in {elapsed:.2f} s (wall clock).")

    # ── Print ─────────────────────────────────────────────────────────────────
    print_results(result, config)

    # ── Save ──────────────────────────────────────────────────────────────────
    if args.output:
        out = Path(args.output)
        out.write_text(json.dumps(result, indent=2))
        log(f"\n[output] Results saved to {out.resolve()}")


if __name__ == "__main__":
    main()
