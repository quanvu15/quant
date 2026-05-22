"""
API Bridge — AI Quant Lab (Phase 5)
=====================================
Nhận JSON payload qua stdin, dispatch đến các qlib scripts.
Tất cả qlib scripts đều cần qlib data được pre-download.
Bridge này wrap và chuẩn hóa output.
"""
import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai_quant_lab"))


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
        elif not isinstance(result, dict):
            result = {"success": True, "data": result}
        print(json.dumps(result, default=str))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))


def dispatch(action: str, params: dict):
    if action == "run_backtest":
        return _run_backtest(params)
    elif action == "train_model":
        return _train_model(params)
    elif action == "predict":
        return _predict(params)
    elif action == "list_models":
        return _list_models()
    elif action == "get_model":
        return _get_model(params.get("model_id", ""))
    elif action == "discover_factors":
        return _discover_factors(params)
    elif action == "evaluate_factor":
        return _evaluate_factor(params)
    elif action == "optimize_portfolio":
        return _optimize_portfolio(params)
    elif action == "train_rl":
        return _train_rl(params)
    elif action == "rl_backtest":
        return _rl_backtest(params)
    elif action == "generate_tearsheet":
        return _generate_tearsheet(params)
    elif action == "factor_attribution":
        return _factor_attribution(params)
    else:
        return {"success": False, "error": f"Unknown action: {action}"}


def _run_backtest(params: dict):
    """Run backtest via qlib_advanced_backtest.py."""
    try:
        from ai_quant_lab import qlib_advanced_backtest as qbt
        strategy = params.get("strategy", {})
        universe = params.get("universe", {})
        start_date = params.get("start_date", "2020-01-01")
        end_date = params.get("end_date", "2024-12-31")
        initial_capital = params.get("initial_capital", 1_000_000)
        benchmark = params.get("benchmark", "SPY")

        result = qbt.run_backtest(
            strategy=strategy,
            universe=universe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            benchmark=benchmark,
        )
        return result
    except ImportError:
        return _simple_backtest_fallback(params)
    except Exception as e:
        return {"error": str(e)}


def _simple_backtest_fallback(params: dict):
    """Simple backtest fallback using yfinance + pandas."""
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np

        universe = params.get("universe", {})
        symbols = universe.get("symbols", ["SPY"])
        start_date = params.get("start_date", "2020-01-01")
        end_date = params.get("end_date", "2024-12-31")
        initial_capital = params.get("initial_capital", 1_000_000)

        # Equal weight portfolio
        data = yf.download(symbols, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if data.empty:
            return {"error": "No data available"}

        if len(symbols) == 1:
            prices = data["Close"].to_frame(symbols[0])
        else:
            prices = data["Close"]

        # Equal weight returns
        returns = prices.pct_change().dropna()
        portfolio_returns = returns.mean(axis=1)

        # Equity curve
        equity = (1 + portfolio_returns).cumprod() * initial_capital
        equity_curve = [
            {"date": str(d.date()), "portfolio_value": round(float(v), 2)}
            for d, v in equity.items()
        ]

        # Metrics
        total_return = float((equity.iloc[-1] / initial_capital) - 1)
        ann_return = float((1 + total_return) ** (252 / len(returns)) - 1)
        volatility = float(portfolio_returns.std() * np.sqrt(252))
        sharpe = ann_return / volatility if volatility > 0 else 0
        max_dd = float((equity / equity.cummax() - 1).min())

        return {
            "success": True,
            "equity_curve": equity_curve[-100:],  # last 100 points
            "metrics": {
                "total_return": round(total_return, 4),
                "annualized_return": round(ann_return, 4),
                "volatility": round(volatility, 4),
                "sharpe_ratio": round(sharpe, 4),
                "max_drawdown": round(max_dd, 4),
            },
            "note": "Simple equal-weight backtest (Qlib not available)",
        }
    except Exception as e:
        return {"error": str(e)}


def _train_model(params: dict):
    """Train ML model via qlib_service.py."""
    try:
        from ai_quant_lab import qlib_service as qs
        return qs.train_model(
            model_type=params.get("model_type", "lightgbm"),
            universe=params.get("universe", {}),
            features=params.get("features", "Alpha158"),
            start_date=params.get("start_date", "2018-01-01"),
            end_date=params.get("end_date", "2023-12-31"),
            hyperparams=params.get("hyperparams", {}),
        )
    except ImportError:
        return {"error": "Qlib not installed. Install with: pip install pyqlib", "success": False}
    except Exception as e:
        return {"error": str(e)}


def _predict(params: dict):
    """Run prediction with trained model."""
    try:
        from ai_quant_lab import qlib_service as qs
        return qs.predict(
            model_id=params.get("model_id", ""),
            symbols=params.get("symbols", []),
            date=params.get("date"),
        )
    except ImportError:
        return {"error": "Qlib not installed", "predictions": []}
    except Exception as e:
        return {"error": str(e)}


def _list_models():
    """List trained models from disk."""
    import glob
    models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "models")
    models = []
    for path in glob.glob(os.path.join(models_dir, "*/metadata.json")):
        try:
            with open(path) as f:
                meta = json.load(f)
                models.append(meta)
        except Exception:
            pass
    return {"models": models, "count": len(models)}


