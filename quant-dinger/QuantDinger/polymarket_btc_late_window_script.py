"""
Polymarket BTC Late-Window Trend Script for QuantDinger.

Purpose:
- Backtest the upstream repo's core thesis in a repo-native script format.
- Keep only the most testable idea first:
  trade near the end of each 15-minute cycle and follow strong price skew.

Important assumptions:
- Best used on 1m data (or finer). On 15m candles this strategy loses the
  "late-window" timing edge because each bar already spans the whole cycle.
- Price is expected to behave like a probability / binary-market quote in the
  0.0-1.0 range, but the script will still run on any positive price series.

Logic summary:
- If minute 13 of a 15-minute cycle and price > trend_up_threshold -> open long
- If minute 13 of a 15-minute cycle and price < trend_down_threshold -> open short
- Skip the middle band as "coin-flip territory"
- Close any open position when the next 15-minute cycle begins
"""

# @param trend_up_threshold float 0.60 Open long when price is above this threshold near cycle end
# @param trend_down_threshold float 0.40 Open short when price is below this threshold near cycle end
# @param position_pct float 0.25 Fraction of equity to deploy per trade
# @param trade_window_start_minute int 13 First minute in the 15-minute cycle where entries are allowed
# @param trade_window_end_minute int 14 Last minute boundary (exclusive) for entries in the 15-minute cycle
# @param momentum_lookback int 3 Number of recent bars used for simple momentum confirmation
# @param use_momentum_filter bool true Require recent momentum to agree with trade direction
# @param min_cycle_move_pct float 0.01 Minimum move from the momentum lookback anchor to confirm direction
# @param allow_short bool true Allow short entries when price is below the down threshold


def on_init(ctx):
    ctx.log("Polymarket BTC late-window trend script initialized")


def on_bar(ctx, bar):
    params = _read_params(ctx)
    _bootstrap_state(ctx)

    ts = bar.timestamp
    cycle_id = _cycle_id(ts)
    minute_in_cycle = _minute_in_cycle(ts)
    price = float(bar.close or 0.0)

    if cycle_id is None or minute_in_cycle is None or price <= 0.0:
        return

    state = ctx._params
    state["last_seen_cycle_id"] = cycle_id

    # Close any carried position once a new cycle begins. This approximates the
    # upstream idea that the edge belongs to the current 15-minute market only.
    entry_cycle_id = state.get("entry_cycle_id")
    if ctx.position and entry_cycle_id is not None and cycle_id != entry_cycle_id:
        ctx.log(
            f"Cycle rollover exit: cycle={cycle_id} entry_cycle={entry_cycle_id} "
            f"price={price:.6f}"
        )
        ctx.close_position()
        state["entry_cycle_id"] = None
        state["last_trade_cycle_id"] = entry_cycle_id
        return

    # One trade attempt per 15-minute cycle.
    if state.get("last_trade_cycle_id") == cycle_id:
        return

    if not _is_trade_window(minute_in_cycle, params):
        return

    recent_bars = ctx.bars(int(params["momentum_lookback"]) + 1)
    momentum = _momentum(recent_bars)

    if price > float(params["trend_up_threshold"]):
        if bool(params["use_momentum_filter"]) and momentum < float(params["min_cycle_move_pct"]):
            ctx.log(
                f"Skip long: weak momentum={momentum:.4%} "
                f"threshold={float(params['min_cycle_move_pct']):.4%}"
            )
            return
        if ctx.position and str(ctx.position["side"]).lower() == "short":
            ctx.close_position()
            state["entry_cycle_id"] = None
            ctx.log(f"Close short before long entry @ {price:.6f}")
            return
        if not ctx.position:
            amount = _entry_amount(ctx, price, params)
            if amount > 0.0:
                ctx.buy(price=price, amount=amount)
                state["entry_cycle_id"] = cycle_id
                state["last_trade_cycle_id"] = cycle_id
                ctx.log(
                    f"Late-window long entry: cycle={cycle_id} minute={minute_in_cycle} "
                    f"price={price:.6f} amount={amount:.6f} momentum={momentum:.4%}"
                )
        return

    if bool(params["allow_short"]) and price < float(params["trend_down_threshold"]):
        if bool(params["use_momentum_filter"]) and momentum > -float(params["min_cycle_move_pct"]):
            ctx.log(
                f"Skip short: weak momentum={momentum:.4%} "
                f"threshold={-float(params['min_cycle_move_pct']):.4%}"
            )
            return
        if ctx.position and str(ctx.position["side"]).lower() == "long":
            ctx.close_position()
            state["entry_cycle_id"] = None
            ctx.log(f"Close long before short entry @ {price:.6f}")
            return
        if not ctx.position:
            amount = _entry_amount(ctx, price, params)
            if amount > 0.0:
                ctx.sell(price=price, amount=amount)
                state["entry_cycle_id"] = cycle_id
                state["last_trade_cycle_id"] = cycle_id
                ctx.log(
                    f"Late-window short entry: cycle={cycle_id} minute={minute_in_cycle} "
                    f"price={price:.6f} amount={amount:.6f} momentum={momentum:.4%}"
                )
        return

    ctx.log(
        f"Skip neutral zone: cycle={cycle_id} minute={minute_in_cycle} price={price:.6f} "
        f"band=({float(params['trend_down_threshold']):.2f}, {float(params['trend_up_threshold']):.2f})"
    )


def _read_params(ctx):
    return {
        "trend_up_threshold": float(ctx.param("trend_up_threshold", 0.60)),
        "trend_down_threshold": float(ctx.param("trend_down_threshold", 0.40)),
        "position_pct": float(ctx.param("position_pct", 0.25)),
        "trade_window_start_minute": int(ctx.param("trade_window_start_minute", 13)),
        "trade_window_end_minute": int(ctx.param("trade_window_end_minute", 14)),
        "momentum_lookback": int(ctx.param("momentum_lookback", 3)),
        "use_momentum_filter": bool(ctx.param("use_momentum_filter", True)),
        "min_cycle_move_pct": float(ctx.param("min_cycle_move_pct", 0.01)),
        "allow_short": bool(ctx.param("allow_short", True)),
    }


def _bootstrap_state(ctx):
    state = ctx._params
    if "entry_cycle_id" not in state:
        state["entry_cycle_id"] = None
    if "last_trade_cycle_id" not in state:
        state["last_trade_cycle_id"] = None
    if "last_seen_cycle_id" not in state:
        state["last_seen_cycle_id"] = None


def _is_trade_window(minute_in_cycle, params):
    start = int(params["trade_window_start_minute"])
    end = int(params["trade_window_end_minute"])
    return start <= int(minute_in_cycle) < end


def _entry_amount(ctx, price, params):
    deploy_ratio = max(0.0, min(1.0, float(params["position_pct"])))
    equity = float(ctx.equity or ctx.balance or 0.0)
    if equity <= 0.0 or price <= 0.0 or deploy_ratio <= 0.0:
        return 0.0
    return (equity * deploy_ratio) / price


def _momentum(bars):
    if not bars or len(bars) < 2:
        return 0.0
    first_price = float(bars[0].close or 0.0)
    last_price = float(bars[-1].close or 0.0)
    if first_price <= 0.0:
        return 0.0
    return (last_price - first_price) / first_price


def _cycle_id(ts):
    try:
        return int(ts.timestamp()) // 900
    except Exception:
        return None


def _minute_in_cycle(ts):
    try:
        return int(ts.minute) % 15
    except Exception:
        return None
