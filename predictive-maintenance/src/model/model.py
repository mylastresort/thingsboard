"""
Main model service module - Combines REST API and WebSocket endpoints

This module provides:
1. WebSocket API - Unified endpoint for all model operations
2. Background job management system for predictions

Directory Structure:
- api/       - REST API endpoints (currently unused, kept for future use)
- ws/        - WebSocket endpoints
  - unified.py - /models/ws/unified - All model operations via WebSocket
- shared.py  - Shared utilities (get_data_registry, train_and_save_model)
- job.py     - Background job management for predictions

Usage:
    from src.model.model import router
    app.include_router(router)
"""

from fastapi import APIRouter

from src.model.api import router as api_router
from src.model.ws import router as ws_router

# Create main router that combines all sub-routers
router = APIRouter()

# Include REST API routes
router.include_router(api_router)

# Include WebSocket routes
router.include_router(ws_router)

__all__ = ["router"]
