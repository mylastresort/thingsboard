from fastapi import APIRouter
from .run_application import run_app


router = APIRouter()


@router.get("/flexsim")
async def update_admin():
    return run_app()