def _get_model(model_id: str):
    """Get model metadata."""
    models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "models", model_id)
    meta_path = os.path.join(models_dir, "metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            return json.load(f)
    return {"error": f"Model {model_id} not found"}


def _discover_factors(params: dict):
    """Factor discovery via qlib_feature_engineering.py."""
    try:
        from ai_quant_lab import qlib_feature_engineering as qfe
        return qfe.discover_factors(
            universe=params.get("universe", {}),
            start_date=params.get("start_date", "2018-01-01"),
            end_date=params.get("end_date", "2023-12-31"),
            method=params.get("method", "alpha158"),
        )
    except ImportError:
        return {"error": "Qlib not installed", "factors": []}
    except Exception as e:
        return {"error": str(e)}


def _evaluate_factor(params: dict):
    """Factor evaluation via qlib_evaluation.py."""
    try:
        from ai_quant_lab import qlib_evaluation as qev
        return qev.evaluate_factor(
            factor_data=params.get("factor_data", []),
            universe=params.get("universe", {}),
            start_date=params.get("start_date", "2018-01-01"),
            end_date=params.get("end_date", "2023-12-31"),
        )
    except ImportError:
        return {"error": "Qlib not installed", "ic_mean": 0}
    except Exception as e:
        return {"error": str(e)}


def _optimize_portfolio(params: dict):
    """Portfolio optimization via qlib_portfolio_opt.py."""
    try:
        from ai_quant_lab import qlib_portfolio_opt as qpo
        return qpo.optimize(
            signals=params.get("signals", []),
            method=params.get("method", "mean_variance"),
            constraints=params.get("constraints", {}),
            risk_model=params.get("risk_model", "sample"),
        )
    except ImportError:
        # Fallback to optimize_portfolio_weights.py
        try:
            import optimize_portfolio_weights as opw
            symbols = [s["symbol"] for s in params.get("signals", [])]
            if not symbols:
                return {"error": "No symbols provided"}
            return opw.optimize_portfolio(symbols=symbols, method="max_sharpe")
        except Exception as e2:
            return {"error": str(e2)}
    except Exception as e:
        return {"error": str(e)}


def _train_rl(params: dict):
    """RL training via qlib_rl.py."""
    try:
        from ai_quant_lab import qlib_rl as qrl
        return qrl.train(
            algorithm=params.get("algorithm", "PPO"),
            environment=params.get("environment", {}),
            training=params.get("training", {}),
        )
    except ImportError:
        return {"error": "Qlib/stable-baselines3 not installed", "success": False}
    except Exception as e:
        return {"error": str(e)}


def _rl_backtest(params: dict):
    """RL model backtest."""
    try:
        from ai_quant_lab import qlib_rl as qrl
        return qrl.backtest(
            model_id=params.get("model_id", ""),
            symbols=params.get("symbols", []),
            start_date=params.get("start_date", "2023-01-01"),
            end_date=params.get("end_date", "2024-12-31"),
        )
    except ImportError:
        return {"error": "Qlib not installed"}
    except Exception as e:
        return {"error": str(e)}


def _generate_tearsheet(params: dict):
    """Generate performance tearsheet via qlib_reporting.py."""
    try:
        from ai_quant_lab import qlib_reporting as qrep
        result = qrep.generate_tearsheet(
            returns=params.get("returns", []),
            benchmark_returns=params.get("benchmark_returns"),
            title=params.get("title", "Portfolio Tearsheet"),
        )
        return result
    except ImportError:
        # Fallback: compute basic metrics
        returns_data = params.get("returns", [])
        if not returns_data:
            return {"error": "No returns data provided"}
        try:
            import numpy as np
            rets = [r.get("return", 0) for r in returns_data]
            arr = np.array(rets)
            total = float((1 + arr).prod() - 1)
            ann = float((1 + total) ** (252 / len(arr)) - 1) if len(arr) > 0 else 0
            vol = float(arr.std() * np.sqrt(252))
            sharpe = ann / vol if vol > 0 else 0
            return {
                "metrics": {
                    "total_return": round(total, 4),
                    "annualized_return": round(ann, 4),
                    "volatility": round(vol, 4),
                    "sharpe_ratio": round(sharpe, 4),
                },
                "note": "Basic metrics (quantstats tearsheet not available)",
            }
        except Exception as e2:
            return {"error": str(e2)}
    except Exception as e:
        return {"error": str(e)}


def _factor_attribution(params: dict):
    """Factor attribution analysis."""
    try:
        from ai_quant_lab import qlib_reporting as qrep
        return qrep.factor_attribution(
            portfolio_returns=params.get("portfolio_returns", []),
            factor_returns=params.get("factor_returns", {}),
        )
    except ImportError:
        # Simple OLS attribution fallback
        try:
            import numpy as np
            port_rets = [r.get("return", 0) for r in params.get("portfolio_returns", [])]
            factor_rets = params.get("factor_returns", {})
            if not port_rets or not factor_rets:
                return {"attribution": [], "r_squared": 0}

            y = np.array(port_rets)
            attribution = []
            for factor_name, factor_data in factor_rets.items():
                x = np.array([r.get("return", 0) if isinstance(r, dict) else r for r in factor_data])
                min_len = min(len(y), len(x))
                if min_len < 2:
                    continue
                corr = float(np.corrcoef(y[:min_len], x[:min_len])[0, 1])
                attribution.append({
                    "factor": factor_name,
                    "contribution": round(corr, 4),
                    "t_stat": round(corr * np.sqrt(min_len - 2) / np.sqrt(1 - corr**2 + 1e-10), 4),
                })
            return {"attribution": attribution, "r_squared": 0, "note": "Correlation-based attribution"}
        except Exception as e2:
            return {"error": str(e2)}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        main()
    else:
        print(json.dumps({"error": "Use --stdin flag"}))
