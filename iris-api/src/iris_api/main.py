"""FastAPI application: the HTTP contract between Scout (ingest), Guardian (lookup) and analysts (review)."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, Query, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from . import __version__, service
from .config import Settings
from .db import make_engine, make_session_factory
from .errors import ApiError, install_handlers
from .names import normalize
from .schemas import (Eco, IngestRequest, IngestResult, LookupRequest, LookupResponse, PackageDetail, PackageList,
                      ReviewRequest, ScoutVerdict, Status)
from .security import Authenticator, Principal, RateLimiter, Role, require

log = logging.getLogger("iris_api")


def create_app(settings: Optional[Settings] = None, engine: Optional[Engine] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if not settings.allow_no_auth:
        settings.validate()                      # fail closed at startup, not on first request
    engine = engine or make_engine(settings.database_url)
    sessions = make_session_factory(engine)

    app = FastAPI(title="Iris Threat Intelligence API", version=__version__,
                  description="Central store for AI-hallucinated package findings (Project Iris, Phase 2).")
    app.state.settings, app.state.engine = settings, engine
    app.state.auth, app.state.limiter = Authenticator(settings), RateLimiter(settings.rate_limit_per_min)
    install_handlers(app)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def get_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    # --------------------------------------------------------------- routes
    @app.get("/healthz", tags=["ops"])
    def healthz(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        return {"status": "ok", "version": __version__}

    @app.post("/v1/findings", response_model=IngestResult, tags=["scout"])
    def ingest_findings(body: IngestRequest, db: Session = Depends(get_db),
                        who: Principal = Depends(require(Role.INGEST))):
        res = service.ingest(db, body)
        log.info("ingest run=%s key=%s created=%d updated=%d obs=%d assessments=%d rejected=%d",
                 res.run_id, who.key_id, res.packages_created, res.packages_updated,
                 res.observations_added, res.assessments_added, len(res.rejected))
        return res

    @app.post("/v1/lookup", response_model=LookupResponse, tags=["guardian"])
    def lookup(body: LookupRequest, db: Session = Depends(get_db), who: Principal = Depends(require(Role.READ))):
        return LookupResponse(results=service.lookup(db, body.packages, settings))

    @app.get("/v1/package", response_model=PackageDetail, tags=["analyst"])
    def package(ecosystem: Eco, name: str = Query(min_length=1, max_length=256), db: Session = Depends(get_db),
                who: Principal = Depends(require(Role.READ))):
        return service.package_detail(db, ecosystem, name, settings)

    @app.get("/v1/packages", response_model=PackageList, tags=["analyst"])
    def packages(ecosystem: Optional[Eco] = None, verdict: Optional[ScoutVerdict | str] = None,
                 status: Optional[Status] = None, limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0), db: Session = Depends(get_db),
                 who: Principal = Depends(require(Role.READ))):
        allowed = {"low_risk", "needs_review", "high_risk", "unresolved", "unknown", "not_assessed"}
        if verdict and verdict not in allowed:
            raise ApiError(422, "validation_error", f"verdict must be one of {sorted(allowed)}")
        return service.list_packages(db, settings, ecosystem, verdict, status, limit, offset)

    @app.get("/v1/stats", tags=["analyst"])
    def stats(db: Session = Depends(get_db), who: Principal = Depends(require(Role.READ))):
        return service.stats(db)

    @app.put("/v1/review", tags=["analyst"])
    def review(body: ReviewRequest, db: Session = Depends(get_db), who: Principal = Depends(require(Role.ADMIN))):
        service.review(db, body, who.key_id)
        log.info("review key=%s %s/%s -> %s", who.key_id, body.ecosystem, normalize(body.ecosystem, body.name), body.status)
        return service.lookup(db, [body], settings)[0]

    return app


def app_factory() -> FastAPI:       # uvicorn --factory iris_api.main:app_factory
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return create_app()
