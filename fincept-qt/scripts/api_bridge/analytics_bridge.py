"""
API Bridge — Portfolio Analytics & Technical Analysis (Phase 2)
===============================================================
Nhận JSON payload qua stdin, dispatch đến:
- optimize_portfolio_weights.py  (portfolio optimization)
- quantstats_analysis.py         (portfolio metrics, backtest)
- compute_technicals.py          (technical indicators)
- equity_talipp.py               (talipp indicators)
- fetch_company_news.py          (news)
- relationship_map.py            (corporate relationships)
- fii_dii_scraper.py             (FII/DII data)
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

    try:
        result = dispatch(action, params)
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


def dispatch(action: str, params: dict):
    # ── Portfolio Optimization ────────────────────────────────────────────────
    if action == "optimize":
        return _portfolio_optimize(params)

    # ── Portfolio Metrics / Backtest ──────────────────────────────────────────
    if action in ("compute_metrics", "backtest", "compute_var"):
        return _portfolio_quantstats(action, params)

    # ── Technical Indicators ──────────────────────────────────────────────────
    if action == "compute_indicators":
        return _compute_technicals(params)

    if action == "compute_signals":
        return _compute_signals(params)

    # ── News ──────────────────────────────────────────────────────────────────
    if action == "get_news":
        return _get_news(params)

    # ── Relationships ─────────────────────────────────────────────────────────
    if action == "get_relationships":
        try:
            import relationship_map as rm
            return rm.get_relationships(params.get("ticker", ""))
        except Exception as e:
            return {"error": str(e), "nodes": [], "edges": []}

    # ── FII/DII ───────────────────────────────────────────────────────────────
    if action == "get_fii_dii":
        try:
            import fii_dii_scraper as fds
            return fds.get_fii_dii_data(days=params.get("days", 30))
        except Exception as e:
            return {"error": str(e), "data": []}

    return {"success": False, "error": f"Unknown action: {action}"}


def _portfolio_optimize(params: dict):
    """
    optimize_portfolio_weights.py reads JSON from stdin with schema:
    {"symbols": [...], "weights": [...], "method": "max_sharpe"}
    We need to translate from our {"action":"optimize","params":{...}} envelope.
    """
    try:
        import optimize_portfolio_weights as opw

        symbols = params.get("symbols", [])
        method = params.get("method", "max_sharpe")
        constraints = params.get("constraints", {})
        start_date = params.get("start_date")
        end_date = params.get("end_date")

        # Map method names
        method_map = {
            "mean_variance": "max_sharpe",
            "min_variance": "min_volatility",
            "risk_parity": "risk_parity",
            "black_litterman": "max_sharpe",  # fallback
        }
        mapped_method = method_map.get(method, method)

        # Call the optimization function directly
        result = opw.optimize_portfolio(
            symbols=symbols,
            method=mapped_method,
            start_date=start_date,
            end_date=end_date,
            constraints=constraints,
        )
        return result
    except AttributeError:
        # Try alternative function name
        try:
            import optimize_portfolio_weights as opw
            # Feed via stdin protocol the script supports
            import subprocess
            import sys as _sys
            payload = {
                "symbols": params.get("symbols", []),
                "method": params.get("method", "max_sharpe"),
            }
            result = subprocess.run(
                [_sys.executable, opw.__file__],
                input=json.dumps(payload).encode(),
                capture_output=True,
                timeout=120,
            )
            if result.returncode == 0:
                return json.loads(result.stdout.decode())
            return {"error": result.stderr.decode()[:500]}
        except Exception as e2:
            return {"error": str(e2)}
    except Exception as e:
        return {"error": str(e)}


def _portfolio_quantstats(action: str, params: dict):
    """Wrap quantstats_analysis.py for metrics, backtest, VaR."""
    try:
        import quantstats_analysis as qs

        holdings = params.get("holdings", [])
        start_date = params.get("start_date", "2020-01-01")
        end_date = params.get("end_date", "2024-12-31")
        benchmark = params.get("benchmark", "SPY")

        if action == "compute_metrics":
            return qs.compute_portfolio_metrics(
                holdings=holdings,
                start_date=start_date,
                end_date=end_date,
                benchmark=benchmark,
            )
        elif action == "backtest":
            return qs.backtest_portfolio(
                holdings=holdings,
                start_date=start_date,
                end_date=end_date,
                rebalance_freq=params.get("rebalance_freq", "monthly"),
            )
        elif action == "compute_var":
            return qs.compute_var(
                holdings=holdings,
                confidence_level=params.get("confidence_level", 0.95),
                method=params.get("method", "historical"),
            )
    except AttributeError:
        # quantstats_analysis.py may have different function names
        return _quantstats_via_subprocess(action, params)
    except Exception as e:
        return {"error": str(e)}


def _quantstats_via_subprocess(action: str, params: dict):
    """Fallback: run quantstats_analysis.py via subprocess with JSON stdin."""
    import subprocess
    import sys as _sys
    import importlib.util

    spec = importlib.util.find_spec("quantstats_analysis")
    if spec is None:
        return {"error": "quantstats_analysis module not found"}

    payload = {"action": action, "params": params}
    try:
        result = subprocess.run(
            [_sys.executable, spec.origin, "--stdin"],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout.decode())
        return {"error": result.stderr.decode()[:500] or "No output"}
    except Exception as e:
        return {"error": str(e)}


def _compute_technicals(params: dict):
    """
    compute_technicals.py expects raw OHLCV array.
    We fetch the data first, then compute indicators.
    """
    symbol = params.get("symbol", "AAPL")
    period = params.get("period", "1y")
    interval = params.get("interval", "1d")
    indicators = params.get("indicators", ["RSI", "MACD", "BB", "EMA20", "SMA50"])

    try:
        # Step 1: Fetch OHLCV data
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            return {"error": f"No data for {symbol}"}

        # Step 2: Convert to list of dicts
        ohlcv = []
        for idx, row in hist.iterrows():
            ohlcv.append({
                "timestamp": int(idx.timestamp()),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,
            })

        # Step 3: Compute technicals
        import compute_technicals as ct
        result_json = ct.compute_all_technicals(json.dumps(ohlcv))
        result = json.loads(result_json)

        # Step 4: Filter to requested indicators
        if result.get("success") and indicators:
            data = result.get("data", [])
            # Keep only requested indicator columns + OHLCV
            base_cols = {"timestamp", "open", "high", "low", "close", "volume"}
            indicator_map = {
                "RSI": ["rsi"],
                "MACD": ["macd", "macd_signal", "macd_diff"],
                "BB": ["bb_bbm", "bb_bbh", "bb_bbl", "bb_bbw"],
                "EMA20": ["ema_20"],
                "SMA50": ["sma_50"],
                "EMA12": ["ema_12"],
                "SMA20": ["sma_20"],
                "ATR": ["atr"],
                "ADX": ["adx"],
                "STOCH": ["stoch", "stoch_signal"],
                "OBV": ["obv"],
                "VWAP": ["vwap"],
            }
            keep_cols = set(base_cols)
            for ind in indicators:
                keep_cols.update(indicator_map.get(ind.upper(), [ind.lower()]))

            filtered = []
            for row in data:
                filtered.append({k: v for k, v in row.items() if k in keep_cols})
            result["data"] = filtered

        return result

    except Exception as e:
        return {"error": str(e), "symbol": symbol}


def _compute_signals(params: dict):
    """Generate trading signals from technical analysis."""
    symbol = params.get("symbol", "AAPL")
    strategy = params.get("strategy", "momentum")

    try:
        import yfinance as yf
        import pandas as pd

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="6mo", interval="1d")

        if hist.empty:
            return {"error": f"No data for {symbol}"}

        close = hist["Close"]
        signal = "hold"
        confidence = 0.5
        reasoning = ""

        if strategy == "momentum":
            sma20 = close.rolling(20).mean().iloc[-1]
            sma50 = close.rolling(50).mean().iloc[-1]
            current = close.iloc[-1]
            if current > sma20 > sma50:
                signal = "buy"
                confidence = 0.7
                reasoning = f"Price ${current:.2f} above SMA20 ${sma20:.2f} and SMA50 ${sma50:.2f}"
            elif current < sma20 < sma50:
                signal = "sell"
                confidence = 0.7
                reasoning = f"Price ${current:.2f} below SMA20 ${sma20:.2f} and SMA50 ${sma50:.2f}"
            else:
                reasoning = "Mixed momentum signals"

        elif strategy == "mean_reversion":
            sma20 = close.rolling(20).mean().iloc[-1]
            std20 = close.rolling(20).std().iloc[-1]
            current = close.iloc[-1]
            z_score = (current - sma20) / std20 if std20 > 0 else 0
            if z_score < -2:
                signal = "buy"
                confidence = 0.65
                reasoning = f"Z-score {z_score:.2f} — oversold"
            elif z_score > 2:
                signal = "sell"
                confidence = 0.65
                reasoning = f"Z-score {z_score:.2f} — overbought"
            else:
                reasoning = f"Z-score {z_score:.2f} — neutral"

        elif strategy == "breakout":
            high52 = close.rolling(252).max().iloc[-1]
            low52 = close.rolling(252).min().iloc[-1]
            current = close.iloc[-1]
            if current >= high52 * 0.98:
                signal = "buy"
                confidence = 0.75
                reasoning = f"Near 52-week high ${high52:.2f}"
            elif current <= low52 * 1.02:
                signal = "sell"
                confidence = 0.75
                reasoning = f"Near 52-week low ${low52:.2f}"
            else:
                reasoning = "No breakout signal"

        return {
            "symbol": symbol,
            "signal": signal,
            "confidence": confidence,
            "reasoning": reasoning,
            "strategy": strategy,
        }

    except Exception as e:
        return {"error": str(e)}


def _get_news(params: dict):
    """Fetch company news."""
    symbol = params.get("symbol", "AAPL")
    limit = params.get("limit", 20)
    source = params.get("source", "yfinance")

    try:
        if source == "finnhub":
            import finnhub_data as fh
            return fh.get_company_news(symbol, limit=limit)
        else:
            # yfinance news
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            news = ticker.news or []
            articles = []
            for item in news[:limit]:
                articles.append({
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "url": item.get("link", ""),
                    "published_at": item.get("providerPublishTime", 0),
                    "source": item.get("publisher", ""),
                    "sentiment": "neutral",
                })
            return {"articles": articles, "symbol": symbol, "count": len(articles)}
    except Exception as e:
        return {"error": str(e), "articles": []}


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        main()
    else:
        print(json.dumps({"error": "Use --stdin flag"}))
