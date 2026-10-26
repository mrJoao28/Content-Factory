import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.exc import IntegrityError

from .config import settings
from .db import engine, seed
from .integrations import PlatformError
from .models import Base
from .queue import Worker
from .security import ConfigurationRequired


@asynccontextmanager
async def lifespan(app):
    # Offline bootstrap does not claim to have applied an Alembic revision.
    Base.metadata.create_all(engine)
    seed()
    worker = Worker()
    if os.environ.get("FACTORY_DISABLE_WORKER") != "1":
        worker.start()
    app.state.worker = worker
    yield
    worker.close()


app = FastAPI(title="AI Content Factory", version="0.1.0", lifespan=lifespan)
origins = [f"http://127.0.0.1:{settings.web_port}", f"http://localhost:{settings.web_port}"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Content-Type", "X-Factory-Client"], allow_credentials=False)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def local_guard(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in origins:
        return JSONResponse({"detail": "Untrusted origin"}, 403)
    if request.method in {"POST", "PATCH", "DELETE", "PUT"}:
        if request.headers.get("x-factory-client") != "local":
            return JSONResponse({"detail": "Missing local client header"}, 403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(ConfigurationRequired)
async def config_error(request, exc):
    return JSONResponse({"detail": str(exc), "state": "MISSING_CONFIG"}, 409)


@app.exception_handler(PlatformError)
async def platform_error(request, exc):
    return JSONResponse({"detail": str(exc)}, 502)


@app.exception_handler(IntegrityError)
async def conflict_error(request, exc):
    return JSONResponse({"detail": "Conflicting record or referenced library item"}, 409)


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({"detail": str(exc)}, 422)


@app.exception_handler(httpx.HTTPError)
async def network_error(request, exc):
    return JSONResponse({"detail": "External network request failed; verify connectivity."}, 502)


from . import routes_library, routes_projects, routes_system  # noqa: E402
app.include_router(routes_projects.router)
app.include_router(routes_library.router)
app.include_router(routes_system.router)
