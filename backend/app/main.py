import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.api.websocket import router as ws_router
from app.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="CodeGen Hub",
    description="AI-powered code generation from project backlogs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "codegen-hub"}


@app.get("/debug/ws")
async def debug_ws():
    from app.services.websocket_manager import manager
    return {
        "connections": {k: len(v) for k, v in manager._connections.items()},
    }
