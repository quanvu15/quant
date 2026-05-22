"""
API Bridge — QuantLib / Derivatives Pricing
============================================
Nhận JSON payload qua stdin, gọi functions từ derivatives_pricing.py trực tiếp.
"""
import sys
import json
import os
import math

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
        elif isinstance(result, dict) and "error" in result:
            result = {"success": False, **result}
        elif not isinstance(result, dict):
            result = {"success": True, "data": result}
        print(json.dumps(result, default=str))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))


def dispatch(action: str, params: dict):
    import derivatives_pricing as dp

    if action == "option_price":
        S = params["S"]; K = params["K"]; T = params["T"]
        r = params["r"]; sigma = params["sigma"]
        q = params.get("q", 0.0)
        option_type = params.get("option_type", "call")
        model = params.get("model", "bsm")

        price = dp.black_scholes_price(S, K, T, r, sigma, q, option_type)
        greeks = dp.black_scholes_greeks(S, K, T, r, sigma, q, option_type)
        return {"price": round(price, 4), "model": model, **greeks}

    elif action == "compute_greeks":
        S = params["S"]; K = params["K"]; T = params["T"]
        r = params["r"]; sigma = params["sigma"]
        q = params.get("q", 0.0)
        option_type = params.get("option_type", "call")

        price = dp.black_scholes_price(S, K, T, r, sigma, q, option_type)
        greeks = dp.black_scholes_greeks(S, K, T, r, sigma, q, option_type)
        return {"price": round(price, 4), **greeks}

    elif action == "compute_iv":
        S = params["S"]; K = params["K"]; T = params["T"]
        r = params["r"]; market_price = params["market_price"]
        q = params.get("q", 0.0)
        option_type = params.get("option_type", "call")

        iv = dp.implied_volatility(S, K, T, r, market_price, q, option_type)
        return {"implied_vol": round(iv, 6), "converged": iv > 0}

    elif action == "fx_option":
        S = params["S"]; K = params["K"]; T = params["T"]
        r_d = params["r_d"]; r_f = params["r_f"]; sigma = params["sigma"]
        option_type = params.get("option_type", "call")

        price = dp.garman_kohlhagen_price(S, K, T, r_d, r_f, sigma, option_type)
        return {"price": round(price, 4)}

    elif action == "bond_price":
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        maturity_years = params["maturity_years"]
        maturity_date = (datetime.now() + timedelta(days=int(maturity_years * 365))).strftime("%Y-%m-%d")

        result = dp.bond_price_from_ytm(
            issue_date=today,
            settlement_date=today,
            maturity_date=maturity_date,
            coupon_rate=params["coupon_rate"] * 100,  # convert to percentage
            ytm=params["ytm"] * 100,
            freq=params.get("frequency", 2)
        )
        # Normalize to face_value
        face = params.get("face_value", 1000)
        if "clean_price" in result:
            result["clean_price"] = round(result["clean_price"] * face / 100, 2)
            result["dirty_price"] = round(result["dirty_price"] * face / 100, 2)
            result["accrued_interest"] = round(result["accrued_interest"] * face / 100, 2)
        return result

    elif action == "bond_ytm":
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        maturity_years = params["maturity_years"]
        maturity_date = (datetime.now() + timedelta(days=int(maturity_years * 365))).strftime("%Y-%m-%d")
        face = params.get("face_value", 1000)
        clean_price_pct = params["clean_price"] / face * 100

        result = dp.bond_ytm_from_price(
            issue_date=today,
            settlement_date=today,
            maturity_date=maturity_date,
            coupon_rate=params["coupon_rate"] * 100,
            clean_price=clean_price_pct,
            freq=params.get("frequency", 2)
        )
        if "ytm" in result:
            result["ytm"] = round(result["ytm"] / 100, 6)  # back to decimal
        return result

    elif action == "irs_valuation":
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        tenor = params["tenor_years"]
        maturity = (datetime.now() + timedelta(days=int(tenor * 365))).strftime("%Y-%m-%d")

        return dp.swap_value(
            effective_date=today,
            maturity_date=maturity,
            fixed_rate=params["fixed_rate"] * 100,
            freq=params.get("payment_freq", 2),
            notional=params["notional"],
            discount_rate=params.get("discount_rate", 5.0)
        )

    elif action == "cds_valuation":
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        tenor = params["tenor_years"]
        maturity = (datetime.now() + timedelta(days=int(tenor * 365))).strftime("%Y-%m-%d")

        return dp.cds_value(
            valuation_date=today,
            maturity_date=maturity,
            recovery_rate=params.get("recovery_rate", 0.4) * 100,
            notional=params["notional"],
            spread_bps=params["spread_bps"]
        )

    elif action == "compute_var":
        returns = params["returns"]
        confidence = params.get("confidence_level", 0.95)
        method = params.get("method", "historical")

        import numpy as np
        r = np.array(returns)
        if method == "historical":
            var = float(np.percentile(r, (1 - confidence) * 100))
            cvar = float(np.mean(r[r <= var]))
        elif method == "parametric":
            from scipy.stats import norm
            mu, sigma = float(np.mean(r)), float(np.std(r))
            var = float(norm.ppf(1 - confidence, mu, sigma))
            cvar = float(mu - sigma * norm.pdf(norm.ppf(confidence)) / (1 - confidence))
        else:  # monte_carlo
            np.random.seed(42)
            mu, sigma = float(np.mean(r)), float(np.std(r))
            sim = np.random.normal(mu, sigma, 10000)
            var = float(np.percentile(sim, (1 - confidence) * 100))
            cvar = float(np.mean(sim[sim <= var]))

        return {
            "var": round(var, 6),
            "cvar": round(cvar, 6),
            "confidence_level": confidence,
            "method": method
        }

    elif action == "batch_greeks":
        contracts = params.get("contracts", [])
        results = []
        for c in contracts:
            try:
                S = c["S"]; K = c["K"]; T = c["T"]; r = c["r"]; sigma = c["sigma"]
                q = c.get("q", 0.0); otype = c.get("option_type", "call")
                price = dp.black_scholes_price(S, K, T, r, sigma, q, otype)
                greeks = dp.black_scholes_greeks(S, K, T, r, sigma, q, otype)
                results.append({"token": c.get("token"), "price": round(price, 4), **greeks})
            except Exception as e:
                results.append({"token": c.get("token"), "error": str(e)})
        return {"results": results}

    elif action == "gbm_simulation":
        import numpy as np
        S0 = params["S0"]; mu = params["mu"]; sigma = params["sigma"]
        T = params["T"]; n_paths = min(params.get("n_paths", 100), 1000)
        n_steps = min(params.get("n_steps", 252), 252)
        seed = params.get("seed")
        if seed:
            np.random.seed(seed)

        dt = T / n_steps
        paths = np.zeros((n_paths, n_steps + 1))
        paths[:, 0] = S0
        for t in range(1, n_steps + 1):
            z = np.random.standard_normal(n_paths)
            paths[:, t] = paths[:, t-1] * np.exp((mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z)

        final = paths[:, -1]
        return {
            "paths": paths.tolist(),
            "statistics": {
                "mean_final": round(float(np.mean(final)), 4),
                "std_final": round(float(np.std(final)), 4),
                "percentile_5": round(float(np.percentile(final, 5)), 4),
                "percentile_95": round(float(np.percentile(final, 95)), 4),
            }
        }

    elif action == "stress_test":
        portfolio = params.get("portfolio", [])
        scenarios = params.get("scenarios", [])
        results = []
        for scenario in scenarios:
            shocks = scenario.get("shocks", {})
            equity_shock = shocks.get("equity", 0)
            pnl = sum(h.get("weight", 0) * equity_shock for h in portfolio)
            results.append({
                "scenario": scenario.get("name", "Unknown"),
                "portfolio_pnl": round(pnl, 4),
                "pct_change": round(pnl * 100, 2)
            })
        return {"results": results}

    elif action == "credit_risk":
        exposure = params["exposure"]
        pd_val = params["pd"]
        lgd = params["lgd"]
        ead = params.get("ead", exposure)
        el = pd_val * lgd * ead
        ul = math.sqrt(pd_val * (1 - pd_val)) * lgd * ead
        return {
            "expected_loss": round(el, 2),
            "unexpected_loss": round(ul, 2),
            "cva": round(el * 0.5, 2),
            "rwa": round(ead * 1.06, 2)
        }

    else:
        return {"success": False, "error": f"Unknown action: {action}"}


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        main()
    else:
        print(json.dumps({"error": "Use --stdin flag"}))
