import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, closing
from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .core import summarize, synthetic
from .checker import load_config, check_service


def create_app(config_path=None, database="data/lantern.sqlite", probe=check_service):
    config = load_config(config_path) if config_path else None
    stop = threading.Event()
    path = Path(database)
    if config:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS samples(service_id TEXT,time INTEGER,state TEXT,latency REAL,PRIMARY KEY(service_id,time))"
            )
            db.execute("CREATE INDEX IF NOT EXISTS samples_time ON samples(time)")

    def collect():
        with ThreadPoolExecutor(max_workers=4) as pool:
            while not stop.is_set():
                timestamp = int(time.time())
                rows = []
                for service, result in zip(
                    config["services"], pool.map(probe, config["services"])
                ):
                    rows.append(
                        (service["id"], timestamp, result["state"], result["latency"])
                    )
                with closing(sqlite3.connect(path, timeout=10)) as db, db:
                    db.executemany(
                        "INSERT OR REPLACE INTO samples VALUES(?,?,?,?)", rows
                    )
                    db.execute(
                        "DELETE FROM samples WHERE time<?",
                        (timestamp - config["retention_days"] * 86400,),
                    )
                stop.wait(config["interval"])

    @asynccontextmanager
    async def lifespan(app):
        worker = None
        if config:
            worker = threading.Thread(
                target=collect, daemon=True, name="lantern-checker"
            )
            worker.start()
        yield
        stop.set()
        if worker:
            worker.join(timeout=18)

    app = FastAPI(title="Lantern Homelab Health", lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    )

    @app.get("/api/config")
    def mode():
        return {
            "mode": "live-local" if config else "synthetic",
            "interval": config["interval"] if config else 600,
            "retention_days": config["retention_days"] if config else None,
        }

    @app.get("/api/summary")
    def summary(
        hours: int = Query(24, ge=1, le=168),
        scenario: str = Query("normal", pattern="^(normal|incident|recovery|gap)$"),
    ):
        now = int(time.time())
        if not config:
            services, samples = synthetic(now, scenario)
            return {
                "mode": "synthetic",
                **summarize(services, samples, now, hours, 600),
            }
        with closing(sqlite3.connect(path, timeout=10)) as db, db:
            db.row_factory = sqlite3.Row
            samples = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM samples WHERE time>=? AND time<=?",
                    (now - hours * 3600, now),
                )
            ]
        return {
            "mode": "live-local",
            **summarize(config["services"], samples, now, hours, config["interval"]),
        }

    @app.middleware("http")
    async def privacy_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.mount(
        "/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web"
    )
    return app
