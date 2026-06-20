"""Seed the database with sim-object configs mirroring the SimPy model.

Objects match exactly the nodes in TestSendReceive_-_Copy_-_Final.fsm:
  - Line 2 (active):  source2, pdm1_proc, pdm2_proc, final_proc, sink2
  - Line 1 (preserved, not simulated): source1, queue1–5,
      processor1–6, straight_conveyor1–4, curved_conveyor1–2, sink1

Run standalone:   python seed.py
Called on boot:   imported and invoked from main.py startup.
"""

import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models import Config, SimpyConfig

# ---------------------------------------------------------------------------
# Legacy generic names — removed from seed; cleaned up from DB on startup
# ---------------------------------------------------------------------------

_LEGACY_NAMES: frozenset[str] = frozenset(
    {
        "source_default",
        "queue_fifo",
        "queue_lifo",
        "processor_single",
        "processor_multi",
        "conveyor_belt",
        "sink_default",
        "operator_default",
        "dispatcher_priority",
    }
)

# ---------------------------------------------------------------------------
# Sim-object configs  (one entry per FlexSim object in the FSM)
# ---------------------------------------------------------------------------

SIM_OBJECTS: list[dict] = [
    # ── Line 2  [ACTIVE] ──────────────────────────────────────────────────────
    {
        "name": "source2",
        "description": "Source2 — generates PdM test entities (exponential IAT, mean 10 s). Line 2 active.",
        "data": {
            "type": "Source",
            "line": 2,
            "active": True,
            "flexsim_name": "Source2",
            "inter_arrival_time_distribution": "exponential",
            "inter_arrival_time_mean": 10.0,
            "entity_class": "Product",
            "output": "pdm1_proc",
            "stats": {"total_created": 0},
        },
    },
    {
        "name": "pdm1_proc",
        "description": "PdM1_Proc — machine 1 IoT/telemetry processor (cycle 1 s). Reads: pressure, vibration, volt, rotation. Line 2 active.",
        "data": {
            "type": "Processor",
            "line": 2,
            "active": True,
            "flexsim_name": "PdM1_Proc",
            "cycle_time": 1.0,
            "cycle_time_distribution": "deterministic",
            "machine": "PdM1",
            "sensors": {
                "pressure": {
                    "distribution": "uniform",
                    "min": 10.0,
                    "max": 100.0,
                    "unit": "bar",
                },
                "vibration": {
                    "distribution": "uniform",
                    "min": 0.1,
                    "max": 10.0,
                    "unit": "mm/s",
                },
                "volt": {
                    "distribution": "uniform",
                    "min": 200.0,
                    "max": 240.0,
                    "unit": "V",
                },
                "rotation": {
                    "distribution": "uniform",
                    "min": 100.0,
                    "max": 3000.0,
                    "unit": "RPM",
                },
            },
            "power_model": {
                "formula": "volt*rotation*0.05 + pressure*1.5 + vibration**2*0.08",
                "output_unit": "model_units",
            },
            "input": "source2",
            "output": "pdm2_proc",
            "stats": {"utilization": 0.0, "total_processed": 0},
        },
    },
    {
        "name": "pdm2_proc",
        "description": "PdM2_Proc — machine 2 IoT/telemetry processor (cycle 1 s). Reads: pressure, vibration, volt, rotation. Line 2 active.",
        "data": {
            "type": "Processor",
            "line": 2,
            "active": True,
            "flexsim_name": "PdM2_Proc",
            "cycle_time": 1.0,
            "cycle_time_distribution": "deterministic",
            "machine": "PdM2",
            "sensors": {
                "pressure": {
                    "distribution": "uniform",
                    "min": 10.0,
                    "max": 100.0,
                    "unit": "bar",
                },
                "vibration": {
                    "distribution": "uniform",
                    "min": 0.1,
                    "max": 10.0,
                    "unit": "mm/s",
                },
                "volt": {
                    "distribution": "uniform",
                    "min": 200.0,
                    "max": 240.0,
                    "unit": "V",
                },
                "rotation": {
                    "distribution": "uniform",
                    "min": 100.0,
                    "max": 3000.0,
                    "unit": "RPM",
                },
            },
            "power_model": {
                "formula": "volt*rotation*0.05 + pressure*1.5 + vibration**2*0.08",
                "output_unit": "model_units",
            },
            "input": "pdm1_proc",
            "output": "final_proc",
            "stats": {"utilization": 0.0, "total_processed": 0},
        },
    },
    {
        "name": "final_proc",
        "description": "Final_Proc — final assembly/output processor (cycle 10 s). Line 2 active.",
        "data": {
            "type": "Processor",
            "line": 2,
            "active": True,
            "flexsim_name": "Final_Proc",
            "cycle_time": 10.0,
            "cycle_time_distribution": "deterministic",
            "input": "pdm2_proc",
            "output": "sink2",
            "stats": {"utilization": 0.0, "total_processed": 0},
        },
    },
    {
        "name": "sink2",
        "description": "Sink2 — absorbs PdM test entities and records flow statistics. Line 2 active.",
        "data": {
            "type": "Sink",
            "line": 2,
            "active": True,
            "flexsim_name": "Sink2",
            "collect_stats": True,
            "input": "final_proc",
            "stats": {"total_absorbed": 0, "avg_flow_time": 0.0},
        },
    },
    # ── Line 1  [PRESERVED, NOT SIMULATED] ───────────────────────────────────
    {
        "name": "source1",
        "description": "Source1 — main production line source (exp IAT 10 s). Line 1 — not simulated.",
        "data": {
            "type": "Source",
            "line": 1,
            "active": False,
            "flexsim_name": "Source1",
            "inter_arrival_time_distribution": "exponential",
            "inter_arrival_time_mean": 10.0,
            "entity_class": "Product",
            "output": "queue1",
            "stats": {"total_created": 0},
        },
    },
    {
        "name": "queue1",
        "description": "Queue1 — buffer before Processor1. Line 1.",
        "data": {
            "type": "Queue",
            "line": 1,
            "active": False,
            "flexsim_name": "Queue1",
            "capacity": -1,
            "discipline": "FIFO",
            "input": "source1",
            "output": "processor1",
            "stats": {"avg_length": 0.0, "max_length": 0},
        },
    },
    {
        "name": "processor1",
        "description": "Processor1 — cycle 5 s. Line 1.",
        "data": {
            "type": "Processor",
            "line": 1,
            "active": False,
            "flexsim_name": "Processor1",
            "cycle_time": 5.0,
            "cycle_time_distribution": "deterministic",
            "input": "queue1",
            "output": "queue2",
            "stats": {"utilization": 0.0, "total_processed": 0},
        },
    },
    {
        "name": "queue2",
        "description": "Queue2 — buffer before Processor2. Line 1.",
        "data": {
            "type": "Queue",
            "line": 1,
            "active": False,
            "flexsim_name": "Queue2",
            "capacity": -1,
            "discipline": "FIFO",
            "input": "processor1",
            "output": "processor2",
            "stats": {"avg_length": 0.0, "max_length": 0},
        },
    },
    {
        "name": "processor2",
        "description": "Processor2 — cycle 15 s. Line 1.",
        "data": {
            "type": "Processor",
            "line": 1,
            "active": False,
            "flexsim_name": "Processor2",
            "cycle_time": 15.0,
            "cycle_time_distribution": "deterministic",
            "input": "queue2",
            "output": "queue3",
            "stats": {"utilization": 0.0, "total_processed": 0},
        },
    },
    {
        "name": "queue3",
        "description": "Queue3 — buffer before Processor3. Line 1.",
        "data": {
            "type": "Queue",
            "line": 1,
            "active": False,
            "flexsim_name": "Queue3",
            "capacity": -1,
            "discipline": "FIFO",
            "input": "processor2",
            "output": "processor3",
            "stats": {"avg_length": 0.0, "max_length": 0},
        },
    },
    {
        "name": "processor3",
        "description": "Processor3 — cycle 30 s. Line 1.",
        "data": {
            "type": "Processor",
            "line": 1,
            "active": False,
            "flexsim_name": "Processor3",
            "cycle_time": 30.0,
            "cycle_time_distribution": "deterministic",
            "input": "queue3",
            "output": "queue4",
            "stats": {"utilization": 0.0, "total_processed": 0},
        },
    },
    {
        "name": "queue4",
        "description": "Queue4 — buffer before Processor4. Line 1.",
        "data": {
            "type": "Queue",
            "line": 1,
            "active": False,
            "flexsim_name": "Queue4",
            "capacity": -1,
            "discipline": "FIFO",
            "input": "processor3",
            "output": "processor4",
            "stats": {"avg_length": 0.0, "max_length": 0},
        },
    },
    {
        "name": "processor4",
        "description": "Processor4 — cycle 30 s. Line 1.",
        "data": {
            "type": "Processor",
            "line": 1,
            "active": False,
            "flexsim_name": "Processor4",
            "cycle_time": 30.0,
            "cycle_time_distribution": "deterministic",
            "input": "queue4",
            "output": "queue5",
            "stats": {"utilization": 0.0, "total_processed": 0},
        },
    },
    {
        "name": "queue5",
        "description": "Queue5 — buffer before Processor5. Line 1.",
        "data": {
            "type": "Queue",
            "line": 1,
            "active": False,
            "flexsim_name": "Queue5",
            "capacity": -1,
            "discipline": "FIFO",
            "input": "processor4",
            "output": "processor5",
            "stats": {"avg_length": 0.0, "max_length": 0},
        },
    },
    {
        "name": "processor5",
        "description": "Processor5 — cycle 20 s. Line 1.",
        "data": {
            "type": "Processor",
            "line": 1,
            "active": False,
            "flexsim_name": "Processor5",
            "cycle_time": 20.0,
            "cycle_time_distribution": "deterministic",
            "input": "queue5",
            "output": "straight_conveyor1",
            "stats": {"utilization": 0.0, "total_processed": 0},
        },
    },
    {
        "name": "straight_conveyor1",
        "description": "StraightConveyor1 — travel time ~5 s. Line 1.",
        "data": {
            "type": "Conveyor",
            "subtype": "Straight",
            "line": 1,
            "active": False,
            "flexsim_name": "StraightConveyor1",
            "travel_time": 5.0,
            "accumulating": True,
            "input": "processor5",
            "output": "curved_conveyor1",
            "stats": {"total_transported": 0},
        },
    },
    {
        "name": "curved_conveyor1",
        "description": "CurvedConveyor1 — travel time ~3 s. Line 1.",
        "data": {
            "type": "Conveyor",
            "subtype": "Curved",
            "line": 1,
            "active": False,
            "flexsim_name": "CurvedConveyor1",
            "travel_time": 3.0,
            "accumulating": True,
            "input": "straight_conveyor1",
            "output": "straight_conveyor2",
            "stats": {"total_transported": 0},
        },
    },
    {
        "name": "straight_conveyor2",
        "description": "StraightConveyor2 — travel time ~5 s. Line 1.",
        "data": {
            "type": "Conveyor",
            "subtype": "Straight",
            "line": 1,
            "active": False,
            "flexsim_name": "StraightConveyor2",
            "travel_time": 5.0,
            "accumulating": True,
            "input": "curved_conveyor1",
            "output": "processor6",
            "stats": {"total_transported": 0},
        },
    },
    {
        "name": "processor6",
        "description": "Processor6 — cycle 20 s. Line 1.",
        "data": {
            "type": "Processor",
            "line": 1,
            "active": False,
            "flexsim_name": "Processor6",
            "cycle_time": 20.0,
            "cycle_time_distribution": "deterministic",
            "input": "straight_conveyor2",
            "output": "straight_conveyor3",
            "stats": {"utilization": 0.0, "total_processed": 0},
        },
    },
    {
        "name": "straight_conveyor3",
        "description": "StraightConveyor3 — travel time ~5 s. Line 1.",
        "data": {
            "type": "Conveyor",
            "subtype": "Straight",
            "line": 1,
            "active": False,
            "flexsim_name": "StraightConveyor3",
            "travel_time": 5.0,
            "accumulating": True,
            "input": "processor6",
            "output": "curved_conveyor2",
            "stats": {"total_transported": 0},
        },
    },
    {
        "name": "curved_conveyor2",
        "description": "CurvedConveyor2 — travel time ~3 s. Line 1.",
        "data": {
            "type": "Conveyor",
            "subtype": "Curved",
            "line": 1,
            "active": False,
            "flexsim_name": "CurvedConveyor2",
            "travel_time": 3.0,
            "accumulating": True,
            "input": "straight_conveyor3",
            "output": "straight_conveyor4",
            "stats": {"total_transported": 0},
        },
    },
    {
        "name": "straight_conveyor4",
        "description": "StraightConveyor4 — travel time ~5 s. Line 1.",
        "data": {
            "type": "Conveyor",
            "subtype": "Straight",
            "line": 1,
            "active": False,
            "flexsim_name": "StraightConveyor4",
            "travel_time": 5.0,
            "accumulating": True,
            "input": "curved_conveyor2",
            "output": "sink1",
            "stats": {"total_transported": 0},
        },
    },
    {
        "name": "sink1",
        "description": "Sink1 — absorbs main production entities. Line 1 — not simulated.",
        "data": {
            "type": "Sink",
            "line": 1,
            "active": False,
            "flexsim_name": "Sink1",
            "collect_stats": True,
            "input": "straight_conveyor4",
            "stats": {"total_absorbed": 0, "avg_flow_time": 0.0},
        },
    },
]

