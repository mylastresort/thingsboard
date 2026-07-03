"""
WebSocket __init__ - Combines all WebSocket endpoints
"""

from fastapi import APIRouter

from .unified import router as unified_router

router = APIRouter(
    prefix="/models",
    tags=["models-websocket"],
)

router.include_router(unified_router)
