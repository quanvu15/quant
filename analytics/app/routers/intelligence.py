"""
Phase 4 — Global Intelligence API router.

Wraps: acled_data.py, hdx_data.py, marinetraffic_data.py, aisstream_data.py,
       fred_data.py, worldbank_data.py, imf_data.py, oecd_data.py,
       economic_calendar.py, ecb_data.py, boj_fetcher.py, boe_data.py,
       rba_data.py, bls_data.py, census_data.py, eurostat_data.py,
       eia_data.py, relationship_map.py
"""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Query

from app.dependencies import ApiKeyDep
from core.cache import TTL, cache
from core.errors import script_error_to_api_error
from core.python_runner import PythonRunnerError, get_runner
from core.script_catalog import catalog
from models.requests.intelligence import MaritimeAreaRequest, MaritimeBatchRequest

logger = structlog.get_logger(__name__)
router = APIRouter()


async def _run(script_key: str, payload: dict, timeout: int = 60) -> dict:
    runner = get_runner(timeout=timeout)
    script = catalog.path(script_key)
    try:
        return await runner.run(script, payload, timeout=timeout)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc


# ── 4.1 Geopolitics ───────────────────────────────────────────────────────────

@router.get("/geopolitics/events", summary="ACLED conflict events")
async def get_geopolitics_events(
    country: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    days: int = Query(default=30, ge=1, le=365),
):
    """GET /api/v1/intelligence/geopolitics/events — TTL 2 min."""
    cache_key = cache.build_key("intel", "geo_events", country=country, category=category, limit=limit, days=days)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "get_events",
        "params": {"country": country, "category": category, "limit": limit, "days": days},
    }
    result = await _run("intel.acled", payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.GEOPOLITICS_EVENTS)
    return result


@router.get("/geopolitics/countries", summary="Countries with event counts")
async def get_geopolitics_countries():
    cache_key = cache.build_key("intel", "geo_countries")
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_countries", "params": {}}
    result = await _run("intel.acled", payload, timeout=60)
    await cache.set(cache_key, result, ttl=600)
    return result


@router.get("/geopolitics/categories", summary="Event categories")
async def get_geopolitics_categories():
    cache_key = cache.build_key("intel", "geo_categories")
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_categories", "params": {}}
    result = await _run("intel.acled", payload, timeout=30)
    await cache.set(cache_key, result, ttl=600)
    return result


@router.get("/geopolitics/hdx/{context}", summary="HDX humanitarian datasets")
async def get_hdx(context: str):
    """GET /api/v1/intelligence/geopolitics/hdx/{context} — TTL 1h."""
    cache_key = cache.build_key("intel", "hdx", context=context)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_datasets", "params": {"context": context}}
    result = await _run("intel.hdx", payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.FRED_SERIES)
    return result


@router.get("/geopolitics/relationships/{ticker}", summary="Corporate geopolitical relationship map")
async def get_geo_relationships(ticker: str):
    cache_key = cache.build_key("intel", "geo_rel", ticker=ticker)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_relationships", "params": {"ticker": ticker.upper()}}
    result = await _run("intel.relationship_map", payload, timeout=30)
    await cache.set(cache_key, result, ttl=600)
    return result


# ── 4.2 Maritime ──────────────────────────────────────────────────────────────

@router.get("/maritime/vessel/{imo}", summary="Vessel position & details by IMO")
async def get_vessel(imo: str, _api_key: ApiKeyDep):
    """GET /api/v1/intelligence/maritime/vessel/{imo} — TTL 1 min."""
    cache_key = cache.build_key("intel", "vessel", imo=imo)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_vessel", "params": {"imo": imo}}
    result = await _run("intel.marinetraffic", payload, timeout=30)
    await cache.set(cache_key, result, ttl=TTL.MARITIME_VESSEL)
    return result


