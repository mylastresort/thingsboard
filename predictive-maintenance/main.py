#
# Copyright © 2016-2024 The Thingsboard Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import traceback
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from library.core.data_registry import DataRegistry
from src.db_connector import setup_model_database
from src.logger import logger  # Global logger
from src.model.job import add_model_log, start_prediction_job
from src.model.model import router as model_router
from src.model.shared import get_data_registry
from src.notify import router as notify_router
from src.settings import settings

pd.set_option("display.max_columns", None)
# Load environment variables from .env file
load_dotenv()

# Ensure the models directory exists
os.makedirs(settings.models_path, exist_ok=True)

app = FastAPI(
    root_path=settings.app_root_path,
    # debug=settings.app_debug,
    debug=False,
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
)

origins = settings.cors_origins
# server shouldn't handle authentication in future, thingsboard should manage it

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(model_router)
app.include_router(notify_router)

# Log startup with current log level
logger.info("Predictive Maintenance Service Starting")


@app.on_event("startup")
async def startup_event():
    # Setup custom model database tables if they don't exist
    try:
        setup_model_database()
        logger.info("Custom model database tables verified/created successfully.")
    except Exception as e:
        logger.error(f"Failed to setup model database tables: {e}")

    # return
    """
    Startup event handler: Auto-start prediction jobs for trained models
    """
    # Check if auto-start is enabled via environment variable
    auto_start_enabled = os.getenv("AUTO_START_PREDICTION_JOBS", "false").lower() == "true"
    if not auto_start_enabled:
        print(
            "AUTO_START_PREDICTION_JOBS is disabled, skipping auto-start of prediction jobs",
            flush=True,
        )
        return
    print("=" * 80, flush=True)
    print("STARTUP: Auto-starting prediction jobs for trained models", flush=True)
    print("=" * 80, flush=True)
    logger.info("=" * 80)
    logger.info("STARTUP: Auto-starting prediction jobs for trained models")
    logger.info("=" * 80)

    try:
        # Get data registry to query database
        data_registry = get_data_registry()

        # Query for all predictive maintenance configurations
        with data_registry.engine.connect() as conn:
            query = text("""
                SELECT id, name, device_id, forecast_algorithm, anomaly_algorithm, additional_data
                FROM predictive_maintenance_config
                ORDER BY created_time DESC
                """)
            result = conn.execute(query)
            configs = result.fetchall()

        print(f"STARTUP: Found {len(configs)} predictive maintenance configurations", flush=True)
        logger.info(f"STARTUP: Found {len(configs)} predictive maintenance configurations")

        models_path = Path(settings.models_path)
        started_jobs = []
        skipped_jobs = []

        for config in configs:
            config_id = str(config[0])
            config_name = config[1]
            device_id = str(config[2])
            forecast_algorithm = config[3]
            anomaly_algorithm = config[4]
            additional_data = config[5] or {}

            print(f"STARTUP: Processing config {config_name} (ID: {config_id})", flush=True)
            logger.info(f"STARTUP: Processing config {config_name} (ID: {config_id})")

            # Check for trained forecast model
            forecast_model_id = f"{config_id}/forecast_model"
            forecast_model_dir = models_path / forecast_model_id
            # Check for either metadata.json or any model files (.pkl, .h5, .joblib)
            has_metadata = (forecast_model_dir / "metadata.json").exists()
            has_model_files = False
            if forecast_model_dir.exists():
                model_files = (
                    list(forecast_model_dir.glob("*.pkl"))
                    + list(forecast_model_dir.glob("*.h5"))
                    + list(forecast_model_dir.glob("*.joblib"))
                )
                has_model_files = len(model_files) > 0

            if forecast_model_dir.exists() and (has_metadata or has_model_files):
                print(f"STARTUP: Found trained forecast model at {forecast_model_dir}", flush=True)
                print(f"STARTUP:   - has metadata.json: {has_metadata}", flush=True)
                print(
                    f"STARTUP:   - has model files: {has_model_files} "
                    f"({len(model_files) if has_model_files else 0} files)",
                    flush=True,
                )
                logger.info(f"STARTUP: Found trained forecast model at {forecast_model_dir}")
                try:
                    success = start_prediction_job(
                        model_id=forecast_model_id, model_type="ForecastModel", device_id=device_id
                    )
                    if success:
                        started_jobs.append(f"{forecast_model_id} (ForecastModel)")
                        print(
                            f"STARTUP: ✓ Started prediction job for {forecast_model_id}", flush=True
                        )
                        logger.info(f"STARTUP: ✓ Started prediction job for {forecast_model_id}")
                        add_model_log(
                            forecast_model_id,
                            "info",
                            "Prediction job auto-started on service restart",
                        )
                    else:
                        skipped_jobs.append(f"{forecast_model_id} (already running)")
                        logger.warning(f"STARTUP: Job for {forecast_model_id} already running")
                except Exception as e:
                    logger.error(f"STARTUP: Failed to start job for {forecast_model_id}: {str(e)}")
                    skipped_jobs.append(f"{forecast_model_id} (error: {str(e)})")
            else:
                logger.info(f"STARTUP: No trained forecast model found for {config_id}")

            # Check for trained anomaly model
            anomaly_model_id = f"{config_id}/anomaly_model"
            anomaly_model_dir = models_path / anomaly_model_id
            if anomaly_model_dir.exists():
                # Check if any model files exist (hour_*.pkl)
                model_files = list(anomaly_model_dir.glob("hour_*.pkl"))
                if model_files:
                    logger.info(f"STARTUP: Found trained anomaly model at {anomaly_model_dir}")
                    try:
                        success = start_prediction_job(
                            model_id=anomaly_model_id,
                            model_type="AnomalyPredictor",
                            device_id=device_id,
                        )
                        if success:
                            started_jobs.append(f"{anomaly_model_id} (AnomalyPredictor)")
                            logger.info(f"STARTUP: ✓ Started prediction job for {anomaly_model_id}")
                            add_model_log(
                                anomaly_model_id,
                                "info",
                                "Prediction job auto-started on service restart",
                            )
                        else:
                            skipped_jobs.append(f"{anomaly_model_id} (already running)")
                            logger.warning(f"STARTUP: Job for {anomaly_model_id} already running")
                    except Exception as e:
                        logger.error(
                            f"STARTUP: Failed to start job for {anomaly_model_id}: {str(e)}"
                        )
                        skipped_jobs.append(f"{anomaly_model_id} (error: {str(e)})")
                else:
                    logger.info(f"STARTUP: No trained anomaly model files found for {config_id}")
            else:
                logger.info(f"STARTUP: No trained anomaly model found for {config_id}")

        # Also scan the models directory for ANY trained models not in config
        print("STARTUP: Scanning models directory for additional trained models...", flush=True)
        print(f"STARTUP: Models path: {models_path}", flush=True)
        if models_path.exists():
            for config_dir in models_path.iterdir():
                if not config_dir.is_dir():
                    continue

                config_id = config_dir.name
                print(f"STARTUP: Checking directory: {config_id}", flush=True)

                # Skip if already processed
                forecast_model_id = f"{config_id}/forecast_model"
                anomaly_model_id = f"{config_id}/anomaly_model"

                if any(
                    forecast_model_id in job or anomaly_model_id in job
                    for job in started_jobs + skipped_jobs
                ):
                    continue

                # Check for forecast model
                forecast_model_dir = config_dir / "forecast_model"
                if forecast_model_dir.exists() and (forecast_model_dir / "metadata.json").exists():
                    print(
                        f"STARTUP: Found orphaned forecast model at {forecast_model_dir}",
                        flush=True,
                    )
                    try:
                        # Try to find device_id from config, otherwise use None
                        device_id = None
                        success = start_prediction_job(
                            model_id=forecast_model_id,
                            model_type="ForecastModel",
                            device_id=device_id,
                        )
                        if success:
                            started_jobs.append(f"{forecast_model_id} (ForecastModel, orphaned)")
                            print(
                                (
                                    f"STARTUP: ✓ Started prediction job for orphaned model "
                                    f"{forecast_model_id}"
                                ),
                                flush=True,
                            )
                    except Exception as e:
                        print(
                            f"STARTUP: Failed to start orphaned model {forecast_model_id}: "
                            f"{str(e)}",
                            flush=True,
                        )
                        skipped_jobs.append(f"{forecast_model_id} (error: {str(e)})")

                # Check for anomaly model
                anomaly_model_dir = config_dir / "anomaly_model"
                if anomaly_model_dir.exists():
                    model_files = list(anomaly_model_dir.glob("hour_*.pkl"))
                    if model_files:
                        print(
                            f"STARTUP: Found orphaned anomaly model at {anomaly_model_dir}",
                            flush=True,
                        )
                        try:
                            device_id = None
                            success = start_prediction_job(
                                model_id=anomaly_model_id,
                                model_type="AnomalyPredictor",
                                device_id=device_id,
                            )
                            if success:
                                started_jobs.append(
                                    f"{anomaly_model_id} (AnomalyPredictor, orphaned)"
                                )
                                print(
                                    f"STARTUP: ✓ Started prediction job for "
                                    f"orphaned model {anomaly_model_id}",
                                    flush=True,
                                )
                        except Exception as e:
                            print(
                                f"STARTUP: Failed to start orphaned model "
                                f"{anomaly_model_id}: {str(e)}",
                                flush=True,
                            )
                            skipped_jobs.append(f"{anomaly_model_id} (error: {str(e)})")

                # Check for legacy anomaly_predictor directory
                anomaly_predictor_dir = config_dir / "anomaly_predictor"
                if anomaly_predictor_dir.exists():
                    # Check for either hour_*.pkl or any .pkl files
                    hour_model_files = list(anomaly_predictor_dir.glob("hour_*.pkl"))
                    any_pkl_files = list(anomaly_predictor_dir.glob("*.pkl"))
                    if hour_model_files or any_pkl_files:
                        legacy_model_id = f"{config_id}/anomaly_predictor"
                        print(
                            f"STARTUP: Found legacy anomaly model at {anomaly_predictor_dir}",
                            flush=True,
                        )
                        print(f"STARTUP:   - hour_*.pkl files: {len(hour_model_files)}", flush=True)
                        print(f"STARTUP:   - total .pkl files: {len(any_pkl_files)}", flush=True)
                        try:
                            device_id = None
                            success = start_prediction_job(
                                model_id=legacy_model_id,
                                model_type="AnomalyPredictor",
                                device_id=device_id,
                            )
                            if success:
                                started_jobs.append(f"{legacy_model_id} (AnomalyPredictor, legacy)")
                                print(
                                    f"STARTUP: ✓ Started prediction job for legacy model {legacy_model_id}",
                                    flush=True,
                                )
                        except Exception as e:
                            print(
                                f"STARTUP: Failed to start legacy model {legacy_model_id}: {str(e)}",
                                flush=True,
                            )
                            skipped_jobs.append(f"{legacy_model_id} (error: {str(e)})")

        # Summary
        print("=" * 80, flush=True)
        print("STARTUP: Auto-start summary", flush=True)
        print(f"  Started jobs: {len(started_jobs)}", flush=True)
        for job in started_jobs:
            print(f"    - {job}", flush=True)
        if skipped_jobs:
            print(f"  Skipped jobs: {len(skipped_jobs)}", flush=True)
            for job in skipped_jobs:
                print(f"    - {job}", flush=True)
        print("=" * 80, flush=True)

        logger.info("=" * 80)
        logger.info("STARTUP: Auto-start summary")
        logger.info(f"  Started jobs: {len(started_jobs)}")
        for job in started_jobs:
            logger.info(f"    - {job}")
        if skipped_jobs:
            logger.info(f"  Skipped jobs: {len(skipped_jobs)}")
            for job in skipped_jobs:
                logger.info(f"    - {job}")
        logger.info("=" * 80)

    except Exception as e:
        print(f"STARTUP: Failed to auto-start prediction jobs: {str(e)}", flush=True)
        print(f"STARTUP: Traceback:\n{traceback.format_exc()}", flush=True)
        logger.error(f"STARTUP: Failed to auto-start prediction jobs: {str(e)}")
        logger.error(f"STARTUP: Traceback:\n{traceback.format_exc()}")


@app.get("/health")
def health_check():
    """Health check endpoint for container monitoring"""
    status = {
        "status": "healthy",
        "service": "predictive-maintenance",
        "database": {"configured": False, "connection": "unknown"},
    }

    # Check if DATABASE_URL is configured
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        status["database"]["configured"] = True
        # Mask password in URL for security
        safe_url = database_url.split("@")[-1] if "@" in database_url else database_url
        status["database"]["url"] = f"***@{safe_url}"

        # Test database connection
        try:
            registry = DataRegistry(database_url)
            # Try a simple query to verify connection
            with registry.engine.connect() as conn:
                conn.execute("SELECT 1")
            status["database"]["connection"] = "connected"
        except Exception as e:
            status["database"]["connection"] = "failed"
            status["database"]["error"] = str(e)
            status["status"] = "degraded"
    else:
        status["database"]["url"] = (
            "postgresql://postgres:postgres@localhost:5432/thingsboard (default)"
        )

    return status


@app.get("/api/predictiveMaintenance")
def read_root():
    ret = {"Hello": "World"}
    print("Predictive Maintenance API return", ret)
    return ret
