"""FastAPI application entry point."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import AsyncSessionLocal, init_db
from app.api.agents import router as agents_router
from app.api.tasks import router as tasks_router
from app.api.workflows import router as workflows_router
from app.api.events import router as events_router
from app.services.event_service import get_event_service
from app.services.message_bus import get_message_bus
from app.services.workflow_worker import WorkflowWorker

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)

_WORKER_IDLE_SLEEP = 0.05


async def _worker_loop(worker: WorkflowWorker) -> None:
    """Drain the in-process dispatch queue until cancelled (S2 Unit 9)."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                processed = await worker.process_next(db)
            if not processed:
                await asyncio.sleep(_WORKER_IDLE_SLEEP)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Worker loop error")
            await asyncio.sleep(0.5)


def _worker_loop_enabled() -> bool:
    return os.getenv("ENABLE_WORKER_LOOP", "").lower() in ("1", "true", "yes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Initialising database")
    await init_db()
    bus = get_message_bus()
    worker = WorkflowWorker(bus)
    app.state.message_bus = bus
    app.state.worker = worker
    get_event_service()

    worker_task: asyncio.Task | None = None
    if _worker_loop_enabled():
        worker_task = asyncio.create_task(_worker_loop(worker))
        log.info("Workflow worker loop started")

    log.info("Database ready")
    yield

    if worker_task is not None:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task
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
app.include_router(events_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