@router.post("/maritime/vessels/batch", summary="Batch vessel lookup by IMO list")
async def get_vessels_batch(body: MaritimeBatchRequest, _api_key: ApiKeyDep):
    payload = {"action": "get_vessels_batch", "params": {"imos": body.imos}}
    return await _run("intel.marinetraffic", payload, timeout=60)


@router.post("/maritime/vessels/area", summary="Vessels in geographic bounding box")
async def get_vessels_area(body: MaritimeAreaRequest, _api_key: ApiKeyDep):
    payload = {
        "action": "get_vessels_area",
        "params": {
            "lat_min": body.lat_min, "lat_max": body.lat_max,
            "lon_min": body.lon_min, "lon_max": body.lon_max,
            "vessel_type": body.vessel_type,
        },
    }
    return await _run("intel.marinetraffic", payload, timeout=60)


@router.get("/maritime/vessel/{imo}/history", summary="Vessel AIS track history")
async def get_vessel_history(imo: str, days: int = Query(default=7, ge=1, le=30), _api_key: ApiKeyDep = None):
    cache_key = cache.build_key("intel", "vessel_history", imo=imo, days=days)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_vessel_history", "params": {"imo": imo, "days": days}}
    result = await _run("intel.aisstream", payload, timeout=60)
    await cache.set(cache_key, result, ttl=300)
    return result


# ── 4.3 Economics ─────────────────────────────────────────────────────────────

# QUAN TRỌNG: /search phải đứng TRƯỚC /{series_id} để tránh FastAPI match "search" như series_id
@router.get("/economics/fred/search", summary="Search FRED series")
async def search_fred(q: str = Query(..., min_length=1), limit: int = Query(default=20, le=100)):
    cache_key = cache.build_key("intel", "fred_search", q=q, limit=limit)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "search_series", "source": "fred", "params": {"query": q, "limit": limit}}
    result = await _run("intel.fred", payload, timeout=30)
    await cache.set(cache_key, result, ttl=TTL.FRED_SERIES)
    return result


@router.get("/economics/fred/{series_id}", summary="FRED economic series data")
async def get_fred_series(
    series_id: str,
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    frequency: Optional[str] = Query(default=None),
):
    """GET /api/v1/intelligence/economics/fred/{series_id} — TTL 1h."""
    cache_key = cache.build_key("intel", "fred", series=series_id, start=start, end=end, freq=frequency)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "get_series",
        "source": "fred",
        "params": {"series_id": series_id, "start": start, "end": end, "frequency": frequency},
    }
    result = await _run("intel.fred", payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.FRED_SERIES)
    return result


@router.get("/economics/worldbank/{indicator}/{country}", summary="World Bank indicator data")
async def get_worldbank(
    indicator: str,
    country: str,
    start: Optional[int] = Query(default=2010),
    end: Optional[int] = Query(default=2024),
):
    cache_key = cache.build_key("intel", "worldbank", indicator=indicator, country=country, start=start, end=end)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "get_indicator",
        "params": {"indicator": indicator, "country": country, "start": start, "end": end},
    }
    result = await _run("intel.worldbank", payload, timeout=90)  # WorldBank API can be slow
    await cache.set(cache_key, result, ttl=TTL.FRED_SERIES)
    return result


@router.get("/economics/imf/{dataset}/{series}", summary="IMF dataset series")
async def get_imf(dataset: str, series: str):
    cache_key = cache.build_key("intel", "imf", dataset=dataset, series=series)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_series", "params": {"dataset": dataset, "series": series}}
    result = await _run("intel.imf", payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.FRED_SERIES)
    return result


@router.get("/economics/oecd/{dataset}", summary="OECD dataset")
async def get_oecd(
    dataset: str,
    country: Optional[str] = Query(default=None),
    subject: Optional[str] = Query(default=None),
    measure: Optional[str] = Query(default=None),
):
    cache_key = cache.build_key("intel", "oecd", dataset=dataset, country=country, subject=subject)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "get_dataset",
        "params": {"dataset": dataset, "country": country, "subject": subject, "measure": measure},
    }
    result = await _run("intel.oecd", payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.FRED_SERIES)
    return result


