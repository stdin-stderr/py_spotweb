"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.api.routes import router, _compute_category_counts
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
    app.state.config = cfg

    # Initialize Jinja2 templates with caching disabled to avoid dict hashing issues
    templates_dir = Path(__file__).parent / "templates"
    app.state.templates = Jinja2Templates(directory=str(templates_dir))
    # Disable caching in the Jinja2 environment
    app.state.templates.env.cache = None

    # Pre-compute category counts for sidebar filters
    import src.api.routes as routes_module
    log.info("Computing category counts...")
    routes_module._CATEGORY_COUNTS = _compute_category_counts(conn)
    log.info("API started — base_url=%s, category counts=%d", cfg.api.base_url, len(routes_module._CATEGORY_COUNTS))

    yield
    conn.close()


app = FastAPI(title="Usenet Indexer", lifespan=lifespan)
app.include_router(router)
