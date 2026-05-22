"""
API Bridge — Global Intelligence (Phase 4)
==========================================
Nhận JSON payload qua stdin, dispatch đến đúng function trong các scripts:
fred_data.py, worldbank_data.py, acled_data.py, imf_data.py, oecd_data.py,
ecb_data.py, boj_fetcher.py, boe_data.py, rba_data.py, bls_data.py,
census_data.py, eurostat_data.py, eia_data.py, economic_calendar.py,
marinetraffic_data.py, aisstream_data.py, hdx_data.py, relationship_map.py
"""
import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            print(json.dumps({"success": False, "error": "No input"}))
            return
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
        return

    action = payload.get("action", "")
    params = payload.get("params", {})
    source = payload.get("source", "")  # optional: which script to use

    try:
        result = dispatch(action, params, source)
        if isinstance(result, dict) and "success" not in result and "error" not in result:
            result = {"success": True, "data": result}
        elif isinstance(result, list):
            result = {"success": True, "data": result}
        elif isinstance(result, dict) and "error" in result:
            result = {"success": False, **result}
        elif not isinstance(result, dict):
            result = {"success": True, "data": result}
        print(json.dumps(result, default=str))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))


def dispatch(action: str, params: dict, source: str = ""):
    # ── FRED search (phải check trước get_series) ─────────────────────────────
    if action == "search_series":
        import fred_data as fd
        return fd.search_series(params.get("query", ""), limit=params.get("limit", 20))

    # ── FRED get series ───────────────────────────────────────────────────────
    if action == "get_series" and (source == "fred" or "series_id" in params):
        import fred_data as fd
        series_id = params.get("series_id", "GDP")
        return fd.get_series(
            series_id,
            start_date=params.get("start"),
            end_date=params.get("end"),
            frequency=params.get("frequency"),
        )

    if action == "get_indicator":
        import worldbank_data as wb
        country = params.get("country", "US")
        indicator = params.get("indicator", "NY.GDP.MKTP.CD")
        start_year = params.get("start", 2010)
        end_year = params.get("end", 2024)
        date_range = f"{start_year}:{end_year}"
        result = wb.get_indicators(
            country_code=country,
            indicator=indicator,
            date_range=date_range,
        )
        return result

    if action == "get_co2":
        import worldbank_data as wb
        country = params.get("country", "WLD")
        start_year = params.get("start", 2000)
        end_year = params.get("end", 2024)
        result = wb.get_indicators(
            country_code=country or "WLD",
            indicator="EN.ATM.CO2E.KT",
            date_range=f"{start_year}:{end_year}",
        )
        return result

    # ── ACLED ─────────────────────────────────────────────────────────────────
    if action == "get_events":
        import acled_data as ac
        country = params.get("country")
        if not country:
            # Return categories if no country
            return ac.get_event_types()
        from datetime import datetime, timedelta
        days = params.get("days", 30)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        result = ac.get_events(
            country=country,
            event_type=params.get("category"),
            start_date=start_date,
            end_date=end_date,
            limit=params.get("limit", 50),
        )
        if isinstance(result, list):
            return {"events": result, "total": len(result)}
        return result

    if action == "get_countries":
        import acled_data as ac
        # Return list of countries with data
        return {"countries": [
            {"name": "Ukraine", "iso": "UKR"}, {"name": "Syria", "iso": "SYR"},
            {"name": "Ethiopia", "iso": "ETH"}, {"name": "Sudan", "iso": "SDN"},
            {"name": "Myanmar", "iso": "MMR"}, {"name": "Afghanistan", "iso": "AFG"},
            {"name": "Somalia", "iso": "SOM"}, {"name": "Nigeria", "iso": "NGA"},
            {"name": "DRC", "iso": "COD"}, {"name": "Mali", "iso": "MLI"},
        ]}

    if action == "get_categories":
        import acled_data as ac
        return ac.get_event_types()

    # ── IMF ───────────────────────────────────────────────────────────────────
    if action == "get_series" and "dataset" in params:
        try:
            import imf_data as imf
            return imf.get_series(
                params.get("dataset", "IFS"),
                params.get("series", ""),
            )
        except Exception as e:
            return {"error": str(e), "dataset": params.get("dataset")}

    # ── OECD ──────────────────────────────────────────────────────────────────
    if action == "get_dataset":
        source_hint = source or params.get("source", "")
        if "oecd" in source_hint or "dataset" in params:
            try:
                import oecd_data as oecd
                return oecd.get_dataset(
                    params.get("dataset", ""),
                    country=params.get("country"),
                    subject=params.get("subject"),
                    measure=params.get("measure"),
                )
            except Exception as e:
                return {"error": str(e)}
        # Generic govdata
        country = params.get("country", "us")
        dataset = params.get("dataset", "")
        return _get_govdata(country, dataset, params)

    # ── Central Banks ─────────────────────────────────────────────────────────
    if action == "get_series" and "bank" in params:
        bank = params.get("bank", "fed").lower()
        series = params.get("series", "policy_rate")
        start = params.get("start", "2020-01-01")
        return _get_central_bank_series(bank, series, start)

    # ── Economic Calendar ─────────────────────────────────────────────────────
    if action == "get_calendar":
        try:
            import economic_calendar as ec
            result = ec.get_upcoming_events(
                limit=params.get("limit", 25),
                country=params.get("country"),
            )
            if isinstance(result, list):
                return {"events": result}
            return result
        except Exception as e:
            return _fallback_calendar(params)

    # ── Maritime ──────────────────────────────────────────────────────────────
    if action == "get_vessel":
        try:
            import marinetraffic_data as mt
            return mt.get_vessel_info(params.get("imo", ""))
        except Exception as e:
            return {"error": str(e), "imo": params.get("imo")}

    if action == "get_vessels_batch":
        try:
            import marinetraffic_data as mt
            results = []
            for imo in params.get("imos", []):
                results.append(mt.get_vessel_info(imo))
            return {"vessels": results, "found_count": len(results)}
        except Exception as e:
            return {"error": str(e)}

    if action == "get_vessels_area":
        try:
            import marinetraffic_data as mt
            return mt.get_vessels_in_area(
                params.get("lat_min"), params.get("lat_max"),
                params.get("lon_min"), params.get("lon_max"),
                vessel_type=params.get("vessel_type"),
            )
        except Exception as e:
            return {"error": str(e)}

    if action == "get_vessel_history":
        try:
            import aisstream_data as ais
            return ais.get_vessel_history(
                params.get("imo", ""),
                days=params.get("days", 7),
            )
        except Exception as e:
            return {"error": str(e)}

    # ── HDX ───────────────────────────────────────────────────────────────────
    if action == "get_datasets":
        try:
            import hdx_data as hdx
            context = params.get("context", "")
            return hdx.get_datasets(context)
        except Exception as e:
            return {"error": str(e), "datasets": []}

    # ── Relationship Map ──────────────────────────────────────────────────────
    if action == "get_relationships":
        try:
            import relationship_map as rm
            return rm.get_relationships(params.get("ticker", ""))
        except Exception as e:
            return {"error": str(e), "nodes": [], "edges": []}

    # ── BLS ───────────────────────────────────────────────────────────────────
    if action == "get_series" and "series_id" in params and source == "bls":
        try:
            import bls_data as bls
            return bls.get_series(params.get("series_id", "LNS14000000"))
        except Exception as e:
            return {"error": str(e)}

    # ── EIA ───────────────────────────────────────────────────────────────────
    if action == "get_data":
        try:
            import eia_data as eia
            return eia.get_data(
                category=params.get("category", "petroleum"),
                series_id=params.get("series_id"),
                start=params.get("start"),
                end=params.get("end"),
            )
        except Exception as e:
            return {"error": str(e)}

    return {"success": False, "error": f"Unknown action: {action}"}