@router.get("/economics/calendar", summary="Economic events calendar")
async def get_economic_calendar(
    limit: int = Query(default=25, ge=1, le=200),
    country: Optional[str] = Query(default=None),
):
    """GET /api/v1/intelligence/economics/calendar — TTL 5 min."""
    cache_key = cache.build_key("intel", "econ_calendar", limit=limit, country=country)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_calendar", "params": {"limit": limit, "country": country}}
    result = await _run("intel.economic_calendar", payload, timeout=30)
    await cache.set(cache_key, result, ttl=TTL.ECONOMIC_CALENDAR)
    return result


_CENTRAL_BANK_MAP = {
    "fed": "intel.fred",
    "ecb": "intel.ecb",
    "boj": "intel.boj",
    "boe": "intel.boe",
    "rba": "intel.rba",
}


@router.get("/economics/central-banks/{bank}", summary="Central bank data series")
async def get_central_bank(
    bank: str,
    series: Optional[str] = Query(default="policy_rate"),
    start: Optional[str] = Query(default="2020-01-01"),
):
    """GET /api/v1/intelligence/economics/central-banks/{bank} — TTL 1h."""
    bank_lower = bank.lower()
    script_key = _CENTRAL_BANK_MAP.get(bank_lower, "intel.fred")
    cache_key = cache.build_key("intel", "central_bank", bank=bank_lower, series=series, start=start)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    # Pass bank as hint so bridge routes correctly
    payload = {
        "action": "get_series",
        "source": bank_lower,
        "params": {"bank": bank_lower, "series": series, "start": start},
    }
    result = await _run(script_key, payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.CENTRAL_BANK)
    return result


# ── 4.4 Government Data ───────────────────────────────────────────────────────

@router.get("/govdata/us/bls/{series_id}", summary="BLS labor statistics series")
async def get_bls(series_id: str):
    cache_key = cache.build_key("intel", "bls", series=series_id)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_series", "source": "bls", "params": {"series_id": series_id}}
    result = await _run("intel.bls", payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.GOV_DATA)
    return result


@router.get("/govdata/{country}/{dataset}", summary="Government open data by country/dataset")
async def get_govdata(country: str, dataset: str, limit: int = Query(default=100, le=1000)):
    """Generic government data endpoint — routes to appropriate script."""
    _COUNTRY_SCRIPT = {
        "us": "intel.census",
        "eu": "intel.eurostat",
    }
    script_key = _COUNTRY_SCRIPT.get(country.lower(), "intel.census")
    cache_key = cache.build_key("intel", "govdata", country=country, dataset=dataset, limit=limit)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_dataset", "params": {"country": country, "dataset": dataset, "limit": limit}}
    result = await _run(script_key, payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.GOV_DATA)
    return result


# ── 4.5 Energy & Environment ──────────────────────────────────────────────────

@router.get("/energy/eia/{category}", summary="EIA energy data")
async def get_eia(
    category: str,
    series_id: Optional[str] = Query(default=None),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
):
    cache_key = cache.build_key("intel", "eia", category=category, series=series_id, start=start, end=end)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "get_data",
        "params": {"category": category, "series_id": series_id, "start": start, "end": end},
    }
    result = await _run("intel.eia", payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.ENERGY)
    return result


@router.get("/environment/co2", summary="CO2 emissions data (OWID)")
async def get_co2(
    country: Optional[str] = Query(default=None),
    start: int = Query(default=2000),
    end: int = Query(default=2024),
):
    cache_key = cache.build_key("intel", "co2", country=country, start=start, end=end)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_co2", "params": {"country": country, "start": start, "end": end}}
    # Use worldbank as fallback for CO2 data
    result = await _run("intel.worldbank", payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.ENVIRONMENT)
    return result
