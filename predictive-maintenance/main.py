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

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi_mcp import FastApiMCP  # noqa: F811

from library.core.data_registry import DataRegistry
from src.logger import logger  # Global logger
from src.model.client import get_client
from src.model.model import router as model_router
from src.notify import router as notify_router
from src.on_startup import on_startup
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

token_auth_scheme = HTTPBearer()

# async def verify_mcp_auth(token=Depends(token_auth_scheme)):
#     if token.credentials != settings.mcp_api_token:
#         raise HTTPException(status_code=401, detail="Invalid credentials")
#     return token.credentials

mcp = FastApiMCP(
    app,
    name=settings.app_name,
    description=settings.app_description,
    exclude_operations=[],
    include_tags=["predictive-maintenance"],
    # auth_config=AuthConfig(dependencies=[Depends(verify_mcp_auth)]),
)

mcp.mount_http()
# Log startup with current log level
logger.info("Predictive Maintenance Service Starting")


@app.on_event("startup")
async def startup_event():
    await on_startup()


@app.on_event("startup")
async def check_thingsboard_connection():
    try:
        _ = get_client()
        logger.info("Successfully connected to Thingsboard")
    except Exception as e:
        logger.error(f"Failed to connect to Thingsboard: {e}")
        raise e


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
