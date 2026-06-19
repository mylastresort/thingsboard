import sys
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from optimize_line2 import run_opt

from fastapi import HTTPException

import sim_model

from database import Base, engine, get_db, SessionLocal
from models import Config, SimpyConfig
from schemas import (
    ConfigCreate,
    ConfigUpdate,
    ConfigResponse,
    ConfigSerializedResponse,
    ConfigImportRequest,
)
from seed import run_seed

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Config API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    run_seed()



# ---------------------------------------------------------------------------
# Simulation schemas
# ---------------------------------------------------------------------------


class SimRunRequest(BaseModel):
    sim_time: float = Field(
        default=sim_model.DEFAULT_SIM_TIME,
        gt=0,
        description="Simulation duration in seconds",
    )
    random_seed: int = Field(
        default=sim_model.DEFAULT_RANDOM_SEED,
        description="RNG seed for reproducibility",
    )


class ResourceState(BaseModel):
    busy: int
    queue: int


class SinkResult(BaseModel):
    name: str
    arrivals: int
    throughput_per_hour: float | None = None
    cycle_time_avg: float | None = None
    cycle_time_min: float | None = None
    cycle_time_max: float | None = None
    cycle_time_stdev: float | None = None
    power_avg: float | None = None
    power_min: float | None = None
    power_max: float | None = None


class SimRunResponse(BaseModel):
    sim_time: float
    random_seed: int
    config_source: str
    sink1: SinkResult
    sink2: SinkResult
    final_resource_state: dict[str, ResourceState]


class OptimizeRequest(BaseModel):
    n_trials: int = Field(
        default=50,
        gt=0,
        description="Number of Optuna trials to run for optimization",
    )
    sampler: str = Field(
        default="tpe",
        description="Optuna sampler to use (e.g. 'tpe', 'random', 'grid')",
    )
    show_progress: bool = Field(
        default=True,
        description="Whether to show Optuna's progress bar during optimization",
    )


# class OptimizeResponse(BaseModel):
#     best_params: dict[str, Any]
#     best_value: float
#     best_trial_number: int


class OptimizeResponse(BaseModel):
    best_params: dict[str, Any]
    best_value: float
    best_trial_number: int
    power_min: float
    power_max: float
    trials: list[tuple[int, float, Any]] = Field(
        default_factory=list,
        description="List of all trials with their parameters and values",
    )


# ---------------------------------------------------------------------------
# DB → Line2Config loader
# ---------------------------------------------------------------------------


def _build_line2_config(db: Session) -> sim_model.Line2Config:
    """
    Read the four Line 2 object configs from the database and deserialise
    them into a Line2Config that sim_model.run() consumes.
    """

    def _get(name: str) -> dict:
        obj = db.query(Config).filter(Config.name == name).first()
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Sim config '{name}' not found. Run seed first.",
            )
        return obj.data

    source2 = _get("source2")
    pdm1 = _get("pdm1_proc")
    pdm2 = _get("pdm2_proc")
    final = _get("final_proc")

    def _sensor_ranges(sensors: dict) -> dict[str, tuple[float, float]]:
        return {k: (float(v["min"]), float(v["max"])) for k, v in sensors.items()}

    return sim_model.Line2Config(
        iat_mean=float(source2["inter_arrival_time_mean"]),
        pdm1_cycle_time=float(pdm1["cycle_time"]),
        pdm2_cycle_time=float(pdm2["cycle_time"]),
        final_cycle_time=float(final["cycle_time"]),
        pdm1_sensors=_sensor_ranges(pdm1["sensors"]),
        pdm2_sensors=_sensor_ranges(pdm2["sensors"]),
    )


# ---------------------------------------------------------------------------
# Simulation endpoint
# ---------------------------------------------------------------------------


@app.post("/sim/run", response_model=SimRunResponse)
async def run_simulation(payload: SimRunRequest = None, db: Session = Depends(get_db)):
    """Load Line 2 config from DB, then run the SimPy PdM model."""
    if payload is None:
        payload = SimRunRequest()
    config = _build_line2_config(db)
    result = await run_in_threadpool(
        sim_model.run,
        sim_time=payload.sim_time,
        random_seed=payload.random_seed,
        verbose=False,
        config=config,
    )
    return result


import argparse
from requests import Response
from pathlib import Path


@app.post("/da")
async def da_endpoint():
    return {
        "message": "This is a placeholder for the DA endpoint. Implement DA logic here."
    }


# @app.post("/optimize", response_model=OptimizeResponse)
# async def optimize(payload: OptimizeRequest = OptimizeRequest(), db: Session = Depends(get_db)):
#     """Load Line 2 config from DB, then run Optuna optimization."""

#     # load vars
#     # build args

#     cfg_path_default = "optuna_config.yaml"
# # ───────────────────────────────────────────────────────────
#     cfg_path = Path(cfg_path_default)
#     if not cfg_path.exists():
#         print(f"[error] Config file not found: {cfg_path}", file=sys.stderr)
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=f"Config file not found: {cfg_path}"
#         )

