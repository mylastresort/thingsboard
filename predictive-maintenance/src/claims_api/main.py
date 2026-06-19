from fastapi import FastAPI

from .database import Base, engine
from .router import router as claims_router

app = FastAPI(title="Claims API")

app.include_router(claims_router)


@app.on_event("startup")
async def on_startup():
    # In a real deployment, the `claim` table is already managed by
    # ThingsBoard's own SQL migrations (or your Alembic setup) -- this is
    # just a dev-convenience for spinning up against an empty database.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