def _get_central_bank_series(bank: str, series: str, start: str):
    """Route to appropriate central bank script."""
    try:
        if bank == "fed":
            import fred_data as fd
            # Map common series names to FRED IDs
            series_map = {
                "policy_rate": "FEDFUNDS",
                "fed_funds": "FEDFUNDS",
                "balance_sheet": "WALCL",
                "inflation": "CPIAUCSL",
            }
            fred_id = series_map.get(series, series.upper())
            return fd.get_series(fred_id, start_date=start)

        elif bank == "ecb":
            import ecb_data as ecb
            return ecb.get_series(series, start_date=start)

        elif bank == "boj":
            import boj_fetcher as boj
            return boj.get_series(series, start_date=start)

        elif bank == "boe":
            import boe_data as boe
            return boe.get_series(series, start_date=start)

        elif bank == "rba":
            import rba_data as rba
            return rba.get_series(series, start_date=start)

        else:
            # Fallback: try FRED for other central banks
            import fred_data as fd
            return fd.get_series(series.upper(), start_date=start)

    except Exception as e:
        return {"error": str(e), "bank": bank, "series": series}


def _get_govdata(country: str, dataset: str, params: dict):
    """Route government data requests."""
    try:
        if country.lower() == "us":
            if "census" in dataset.lower():
                import census_data as cd
                return cd.get_data(dataset, **{k: v for k, v in params.items() if k not in ("country", "dataset")})
            elif "bls" in dataset.lower():
                import bls_data as bls
                return bls.get_series(params.get("series_id", "LNS14000000"))
        elif country.lower() in ("eu", "europe"):
            import eurostat_data as es
            return es.get_dataset(dataset, **{k: v for k, v in params.items() if k not in ("country", "dataset")})
        return {"error": f"No handler for country={country} dataset={dataset}"}
    except Exception as e:
        return {"error": str(e)}


def _fallback_calendar(params: dict):
    """Fallback economic calendar using investing_calendar_data or static data."""
    try:
        import investing_calendar_data as icd
        return icd.get_calendar(limit=params.get("limit", 25))
    except Exception:
        # Return empty calendar if no source available
        return {"events": [], "note": "Economic calendar requires external API key"}


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        main()
    else:
        print(json.dumps({"error": "Use --stdin flag"}))
