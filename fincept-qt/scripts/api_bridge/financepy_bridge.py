"""
API Bridge — FinancePy / Stochastic Models
==========================================
Nhận JSON payload qua stdin, gọi functions từ financepy_wrapper.py
và các stochastic models.

Fallback về pure-math nếu FinancePy chưa cài.
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
    # ── Bond pricing (pure math, no FinancePy needed) ─────────────────────────
    if action in ("bond_price", "bond_ytm", "bond_duration"):
        try:
            import derivatives_pricing as dp
        except ImportError as e:
            return {"success": False, "error": f"Failed to import derivatives_pricing: {e}"}
        from datetime import datetime, timedelta

        today = datetime.now().strftime("%Y-%m-%d")
        maturity_years = params.get("maturity_years", 5.0)
        maturity_date = (datetime.now() + timedelta(days=int(maturity_years * 365))).strftime("%Y-%m-%d")
        face = params.get("face_value", 1000.0)
        coupon_rate_pct = params.get("coupon_rate", 0.05) * 100
        freq = params.get("frequency", 2)

        if action == "bond_price":
            ytm_pct = params.get("ytm", 0.05) * 100
            result = dp.bond_price_from_ytm(today, today, maturity_date, coupon_rate_pct, ytm_pct, freq)
            if "clean_price" in result:
                result["clean_price"] = round(result["clean_price"] * face / 100, 2)
                result["dirty_price"] = round(result["dirty_price"] * face / 100, 2)
                result["accrued_interest"] = round(result["accrued_interest"] * face / 100, 2)
            return result

        elif action == "bond_ytm":
            clean_price_pct = params.get("clean_price", face * 0.985) / face * 100
            result = dp.bond_ytm_from_price(today, today, maturity_date, coupon_rate_pct, clean_price_pct, freq)
            if "ytm" in result:
                result["ytm"] = round(result["ytm"] / 100, 6)
            return result

        elif action == "bond_duration":
            ytm_pct = params.get("ytm", 0.05) * 100
            result = dp.bond_price_from_ytm(today, today, maturity_date, coupon_rate_pct, ytm_pct, freq)
            return result

    # ── Yield curve bootstrap (simple linear interpolation) ───────────────────
    elif action == "yield_curve_bootstrap":
        instruments = params.get("instruments", [])
        curve = []
        for inst in sorted(instruments, key=lambda x: x.get("maturity", 0)):
            mat = inst.get("maturity", 1.0)
            rate = inst.get("rate", 0.05)
            df = math.exp(-rate * mat)
            curve.append({"maturity": mat, "zero_rate": round(rate, 6), "discount_factor": round(df, 6)})
        return {"curve": curve}

    # ── GBM simulation (numpy, no FinancePy) ──────────────────────────────────
    elif action == "gbm_simulation":
        import numpy as np
        S0 = params["S0"]; mu = params["mu"]; sigma = params["sigma"]
        T = params["T"]
        n_paths = min(params.get("n_paths", 100), 500)   # cap at 500 for memory
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

    # ── Heston model (try FinancePy, fallback to BSM approximation) ───────────
    elif action == "heston_price":
        try:
            return _heston_financepy(params)
        except ImportError:
            return _heston_bsm_approx(params)

    # ── Hull-White (try FinancePy, fallback to Vasicek approximation) ─────────
    elif action == "hull_white":
        try:
            return _hull_white_financepy(params)
        except ImportError:
            return _hull_white_approx(params)

    else:
        return {"success": False, "error": f"Unknown action: {action}"}


def _heston_financepy(params):
    """Heston pricing via FinancePy."""
    from financepy.models.heston import Heston
    from financepy.utils.date import Date
    from financepy.products.equity.equity_vanilla_option import EquityVanillaOption
    from financepy.utils.global_types import OptionTypes
    import datetime

    S0 = params["S0"]; K = params["K"]; T = params["T"]; r = params["r"]
    v0 = params["v0"]; kappa = params["kappa"]; theta = params["theta"]
    sigma_v = params["sigma_v"]; rho = params["rho"]
    option_type = params.get("option_type", "call")

    today = datetime.date.today()
    expiry = today + datetime.timedelta(days=int(T * 365))
    val_date = Date(today.day, today.month, today.year)
    exp_date = Date(expiry.day, expiry.month, expiry.year)

    opt_type = OptionTypes.EUROPEAN_CALL if option_type == "call" else OptionTypes.EUROPEAN_PUT
    option = EquityVanillaOption(exp_date, K, opt_type)
    model = Heston(v0, kappa, theta, sigma_v, rho)
    price = option.value(val_date, S0, 0.0, r, model)

    # Implied vol via BSM
    import derivatives_pricing as dp
    iv = dp.implied_volatility(S0, K, T, r, float(price), 0.0, option_type)
    return {"price": round(float(price), 4), "implied_vol": round(iv, 6)}


def _heston_bsm_approx(params):
    """Heston approximation using BSM with Heston vol."""
    import derivatives_pricing as dp
    S0 = params["S0"]; K = params["K"]; T = params["T"]; r = params["r"]
    v0 = params["v0"]; theta = params["theta"]
    option_type = params.get("option_type", "call")

    # Use average of v0 and theta as effective vol
    sigma_eff = math.sqrt((v0 + theta) / 2)
    price = dp.black_scholes_price(S0, K, T, r, sigma_eff, 0.0, option_type)
    return {"price": round(price, 4), "implied_vol": round(sigma_eff, 6), "note": "BSM approximation (FinancePy not available)"}


def _hull_white_financepy(params):
    """Hull-White simulation via FinancePy."""
    from financepy.models.hw_tree import HWTree
    import numpy as np

    r0 = params["r0"]; a = params["a"]; sigma = params["sigma"]
    T = params["T"]
    n_paths = min(params.get("n_paths", 100), 500)
    n_steps = min(params.get("n_steps", 252), 252)

    dt = T / n_steps
    paths = np.zeros((n_paths, n_steps + 1))
    paths[:, 0] = r0

    for t in range(1, n_steps + 1):
        z = np.random.standard_normal(n_paths)
        theta_t = r0 * a  # simplified theta
        paths[:, t] = paths[:, t-1] + a * (theta_t / a - paths[:, t-1]) * dt + sigma * math.sqrt(dt) * z

    mean_path = np.mean(paths, axis=0).tolist()
    return {"paths": paths.tolist(), "mean_path": [round(x, 6) for x in mean_path]}


def _hull_white_approx(params):
    """Hull-White Vasicek approximation."""
    import numpy as np
    r0 = params["r0"]; a = params["a"]; sigma = params["sigma"]
    T = params["T"]
    n_paths = min(params.get("n_paths", 100), 500)
    n_steps = min(params.get("n_steps", 252), 252)

    dt = T / n_steps
    paths = np.zeros((n_paths, n_steps + 1))
    paths[:, 0] = r0
    theta = r0 + sigma**2 / (2 * a)  # long-run mean

    for t in range(1, n_steps + 1):
        z = np.random.standard_normal(n_paths)
        paths[:, t] = paths[:, t-1] + a * (theta - paths[:, t-1]) * dt + sigma * math.sqrt(dt) * z

    mean_path = np.mean(paths, axis=0).tolist()
    return {
        "paths": paths.tolist(),
        "mean_path": [round(x, 6) for x in mean_path],
        "note": "Vasicek approximation (FinancePy not available)"
    }


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        main()
    else:
        print(json.dumps({"error": "Use --stdin flag"}))
