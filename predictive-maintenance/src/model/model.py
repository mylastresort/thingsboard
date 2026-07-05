from fastapi import APIRouter

from src.model.ws import router as ws_router

router = APIRouter()


router.include_router(ws_router)

__all__ = ["router"]
