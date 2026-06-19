import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Point this at the same Postgres instance ThingsBoard already uses.
# e.g. postgresql+asyncpg://thingsboard:<pw>@localhost:5432/thingsboard
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://thingsboard:postgres@localhost:5432/thingsboard",
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