# ---------------------------------------------------------------------------
# Seed function
# ---------------------------------------------------------------------------


def seed(db: Session) -> None:
    """
    Idempotent seed:
      1. Delete any legacy generic configs no longer in the model.
      2. Insert model configs that do not yet exist (skip existing by name).
    """
    # Step 1 — cleanup stale generic entries
    deleted = (
        db.query(Config)
        .filter(Config.name.in_(_LEGACY_NAMES))
        .delete(synchronize_session=False)
    )
    if deleted:
        print(f"[seed] removed {deleted} legacy config(s).")
 
    # Step 2 — insert missing model objects
    inserted = 0
    for entry in SIM_OBJECTS:
        if db.query(Config).filter(Config.name == entry["name"]).first():
            continue
        obj = Config(
            id=str(uuid.uuid4()),
            name=entry["name"],
            description=entry.get("description"),
            data=entry["data"],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(obj)
        inserted += 1
 
    db.commit()
    total = len(SIM_OBJECTS)
    print(
        f"[seed] inserted {inserted} config(s) ({total - inserted} already existed). Total model objects: {total}."
    )
 
 
def simpy_seed(db: Session) -> None:
    """
    Idempotent seed for SimPy config:
      1. Check if default_simpy_config already exists.
      2. Insert if missing, skip if already present.
    """
    cfg_name = "default_simpy_config"
 
    # Check if config already exists
    if db.query(SimpyConfig).filter(SimpyConfig.name == cfg_name).first():
        print(f"[simpy_seed] {cfg_name} already exists, skipping.")
        return
 
    # Load and insert config
    cfg_path = "optuna_config.yaml"
    with open(cfg_path, "r") as f:
        import yaml
 
        simpy_cfg_data = yaml.safe_load(f)
        obj = SimpyConfig(
            id=str(uuid.uuid4()),
            name=cfg_name,
            description="Default SimPy configuration loaded from YAML.",
            data=simpy_cfg_data,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(obj)
        db.commit()
        print(f"[simpy_seed] inserted SimPy config from {cfg_path}.")

# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------

def run_seed():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
        simpy_seed(db)

if __name__ == "__main__":
    run_seed()
