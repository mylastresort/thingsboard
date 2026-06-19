"""
SimPy conversion of: TestSendReceive_-_Copy_-_Final.fsm
FlexSim 26.0 | UM6P — IoT PdM test model

══════════════════════════════════════════════════════════════════════
  Extracted from binary FSM  (gzip-compressed flexsimtree v26.0)
══════════════════════════════════════════════════════════════════════

  Model objects recovered:
    Sources     : Source1, Source2
    Processors  : Processor1–6  (cycle times: 5, 15, 30, 30, 20, 20 s)
                  PdM1_Proc, PdM2_Proc (cycle time: 1 s each)
                  Final_Proc          (cycle time: 10 s)
    Queues      : Queue1–5  (unlimited capacity)
    Conveyors   : StraightConveyor1–4, CurvedConveyor1–2
    Sinks       : Sink1, Sink2
    Operators   : Operator1, Operator2  (not modelled — not needed for flow)
    Parameters  : PdM1/PdM2 sensor bounds (pressure, vibration, volt, rotation)

  Inferred topology
  ─────────────────
  Line 1  (Source1 → Sink1)  ─── main production line  [PRESERVED, NOT SIMULATED]:
    Source1
      → Queue1 → Processor1 (5 s)
      → Queue2 → Processor2 (15 s)
      → Queue3 → Processor3 (30 s)
      → Queue4 → Processor4 (30 s)
      → Queue5 → Processor5 (20 s)
      → StraightConveyor1 → CurvedConveyor1 → StraightConveyor2
      → Processor6 (20 s)
      → StraightConveyor3 → CurvedConveyor2 → StraightConveyor4
      → Sink1

  Line 2  (Source2 → Sink2)  ─── PdM / IoT Send-Receive test  [ACTIVE]:
    Source2
      → PdM1_Proc (1 s, reads sensors: pressure, vibration, volt, rotation)
      → PdM2_Proc (1 s, reads sensors: same set for machine 2)
      → Final_Proc (10 s)
      → Sink2

  Distributions
  ─────────────
    Source IAT : exponential(mean = 10 s)   [both sources; FlexSim tag par2 = 10]
    Cycle times: deterministic              [extracted from cycletime double nodes]
    Sensor vals: uniform(min, max)          [sampled from PdM OptQuest ranges]

  Power usage model  (FlexScript in Processor7 OnProcessFinish → Python)
  ────────────────────────────────────────────────────────────────────────
    mechanicalPower = volt * rotation * 0.05
    loadPower       = pressure * 1.5
    vibrationLoss   = vibration² * 0.08
    PowerUsage      = mechanicalPower + loadPower + vibrationLoss

  Simulation time: 28 000 s  (08:00 AM → 15:46:40  on 23/03/2026)
"""

from __future__ import annotations

import dataclasses
import random
import statistics
import sys
from typing import Any

import simpy

# ──────────────────────────────────────────────────────────────────────────────
#  Model parameters
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_SIM_TIME: float = 28_000.0
DEFAULT_RANDOM_SEED: int = 42
IAT_MEAN: float = 10.0

CYCLE_TIMES: dict[str, float] = {
    "Processor1": 5.0,
    "Processor2": 15.0,
    "Processor3": 30.0,
    "Processor4": 30.0,
    "Processor5": 20.0,
    "Processor6": 20.0,
    "PdM1": 1.0,
    "PdM2": 1.0,
    "Final": 10.0,
}

CONVEYOR_TIMES: dict[str, float] = {
    "Straight1": 5.0,
    "Straight2": 5.0,
    "Straight3": 5.0,
    "Straight4": 5.0,
    "Curved1": 3.0,
    "Curved2": 3.0,
}

PdM_RANGES: dict[str, dict[str, tuple]] = {
    "PdM1": {
        "pressure": (10.0, 100.0),
        "vibration": (0.1, 10.0),
        "volt": (200.0, 240.0),
        "rotation": (100.0, 3000.0),
    },
    "PdM2": {
        "pressure": (10.0, 100.0),
        "vibration": (0.1, 10.0),
        "volt": (200.0, 240.0),
        "rotation": (100.0, 3000.0),
    },
}


