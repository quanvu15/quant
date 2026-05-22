"""
API Bridge — Market Data
========================
Nhận JSON payload qua stdin, gọi functions từ yfinance_data.py,
trả về JSON qua stdout.

Đây là adapter layer giữa fincept-api (JSON stdin protocol)
và các scripts gốc (CLI args interface).

Usage: python market_bridge.py --stdin
Payload: {"action": "get_quote", "params": {"symbol": "AAPL"}}
"""
import sys
import json
import os

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    # Read JSON from stdin
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
        # Wrap in standard format if not already
        if isinstance(result, dict) and "success" not in result:
            result = {"success": True, "data": result}
        elif not isinstance(result, dict):
            result = {"success": True, "data": result}
        print(json.dumps(result, default=str))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))


def dispatch(action: str, params: dict):
    import yfinance_data as yf_data

    if action == "get_quote":
        symbol = params.get("symbol", "AAPL").upper()
        return yf_data.get_quote(symbol)

    elif action == "get_batch_quotes":
        symbols = [s.upper() for s in params.get("symbols", [])]
        return yf_data.get_batch_quotes(symbols)

    elif action == "get_history":
        symbol = params.get("symbol", "AAPL").upper()
        start = params.get("start", "2024-01-01")
        end = params.get("end") or None
        interval = params.get("interval", "1d")
        if end:
            return yf_data.get_historical(symbol, start, end, interval)
        else:
            # Use period instead of end date
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start, interval=interval)
            if hist.empty:
                return []
            import pandas as pd
            result = []
            for index, row in hist.iterrows():
                result.append({
                    "symbol": symbol,
                    "timestamp": int(index.timestamp()),
                    "open": round(float(row['Open']), 2),
                    "high": round(float(row['High']), 2),
                    "low": round(float(row['Low']), 2),
                    "close": round(float(row['Close']), 2),
                    "volume": int(row['Volume']) if not pd.isna(row['Volume']) else 0,
                })
            return result

    elif action == "get_info":
        symbol = params.get("symbol", "AAPL").upper()
        return yf_data.get_info(symbol)

    elif action == "get_financials":
        symbol = params.get("symbol", "AAPL").upper()
        return yf_data.get_financials(symbol)

    elif action == "search_symbols":
        query = params.get("query", "")
        limit = params.get("limit", 10)
        # yfinance doesn't have search — use basic lookup
        import yfinance as yf
        try:
            ticker = yf.Ticker(query.upper())
            info = ticker.info
            if info.get("symbol"):
                return {"results": [{"symbol": info["symbol"], "name": info.get("longName", ""), "exchange": info.get("exchange", "")}]}
        except Exception:
            pass
        return {"results": []}

    elif action == "get_sectors":
        # Return sector ETF performance
        sector_etfs = {
            "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
            "Energy": "XLE", "Consumer Discretionary": "XLY",
            "Industrials": "XLI", "Materials": "XLB",
            "Utilities": "XLU", "Real Estate": "XLRE",
            "Communication Services": "XLC", "Consumer Staples": "XLP"
        }
        import yfinance as yf
        import pandas as pd
        sectors = []
        tickers = list(sector_etfs.values())
        try:
            data = yf.download(tickers, period="1mo", progress=False, auto_adjust=True)
            for name, etf in sector_etfs.items():
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        closes = data["Close"][etf].dropna()
                    else:
                        closes = data["Close"].dropna()
                    if len(closes) >= 2:
                        perf_1d = (closes.iloc[-1] / closes.iloc[-2] - 1) * 100
                        perf_1w = (closes.iloc[-1] / closes.iloc[-5] - 1) * 100 if len(closes) >= 5 else 0
                        perf_1m = (closes.iloc[-1] / closes.iloc[0] - 1) * 100
                        sectors.append({
                            "name": name, "etf": etf,
                            "performance_1d": round(float(perf_1d), 2),
                            "performance_1w": round(float(perf_1w), 2),
                            "performance_1m": round(float(perf_1m), 2),
                        })
                except Exception:
                    sectors.append({"name": name, "etf": etf, "performance_1d": 0, "performance_1w": 0, "performance_1m": 0})
        except Exception as e:
            return {"sectors": [], "error": str(e)}
        return {"sectors": sectors}

    else:
        return {"success": False, "error": f"Unknown action: {action}"}


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        main()
    else:
        print(json.dumps({"error": "Use --stdin flag"}))
