from fastapi import Depends, FastAPI

from .dependencies import get_query_token, get_token_header
from .internal import admin
from .routers import items, users
from .internal import flexsim

PORT = 7872

app = FastAPI(dependencies=[Depends(get_query_token)], PORT=PORT)


app.include_router(users.router)
app.include_router(items.router)
app.include_router(flexsim.router)
app.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_token_header)],
    responses={418: {"description": "I'm a teapot"}},
)


@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}
