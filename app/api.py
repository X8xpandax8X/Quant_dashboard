import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.auth import COOKIE, csrf_token, current_user, require_csrf, serializer, setup_secret
from app.config import Settings
from app.db import Conflict, NotFound, PortfolioStore
from app.schemas import (AnalyticsResponse, AuthResponse, FundamentalsResponse, MarketResponse,
                         PortfolioAnalyticsResponse, PortfolioCreate, PortfolioList, PortfolioRecord,
                         PortfolioUpdate, Positions, PriceResponse, UniverseResponse)

Timeframe = Literal["1D", "5D", "1M", "1Y"]
Authenticated = Annotated[dict, Depends(current_user)]
WritingUser = Annotated[dict, Depends(require_csrf)]


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def create_app(settings: Settings | None = None, data_service=None, *, supabase_transport=None):
    settings = settings or Settings()
    settings.check()
    if settings.backend == "legacy":
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
    application = FastAPI(title="Quant Stock API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    application.state.settings = settings
    application.state.auth_secret = setup_secret(settings)
    application.state.supabase_transport = supabase_transport
    application.state.store = (PortfolioStore(settings.storage_dir / "portfolios.sqlite3")
                               if settings.backend == "legacy" else None)
    if data_service is None:
        from data_engine.service import DataService
        if settings.backend == "supabase":
            from data_engine.supabase_cache import SupabaseMarketCache
            cache = SupabaseMarketCache(settings.supabase_url, settings.supabase_market_key, transport=supabase_transport)
            data_service = DataService(None, settings.mode, cache=cache)
        else:
            data_service = DataService(settings.storage_dir / "cache", settings.mode)
    application.state.data = data_service

    @application.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(NotFound)
    async def not_found(request, exc):
        return JSONResponse(status_code=404, content={"detail": "Portfolio not found"})

    @application.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": {"code": "revision_conflict", "message": str(exc)}})

    @application.get("/health")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    def auth_payload(request, user):
        return {"user": user, "csrf_token": csrf_token(request, user), "mode": settings.mode}

    @application.post("/api/v1/auth/demo", response_model=AuthResponse)
    def demo_login(request: Request, response: Response):
        if settings.mode != "demo":
            raise HTTPException(404, "Not found")
        if request.headers.get("origin", "") != settings.public_origin.rstrip("/"):
            raise HTTPException(403, "Request origin is not allowed")
        user = {"id": "demo-researcher", "email": "demo@quant-stock.local", "name": "Researcher"}
        response.set_cookie(COOKIE, serializer(request).dumps(user), httponly=True, secure=settings.public_origin.startswith("https://"), samesite="lax", max_age=settings.session_max_age)
        return auth_payload(request, user)

    @application.get("/api/v1/auth/me", response_model=AuthResponse)
    def me(request: Request, user: Authenticated):
        return auth_payload(request, user)

    @application.post("/api/v1/auth/logout", status_code=204)
    def logout(request: Request, response: Response, user: WritingUser):
        if settings.backend == "supabase":
            request.state.user_data_client.logout()
        response.delete_cookie(COOKIE, httponly=True, secure=settings.public_origin.startswith("https://"), samesite="lax")

    def validate_symbol(symbol):
        if symbol not in data_service.universe_symbols():
            raise HTTPException(422, "Select a current S&P 500 constituent")

    def validate_positions(payload):
        for position in payload.positions:
            validate_symbol(position.symbol)

    def bar_payload(symbol, timeframe):
        result = data_service.get_history(symbol, timeframe)
        frame = result.frame
        bars = [{"time": t.isoformat(), **{c: row.get(c) for c in ("open", "high", "low", "close", "volume")}} for t, row in frame.iterrows()]
        closes = frame["close"].dropna() if "close" in frame else pd.Series(dtype=float)
        last = float(closes.iloc[-1]) if len(closes) else None
        # Quote change uses the previous completed trading session, independently of chart range.
        daily = result if timeframe == "1Y" else data_service.get_history(symbol, "1Y")
        dc = daily.frame["close"].dropna() if "close" in daily.frame else pd.Series(dtype=float)
        baseline = None
        if len(dc) >= 2:
            last_date = closes.index[-1].date() if len(closes) else None
            preceding = dc.loc[[t.date() < last_date for t in dc.index]] if last_date else dc.iloc[0:0]
            baseline = float(preceding.iloc[-1]) if len(preceding) else float(dc.iloc[-2])
        change = last / baseline - 1 if last is not None and baseline and baseline > 0 else None
        return clean_json({"instrument": data_service.instrument(symbol), "bars": bars, "last_price": last, "change": change, "meta": result.meta})

    @application.get("/api/v1/universe", response_model=UniverseResponse)
    def universe(user: Authenticated, q: str = Query("", max_length=100), limit: int = Query(50, ge=1, le=600)):
        return {"items": data_service.search_universe(q, limit), "source": getattr(data_service,"universe_source","Dated S&P 500 constituent snapshot"), "as_of": getattr(data_service, "universe_as_of", None)}

    @application.get("/api/v1/markets", response_model=MarketResponse)
    def markets(user: Authenticated, timeframe: Timeframe = "1D"):
        from data_engine.instruments import MARKETS
        with ThreadPoolExecutor(max_workers=4) as pool:
            items = list(pool.map(lambda i: bar_payload(i["symbol"], timeframe), MARKETS))
        return {"items": items, "timeframe": timeframe}

    @application.get("/api/v1/stocks/{symbol}/prices", response_model=PriceResponse)
    def prices(symbol: str, user: Authenticated, timeframe: Timeframe = "1Y"):
        validate_symbol(symbol)
        return bar_payload(symbol, timeframe)

    @application.get("/api/v1/stocks/{symbol}/analytics", response_model=AnalyticsResponse)
    def analytics(symbol: str, user: Authenticated, peers: str = Query("", max_length=140), timeframe: Timeframe = "1Y"):
        from quant_engine.analytics import distribution, volume_profile, comparison, capm
        validate_symbol(symbol)
        symbols = list(dict.fromkeys([symbol, *[s.strip() for s in peers.split(",") if s.strip()]]))
        if len(symbols) > 6:
            raise HTTPException(422, "Compare at most six stocks")
        for peer in symbols:
            validate_symbol(peer)
        histories = {s: data_service.get_history(s, "1Y") for s in symbols}
        target = histories[symbol]
        benchmark = data_service.get_history("^GSPC", "1Y")
        rf = data_service.risk_free_rate()
        meta = dict(target.meta)
        meta["notes"] = list(meta.get("notes", [])) + ["Statistics use trailing 1Y daily price returns; dividends excluded.", "Risk-free proxy: FRED DGS10, observed " + str(rf.get("date") or "unavailable")]
        sources=[*histories.values(),benchmark]
        if settings.mode != "demo" and meta.get("status") != "unavailable":
            if any(r.meta.get("status") in {"unavailable","stale","partial"} for r in sources) or rf.get("meta",{}).get("status") in {"unavailable","stale","partial"}:
                meta["status"]="partial"
                meta["notes"].append("Some comparison or risk-free inputs are stale, partial or unavailable; inspect individual results.")
        return clean_json({"symbol": symbol, "distribution": distribution(target.frame), "volume_profile": volume_profile(data_service.get_history(symbol, timeframe).frame), "comparison": comparison({s:r.frame for s,r in histories.items()}), "capm": capm(target.frame, benchmark.frame, rf.get("rate")), "meta": meta})

    @application.get("/api/v1/stocks/{symbol}/fundamentals", response_model=FundamentalsResponse)
    def fundamentals(symbol: str, user: Authenticated):
        from quant_engine.analytics import capm, sharpe_ratio
        validate_symbol(symbol)
        payload = data_service.get_fundamentals(symbol)
        history = data_service.get_history(symbol, "1Y")
        benchmark = data_service.get_history("^GSPC", "1Y")
        rf = data_service.risk_free_rate()
        model = capm(history.frame, benchmark.frame, rf.get("rate"))
        payload["metrics"].update(beta=model.get("beta"), capm_target=model.get("scenario_price"), sharpe_6m=sharpe_ratio(history.frame, rf.get("rate")))
        if settings.mode != "demo" and payload["meta"]["status"] != "unavailable" and any(s in {"stale","unavailable","partial"} for s in [history.meta.get("status"),benchmark.meta.get("status"),rf.get("meta",{}).get("status")]):
            payload["meta"]["status"]="partial"
            payload["meta"]["notes"].append("Some price or risk-free inputs are stale or unavailable; derived metrics may be unavailable.")
        return clean_json(payload)

    @application.post("/api/v1/portfolio-analytics", response_model=PortfolioAnalyticsResponse)
    def simulate(payload: Positions, user: WritingUser):
        from quant_engine.analytics import portfolio_analysis
        validate_positions(payload)
        if sum(p.weight_bps for p in payload.positions) != 10000:
            raise HTTPException(422, "Portfolio weights must total exactly 100%")
        active = [p for p in payload.positions if p.weight_bps > 0]
        histories = {p.symbol: data_service.get_history(p.symbol, "1Y") for p in active}
        benchmark = data_service.get_history("^GSPC", "1Y")
        rf = data_service.risk_free_rate()
        result = portfolio_analysis({s:r.frame for s,r in histories.items()}, {p.symbol:p.weight_bps for p in active}, benchmark.frame, rf.get("rate"))
        sectors = {}
        for p in active:
            sector = data_service.instrument(p.symbol).get("sector") or "Unclassified"
            sectors.setdefault(sector, {"sector":sector, "weight_bps":0, "holdings":[]})
            sectors[sector]["weight_bps"] += p.weight_bps
            sectors[sector]["holdings"].append(p.model_dump())
        meta = dict(benchmark.meta)
        meta["sample_count"] = result["metrics"]["sample_count"]
        meta["notes"] = list(meta.get("notes", [])) + ["Constant target weights rebalanced daily; no fees, taxes or dividends.", "Risk-free proxy observed " + str(rf.get("date") or "unavailable")]
        price_statuses = [benchmark.meta.get("status"), *(h.meta.get("status") for h in histories.values())]
        risk_free_status = rf.get("meta", {}).get("status")
        if any(status == "unavailable" for status in price_statuses):
            meta["status"] = "unavailable"
        elif any(status in {"partial", "stale"} for status in price_statuses) or risk_free_status in {"partial", "stale", "unavailable"}:
            meta["status"] = "partial"
            meta["notes"].append("Some price or risk-free inputs are stale, partial or unavailable; derived metrics may be unavailable.")
        return clean_json({**result, "sectors": sorted(sectors.values(), key=lambda s:-s["weight_bps"]), "meta":meta})

    def portfolio_call(request, user, action, *args):
        if settings.backend == "supabase":
            from packages.portfolio_service import SupabasePortfolioStore
            return getattr(SupabasePortfolioStore(request.state.user_data_client), action)(*args)
        return getattr(application.state.store, action)(user["id"], *args)

    @application.get("/api/v1/portfolios", response_model=PortfolioList)
    def list_portfolios(request: Request, user: Authenticated):
        return {"items": portfolio_call(request, user, "list")}

    @application.post("/api/v1/portfolios", response_model=PortfolioRecord, status_code=201)
    def create_portfolio(request: Request, payload: PortfolioCreate, user: WritingUser, idempotency_key: str | None = Header(None, max_length=128)):
        validate_positions(payload)
        return portfolio_call(request, user, "create", payload.name, [p.model_dump() for p in payload.positions], idempotency_key)

    @application.get("/api/v1/portfolios/{portfolio_id}", response_model=PortfolioRecord)
    def get_portfolio(request: Request, portfolio_id: str, user: Authenticated):
        return portfolio_call(request, user, "get", portfolio_id)

    @application.patch("/api/v1/portfolios/{portfolio_id}", response_model=PortfolioRecord)
    def update_portfolio(request: Request, portfolio_id: str, payload: PortfolioUpdate, user: WritingUser):
        validate_positions(payload)
        return portfolio_call(request, user, "update", portfolio_id, payload.name, [p.model_dump() for p in payload.positions], payload.revision)

    @application.delete("/api/v1/portfolios/{portfolio_id}", status_code=204)
    def delete_portfolio(request: Request, portfolio_id: str, user: WritingUser, revision: int = Query(ge=1)):
        portfolio_call(request, user, "delete", portfolio_id, revision)

    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if (dist / "assets").exists():
        application.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        if (dist / "index.html").exists():
            return FileResponse(dist / "index.html", headers={"Cache-Control":"no-cache"})
        return JSONResponse({"message":"Frontend is not built. Start the Vite dev server or run the frontend build."})

    return application