# ──────────────────────────────────────────────────────────────────────────────
#  Line 2 runtime config  (loaded from DB; falls back to module-level constants)
# ──────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Line2Config:
    """
    All parameters needed to run Line 2, deserialised from the DB configs:
      source2, pdm1_proc, pdm2_proc, final_proc.

    Defaults mirror the module-level constants so the model runs standalone
    without a database connection.
    """

    iat_mean: float = IAT_MEAN
    pdm1_cycle_time: float = 1.0
    pdm2_cycle_time: float = 1.0
    final_cycle_time: float = 10.0
    pdm1_sensors: dict[str, tuple[float, float]] = dataclasses.field(
        default_factory=lambda: {k: (v[0], v[1]) for k, v in PdM_RANGES["PdM1"].items()}
    )
    pdm2_sensors: dict[str, tuple[float, float]] = dataclasses.field(
        default_factory=lambda: {k: (v[0], v[1]) for k, v in PdM_RANGES["PdM2"].items()}
    )


# ──────────────────────────────────────────────────────────────────────────────
#  Entity  (= FlowItem in FlexSim)
# ──────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Entity:
    eid: int
    source: str
    created_at: float
    labels: dict[str, float] = dataclasses.field(default_factory=dict)
    power_log: list[float] = dataclasses.field(default_factory=list)

    @property
    def total_power(self) -> float:
        return sum(self.power_log)


# ──────────────────────────────────────────────────────────────────────────────
#  Statistics collector
# ──────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class SinkStats:
    name: str
    arrivals: int = 0
    cycle_times: list[float] = dataclasses.field(default_factory=list)
    power_vals: list[float] = dataclasses.field(default_factory=list)

    def record(self, entity: Entity, now: float) -> None:
        self.arrivals += 1
        self.cycle_times.append(now - entity.created_at)
        if entity.power_log:
            self.power_vals.append(entity.total_power)

    def to_dict(self, sim_time: float) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "arrivals": self.arrivals}
        if self.arrivals == 0:
            return d
        d["throughput_per_hour"] = round(self.arrivals / sim_time * 3600, 4)
        if self.cycle_times:
            d["cycle_time_avg"] = round(statistics.mean(self.cycle_times), 4)
            d["cycle_time_min"] = round(min(self.cycle_times), 4)
            d["cycle_time_max"] = round(max(self.cycle_times), 4)
            if len(self.cycle_times) > 1:
                d["cycle_time_stdev"] = round(statistics.stdev(self.cycle_times), 4)
        if self.power_vals:
            d["power_avg"] = round(statistics.mean(self.power_vals), 4)
            d["power_min"] = round(min(self.power_vals), 4)
            d["power_max"] = round(max(self.power_vals), 4)
        return d


# ──────────────────────────────────────────────────────────────────────────────
#  Power usage formula  (FlexScript Processor7 OnProcessFinish)
# ──────────────────────────────────────────────────────────────────────────────


def compute_power(
    vibration: float, volt: float, pressure: float, rotation: float
) -> float:
    mechanical = volt * rotation * 0.05
    load = pressure * 1.5
    vibr_loss = vibration * vibration * 0.08
    return mechanical + load + vibr_loss


# ──────────────────────────────────────────────────────────────────────────────
#  Low-level SimPy helpers
# ──────────────────────────────────────────────────────────────────────────────


def use_processor(env: simpy.Environment, resource: simpy.Resource, cycle_time: float):
    with resource.request() as req:
        yield req
        yield env.timeout(cycle_time)


def use_conveyor(env: simpy.Environment, travel_time: float):
    yield env.timeout(travel_time)


# ──────────────────────────────────────────────────────────────────────────────
#  PdM processor  (ThingsBoard IoT Send/Receive)
# ──────────────────────────────────────────────────────────────────────────────


