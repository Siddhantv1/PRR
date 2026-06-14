import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import db
from backend.api.routes import router as api_router
from backend.api.websocket import router as websocket_router
from backend.config import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(config.REPOS_DIR, exist_ok=True)
    os.makedirs("data", exist_ok=True)
    await db.init_db()
    yield


app = FastAPI(title="Pre-Reviewed Contributor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(websocket_router)


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=config.PORT, reload=True)
