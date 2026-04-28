"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.api.routes import router
from src.config import load as load_config
from src.db.conn import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    init_db(cfg.database.dsn)
    conn = psycopg.connect(cfg.database.dsn)
    app.state.db_conn = conn
    app.state.base_url = cfg.api.base_url
    log.info("API started — base_url=%s", cfg.api.base_url)
    yield
    conn.close()


app = FastAPI(title="Usenet Indexer", lifespan=lifespan)
app.include_router(router)