def pdm_processor(
    env: simpy.Environment,
    resource: simpy.Resource,
    entity: Entity,
    machine: str,
    rng: random.Random,
    cycle_time: float,
    sensor_ranges: dict[str, tuple[float, float]],
):
    pressure = rng.uniform(*sensor_ranges["pressure"])
    vibration = rng.uniform(*sensor_ranges["vibration"])
    volt = rng.uniform(*sensor_ranges["volt"])
    rotation = rng.uniform(*sensor_ranges["rotation"])

    with resource.request() as req:
        yield req
        yield env.timeout(cycle_time)

    entity.labels.update(
        {
            f"{machine}_pressure": pressure,
            f"{machine}_vibration": vibration,
            f"{machine}_volt": volt,
            f"{machine}_rotation": rotation,
        }
    )
    entity.power_log.append(compute_power(vibration, volt, pressure, rotation))


# ──────────────────────────────────────────────────────────────────────────────
#  Line 1  —  main production line  [PRESERVED, NOT SIMULATED]
# ──────────────────────────────────────────────────────────────────────────────


def line1_flow(
    env: simpy.Environment,
    entity: Entity,
    res: dict[str, simpy.Resource],
    sink: SinkStats,
    rng: random.Random,
):
    yield env.process(use_processor(env, res["P1"], CYCLE_TIMES["Processor1"]))
    yield env.process(use_processor(env, res["P2"], CYCLE_TIMES["Processor2"]))
    yield env.process(use_processor(env, res["P3"], CYCLE_TIMES["Processor3"]))
    yield env.process(use_processor(env, res["P4"], CYCLE_TIMES["Processor4"]))
    yield env.process(use_processor(env, res["P5"], CYCLE_TIMES["Processor5"]))
    yield env.process(use_conveyor(env, CONVEYOR_TIMES["Straight1"]))
    yield env.process(use_conveyor(env, CONVEYOR_TIMES["Curved1"]))
    yield env.process(use_conveyor(env, CONVEYOR_TIMES["Straight2"]))
    yield env.process(use_processor(env, res["P6"], CYCLE_TIMES["Processor6"]))
    yield env.process(use_conveyor(env, CONVEYOR_TIMES["Straight3"]))
    yield env.process(use_conveyor(env, CONVEYOR_TIMES["Curved2"]))
    yield env.process(use_conveyor(env, CONVEYOR_TIMES["Straight4"]))
    sink.record(entity, env.now)


# ──────────────────────────────────────────────────────────────────────────────
#  Line 2  —  PdM / IoT Send-Receive  [ACTIVE]
# ──────────────────────────────────────────────────────────────────────────────


def line2_flow(
    env: simpy.Environment,
    entity: Entity,
    res: dict[str, simpy.Resource],
    sink: SinkStats,
    rng: random.Random,
    config: Line2Config,
):
    yield env.process(
        pdm_processor(
            env,
            res["PdM1"],
            entity,
            "PdM1",
            rng,
            config.pdm1_cycle_time,
            config.pdm1_sensors,
        )
    )
    yield env.process(
        pdm_processor(
            env,
            res["PdM2"],
            entity,
            "PdM2",
            rng,
            config.pdm2_cycle_time,
            config.pdm2_sensors,
        )
    )
    yield env.process(use_processor(env, res["Final"], config.final_cycle_time))
    sink.record(entity, env.now)


# ──────────────────────────────────────────────────────────────────────────────
#  Source generator
# ──────────────────────────────────────────────────────────────────────────────


def source_gen(
    env: simpy.Environment,
    src_name: str,
    flow_fn,
    res: dict[str, simpy.Resource],
    sink: SinkStats,
    rng: random.Random,
    iat_mean: float = IAT_MEAN,
):
    eid = 0
    while True:
        yield env.timeout(rng.expovariate(1.0 / iat_mean))
        eid += 1
        entity = Entity(eid=eid, source=src_name, created_at=env.now)
        env.process(flow_fn(env, entity, res, sink, rng))


