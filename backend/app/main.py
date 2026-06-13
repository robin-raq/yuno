"""FastAPI application entry point."""
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.api.agents import router as agents_router
from app.api.tasks import router as tasks_router
from app.api.workflows import router as workflows_router

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Initialising database")
    await init_db()
    log.info("Database ready")
    yield
    log.info("Shutdown")


app = FastAPI(title="Yuno API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(workflows_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