#     result = await run_opt(
#         cfg_path=cfg_path,
#         base_config=_build_line2_config(db),
#         quiet=not payload.show_progress,
#         trials=payload.n_trials,
#         study_db="sqlite:///optuna_study.db",
#         study_name="line2_optimization",
#         host="thingsboard"
#     )

#     # TODO: adjust vars based on pivot values from sim runs

#     response = OptimizeResponse(
#         best_params=result[0].best_params,
#         best_value=result[0].best_value,
#         best_trial_number=result[0].best_trial.number,
#     )

#     return response


@app.post("/optimize", response_model=OptimizeResponse)
async def optimize(
    payload: OptimizeRequest = OptimizeRequest(), db: Session = Depends(get_db)
):
    cfg_path = Path("optuna_config.yaml")
    if not cfg_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Config file not found: {cfg_path}",
        )

    result = await run_opt(
        cfg_path=cfg_path,
        base_config=_build_line2_config(db),
        quiet=not payload.show_progress,
        trials=payload.n_trials,
        study_db="sqlite:///optuna_study.db",
        study_name="line2_optimization",
        host="thingsboard",
    )

    study = result[0]
    trial_values = [t.value for t in study.trials if t.value is not None]

    return OptimizeResponse(
        best_params=study.best_params,
        best_value=study.best_value,
        best_trial_number=study.best_trial.number,
        power_min=min(trial_values, default=0.0),
        power_max=max(trial_values, default=0.0),
        trials=[
            (
                t.number,
                t.values[0],
                t.params,
            )
            for t in study.trials
        ],
    )

class OptimizeConfigParamsResponse(BaseModel):
    # return a list of avaiable input parameters for the simulation
    parameters: dict[str, dict[str, Any]]  # param name → {type, min, max, etc.}

# @app.get("/optimize/config/params", response_model=OptimizeConfigParamsResponse)
# async def get_optimize_config_params():
#     # TODO: Implement logic to return available input parameters for the simulation
#     return OptimizeConfigParamsResponse(parameters={})


class OptimizeConfigsList(BaseModel):
    configs: list[str]  # list of available config names in the DB

class OptimizeConfigLoadResponse(BaseModel):
    config_name: str
    config_data: dict[str, Any]


@app.get("/optimize/configs", response_model=OptimizeConfigsList)
async def list_optimize_configs(db: Session = Depends(get_db)):
    # Return a list of available config names in the DB
    configs = db.query(SimpyConfig).all()
    config_names = [config.name for config in configs]
    return OptimizeConfigsList(configs=config_names)

@app.get("/optimize/configs/{config_name}", response_model=OptimizeConfigLoadResponse)
async def load_optimize_config(config_name: str, db: Session = Depends(get_db)):
    # Load the specified config from the DB and return its data
    config = db.query(SimpyConfig).filter(SimpyConfig.name == config_name).first()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simpy Config '{config_name}' not found",
        )
    return OptimizeConfigLoadResponse(config_name=config.name, config_data=config.data)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_or_404(db: Session, config_id: str) -> Config:
    obj = db.get(Config, config_id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Config not found"
        )
    return obj


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/configs", response_model=ConfigResponse, status_code=status.HTTP_201_CREATED
)
def create_config(payload: ConfigCreate, db: Session = Depends(get_db)):
    if db.query(Config).filter(Config.name == payload.name).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A config with this name already exists",
        )
    obj = Config(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        data=payload.data,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/configs", response_model=list[ConfigResponse])
def list_configs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Config).offset(skip).limit(limit).all()


@app.get("/configs/{config_id}", response_model=ConfigResponse)
def get_config(config_id: str, db: Session = Depends(get_db)):
    return _get_or_404(db, config_id)


@app.put("/configs/{config_id}", response_model=ConfigResponse)
def update_config(config_id: str, payload: ConfigUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, config_id)
    if payload.name is not None:
        existing = (
            db.query(Config)
            .filter(Config.name == payload.name, Config.id != config_id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A config with this name already exists",
            )
        obj.name = payload.name
    if payload.description is not None:
        obj.description = payload.description
    if payload.data is not None:
        obj.data = payload.data
    obj.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(obj)
    return obj


@app.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(config_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, config_id)
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Serialization / deserialization endpoints
# ---------------------------------------------------------------------------


@app.get("/configs/{config_id}/export", response_model=ConfigSerializedResponse)
def export_config(config_id: str, db: Session = Depends(get_db)):
    """Return config with `data` serialized as a JSON string for transport/storage."""
    obj = _get_or_404(db, config_id)
    return ConfigSerializedResponse.from_config(ConfigResponse.model_validate(obj))


@app.post(
    "/configs/import",
    response_model=ConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_config(payload: ConfigImportRequest, db: Session = Depends(get_db)):
    """Create a config from a serialized JSON string (deserializes on save)."""
    if db.query(Config).filter(Config.name == payload.name).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A config with this name already exists",
        )
    obj = Config(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        data=payload.deserialize(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