# ──────────────────────────────────────────────────────────────────────────────
#  Optional telemetry logger  (mirrors ThingsBoard dashboard polling)
# ──────────────────────────────────────────────────────────────────────────────


def telemetry_logger(
    env: simpy.Environment, res: dict[str, simpy.Resource], interval: float = 500.0
):
    resource_names = {"PdM1": "PdM1_Proc", "PdM2": "PdM2_Proc", "Final": "Final_Proc"}
    while True:
        yield env.timeout(interval)
        busy = {resource_names[k]: res[k].count for k in resource_names}
        queue_len = {resource_names[k]: len(res[k].queue) for k in resource_names}
        print(f"  t={env.now:7.0f}s  |  busy: {busy}  |  queue_len: {queue_len}")


# ──────────────────────────────────────────────────────────────────────────────
#  Main entry-point
# ──────────────────────────────────────────────────────────────────────────────


def run(
    sim_time: float = DEFAULT_SIM_TIME,
    random_seed: int = DEFAULT_RANDOM_SEED,
    verbose: bool = False,
    config: Line2Config | None = None,
) -> dict[str, Any]:
    """
    Run the simulation and return a structured result dict.

    Only Line 2 (PdM / IoT Send-Receive) is active.
    Line 1 resources are instantiated but Source1 is not started.

    If `config` is provided its values (IAT, cycle times, sensor ranges)
    override the module-level constants — this is how the /sim/run endpoint
    injects parameters loaded from the database.
    """
    if config is None:
        config = Line2Config()

    rng = random.Random(random_seed)
    env = simpy.Environment()

    res: dict[str, simpy.Resource] = {
        # Line 1  (preserved, idle)
        "P1": simpy.Resource(env, capacity=1),
        "P2": simpy.Resource(env, capacity=1),
        "P3": simpy.Resource(env, capacity=1),
        "P4": simpy.Resource(env, capacity=1),
        "P5": simpy.Resource(env, capacity=1),
        "P6": simpy.Resource(env, capacity=1),
        # Line 2  (active)
        "PdM1": simpy.Resource(env, capacity=1),
        "PdM2": simpy.Resource(env, capacity=1),
        "Final": simpy.Resource(env, capacity=1),
    }

    sink1 = SinkStats("Sink1 (Line 1 — Main Production) [NOT SIMULATED]")
    sink2 = SinkStats("Sink2 (Line 2 — PdM / IoT Send-Receive)")

    # Closure binds DB-loaded config to line2_flow without changing source_gen's signature.
    def _line2(env, entity, res, sink, rng):
        yield env.process(line2_flow(env, entity, res, sink, rng, config))

    # Line 2  [ACTIVE]
    env.process(
        source_gen(env, "Source2", _line2, res, sink2, rng, iat_mean=config.iat_mean)
    )

    # Line 1  [DISABLED — uncomment to re-enable]
    # env.process(source_gen(env, "Source1", line1_flow, res, sink1, rng))

    if verbose:
        env.process(telemetry_logger(env, res, interval=5_000.0))

    env.run(until=sim_time)

    return {
        "sim_time": sim_time,
        "random_seed": random_seed,
        "config_source": "database" if config is not None else "defaults",
        "sink1": sink1.to_dict(sim_time),
        "sink2": sink2.to_dict(sim_time),
        "final_resource_state": {
            "PdM1_Proc": {"busy": res["PdM1"].count, "queue": len(res["PdM1"].queue)},
            "PdM2_Proc": {"busy": res["PdM2"].count, "queue": len(res["PdM2"].queue)},
            "Final_Proc": {
                "busy": res["Final"].count,
                "queue": len(res["Final"].queue),
            },
        },
    }


if __name__ == "__main__":
    import json

    result = run(verbose="--quiet" not in sys.argv)
    print(json.dumps(result, indent=2))
