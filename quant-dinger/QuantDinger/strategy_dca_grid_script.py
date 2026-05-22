"""
DCA Grid ScriptStrategy for QuantDinger.

Design goals:
- keep DCA grid entries
- keep exit-on-recovery-after-DCA logic
- keep trailing stop-loss logic
- follow current QuantDinger ScriptStrategy runtime semantics
- stay close to the documented DCA Grid strategy rules

Important runtime note:
- `ctx.param()` is read-or-init only in the current engine
- mutable runtime state is therefore stored in `ctx._params`
- DCA layer state is tracked in strategy units, then converted to a reduce ratio
  against the current position for partial exits
"""

# @param rsi_period int 14 RSI period
# @param ma_rsi_period int 7 MA-RSI smoothing period
# @param rsi_threshold_long float 30.0 RSI oversold threshold for long entries
# @param rsi_threshold_short float 70.0 RSI overbought threshold for short entries
# @param ma_rsi_threshold_long float 35.0 MA-RSI threshold for long entries
# @param ma_rsi_threshold_short float 65.0 MA-RSI threshold for short entries

# @param dca_grid_pct float 2.0 First DCA grid distance in percent
# @param dca_multiplier float 1.05 Multiplier applied to each next grid step
# @param dca_max_count int 5 Maximum DCA adds

# @param entry_pct float 0.25 Initial entry size ratio
# @param dca_amount float 100.0 DCA amount as percent of previous fill (100 = same size, 105 = 5% larger)
# @param dca_amount_multiplier float 1.05 Extra multiplier applied to each next DCA amount (from 2nd DCA onward)

# @param init_roi_pct float 2.0 Profit threshold that activates trailing
# @param trailing_pct float 1.5 Trailing stop distance in percent
# @param stop_loss_pct float 5.0 Hard stop-loss distance in percent

# @param allow_short bool false Allow short trades
# @param use_stop_loss bool false Enable hard stop-loss
# @param use_trailing bool false Enable trailing stop
# @param use_exit_dca bool true Exit after recovery from the latest DCA level


def on_init(ctx):
    ctx.log("DCA grid script initialized")


def on_bar(ctx, bar):
    params = _read_params(ctx)
    _bootstrap_runtime_state(ctx)

    bars = ctx.bars(_required_lookback(params))
    if len(bars) < max(int(params["rsi_period"]) + int(params["ma_rsi_period"]) + 2, 20):
        return

    closes = np.array([float(b.close) for b in bars], dtype=float)
    rsi_series = _calculate_rsi_series(closes, int(params["rsi_period"]))
    ma_rsi_series = _calculate_ema_series(rsi_series, int(params["ma_rsi_period"]))

    if len(rsi_series) < 2 or len(ma_rsi_series) < 2:
        return

    rsi_now = float(rsi_series[-1])
    rsi_prev = float(rsi_series[-2])
    ma_rsi_now = float(ma_rsi_series[-1])
    ma_rsi_prev = float(ma_rsi_series[-2])

    if not _is_finite_signal(rsi_now, rsi_prev, ma_rsi_now, ma_rsi_prev):
        return

    price = float(bar.close)

    if not ctx.position:
        _reset_runtime_state(ctx)

        if _is_long_entry_signal(rsi_now, rsi_prev, ma_rsi_now, ma_rsi_prev, params):
            _log_entry_signal_snapshot(ctx, "long", price, rsi_now, rsi_prev, ma_rsi_now, ma_rsi_prev, params)
            _open_long_position(ctx, price, params)
            return

        if bool(params["allow_short"]) and _is_short_entry_signal(rsi_now, rsi_prev, ma_rsi_now, ma_rsi_prev, params):
            _log_entry_signal_snapshot(ctx, "short", price, rsi_now, rsi_prev, ma_rsi_now, ma_rsi_prev, params)
            _open_short_position(ctx, price, params)
        return

    _sync_position_state(ctx, price, params)
    _log_state_snapshot(ctx, f"state_sync side={ctx.position['side']} price={price}")

    side = str(ctx.position["side"] or "").strip().lower()
    if side == "long":
        _handle_long_position(ctx, price, params)
        return
    if side == "short":
        _handle_short_position(ctx, price, params)
        return

    _reset_runtime_state(ctx)


def _read_params(ctx):
    return {
        "rsi_period": int(ctx.param("rsi_period", 14)),
        "ma_rsi_period": int(ctx.param("ma_rsi_period", 7)),
        "rsi_threshold_long": float(ctx.param("rsi_threshold_long", 30.0)),
        "rsi_threshold_short": float(ctx.param("rsi_threshold_short", 70.0)),
        "ma_rsi_threshold_long": float(ctx.param("ma_rsi_threshold_long", 35.0)),
        "ma_rsi_threshold_short": float(ctx.param("ma_rsi_threshold_short", 65.0)),
        "dca_grid_pct": float(ctx.param("dca_grid_pct", 2.0)),
        "dca_multiplier": float(ctx.param("dca_multiplier", 1.05)),
        "dca_max_count": int(ctx.param("dca_max_count", 5)),
        "entry_pct": float(ctx.param("entry_pct", 0.25)),
        "dca_amount": float(ctx.param("dca_amount", 100.0)),
        "dca_amount_multiplier": float(ctx.param("dca_amount_multiplier", 1.05)),
        "init_roi_pct": float(ctx.param("init_roi_pct", 2.0)),
        "trailing_pct": float(ctx.param("trailing_pct", 1.5)),
        "stop_loss_pct": float(ctx.param("stop_loss_pct", 5.0)),
        "allow_short": bool(ctx.param("allow_short", False)),
        "use_stop_loss": bool(ctx.param("use_stop_loss", False)),
        "use_trailing": bool(ctx.param("use_trailing", False)),
        "use_exit_dca": bool(ctx.param("use_exit_dca", True)),
    }


def _bootstrap_runtime_state(ctx):
    state = ctx._params
    if "grid_anchor_price" not in state:
        state["grid_anchor_price"] = 0.0
    if "dca_count" not in state:
        state["dca_count"] = 0
    if "layers" not in state or not isinstance(state.get("layers"), list):
        state["layers"] = []
    if "highest_price" not in state:
        state["highest_price"] = 0.0
    if "lowest_price" not in state:
        state["lowest_price"] = 0.0
    if "trailing_activated" not in state:
        state["trailing_activated"] = False
    if "total_entry_value" not in state:
        state["total_entry_value"] = 0.0
    if "total_exit_value" not in state:
        state["total_exit_value"] = 0.0


def _reset_runtime_state(ctx):
    state = ctx._params
    state["grid_anchor_price"] = 0.0
    state["dca_count"] = 0
    state["layers"] = []
    state["highest_price"] = 0.0
    state["lowest_price"] = 0.0
    state["trailing_activated"] = False
    state["total_entry_value"] = 0.0
    state["total_exit_value"] = 0.0


def _sync_position_state(ctx, current_price, params):
    state = ctx._params
    side = str(ctx.position["side"] or "").strip().lower()
    entry_price = float(ctx.position["entry_price"] or 0.0)
    position_size = float(ctx.position.get("size") or 0.0)

    if side == "long":
        if float(state.get("grid_anchor_price") or 0.0) <= 0:
            state["grid_anchor_price"] = entry_price
        if not state.get("layers"):
            # Restore the base layer from the real position size so script layers
            # stay aligned with engine-sized entries after restart/state loss.
            restored_amount = position_size if position_size > 0.0 else _entry_order_amount(ctx, entry_price, params)
            state["layers"] = [_make_layer(entry_price, restored_amount, entry_price, "restored_base")]
        if float(state.get("highest_price") or 0.0) <= 0:
            state["highest_price"] = current_price
        state["highest_price"] = max(float(state.get("highest_price") or 0.0), current_price)
        if float(state.get("lowest_price") or 0.0) <= 0:
            state["lowest_price"] = entry_price
        # Restore total_entry_value from layers if missing (e.g. after restart)
        if float(state.get("total_entry_value") or 0.0) <= 0:
            total_ev = sum(
                float(l.get("amount") or 0.0) * float(l.get("price") or 0.0)
                for l in (state.get("layers") or [])
            )
            state["total_entry_value"] = total_ev
        return

    if side == "short":
        if float(state.get("grid_anchor_price") or 0.0) <= 0:
            state["grid_anchor_price"] = entry_price
        if not state.get("layers"):
            restored_amount = position_size if position_size > 0.0 else _entry_order_amount(ctx, entry_price, params)
            state["layers"] = [_make_layer(entry_price, restored_amount, entry_price, "restored_base")]
        if float(state.get("lowest_price") or 0.0) <= 0:
            state["lowest_price"] = current_price
        state["lowest_price"] = min(float(state.get("lowest_price") or 0.0), current_price)
        if float(state.get("highest_price") or 0.0) <= 0:
            state["highest_price"] = entry_price
        # Restore total_entry_value from layers if missing (e.g. after restart)
        if float(state.get("total_entry_value") or 0.0) <= 0:
            total_ev = sum(
                float(l.get("amount") or 0.0) * float(l.get("price") or 0.0)
                for l in (state.get("layers") or [])
            )
            state["total_entry_value"] = total_ev
        return

    _reset_runtime_state(ctx)


def _handle_long_position(ctx, price, params):
    state = ctx._params
    entry_price = float(ctx.position["entry_price"] or 0.0)
    if entry_price <= 0:
        return

    highest_price = max(float(state.get("highest_price") or price), price)
    state["highest_price"] = highest_price

    # --- ROI tổng hợp: tính cả phần đã exit DCA ---
    # roi = (marketPrice * remaining + totalExitValue - totalEntryValue) / totalEntryValue * 100
    layers = list(state.get("layers") or [])
    remaining_amount = sum(float(l.get("amount") or 0.0) for l in layers)
    total_entry_value = float(state.get("total_entry_value") or 0.0)
    total_exit_value = float(state.get("total_exit_value") or 0.0)
    if total_entry_value > 0.0:
        roi_pct = (price * remaining_amount + total_exit_value - total_entry_value) / total_entry_value * 100.0
    else:
        # fallback nếu chưa có total_entry_value (ví dụ restored từ restart)
        roi_pct = ((price / entry_price) - 1.0) * 100.0

    dca_count = max(0, len(layers) - 1)
    state["dca_count"] = dca_count

    was_trailing = bool(state.get("trailing_activated"))
    if roi_pct >= float(params["init_roi_pct"]):
        state["trailing_activated"] = True
    if not was_trailing and bool(state.get("trailing_activated")):
        ctx.log(f"LONG trailing_activated: roi={roi_pct:.4f}% >= threshold={params['init_roi_pct']}% @ price={price:.6f}")

    ctx.log(
        "LONG monitor "
        f"price={price:.6f} entry={entry_price:.6f} roi={roi_pct:.4f}% "
        f"remaining={remaining_amount:.6f} total_entry={total_entry_value:.4f} total_exit={total_exit_value:.4f} "
        f"highest={highest_price:.6f} trailing_active={bool(state.get('trailing_activated'))}"
    )
    _log_state_snapshot(ctx, "long_monitor")

    # TP toàn cục luôn được ưu tiên hơn exit DCA.
    if roi_pct >= float(params["init_roi_pct"]) and not bool(params["use_trailing"]):
        ctx.close_position()
        ctx.log(
            f"Take profit global (LONG): close @ {price} "
            f"roi={roi_pct:.4f}% >= threshold={params['init_roi_pct']}%"
        )
        _log_state_snapshot(ctx, "long_take_profit_before_reset")
        _reset_runtime_state(ctx)
        return

    if bool(params["use_trailing"]) and bool(state.get("trailing_activated")):
        trailing_stop = highest_price * (1.0 - float(params["trailing_pct"]) / 100.0)
        ctx.log(f"LONG trailing_check stop={trailing_stop:.6f} price={price:.6f}")
        if price <= trailing_stop:
            ctx.close_position()
            ctx.log(f"Trailing stop hit (LONG): close @ {price} roi={roi_pct:.4f}%")
            _log_state_snapshot(ctx, "long_trailing_close_before_reset")
            _reset_runtime_state(ctx)
            return

    if bool(params["use_stop_loss"]) and float(params["stop_loss_pct"]) > 0.0:
        stop_loss_price = entry_price * (1.0 - float(params["stop_loss_pct"]) / 100.0)
        ctx.log(f"LONG stop_check hard_stop={stop_loss_price:.6f} price={price:.6f}")
        if price <= stop_loss_price:
            ctx.close_position()
            ctx.log(f"Hard stop hit (LONG): close @ {price} roi={roi_pct:.4f}%")
            _log_state_snapshot(ctx, "long_hard_stop_before_reset")
            _reset_runtime_state(ctx)
            return

    if bool(params["use_exit_dca"]) and len(layers) > 1:
        last_layer = layers[-1]
        exit_price = float(last_layer.get("exit_price") or 0.0)
        reduce_ratio = _layer_reduce_ratio(layers, float(last_layer.get("amount") or 0.0))
        stack_before = [float(layer.get("price") or 0.0) for layer in layers]
        ctx.log(
            "LONG exit_dca_check "
            f"trigger_price={exit_price:.6f} price={price:.6f} reduce_ratio={reduce_ratio:.6f} "
            f"layers_count={len(layers)} stack_prices={stack_before} layer={_format_layer(last_layer)}"
        )
        if last_layer.get("kind") == "dca" and exit_price > 0.0 and reduce_ratio > 0.0 and price >= exit_price:
            exit_amount = float(last_layer.get("amount") or 0.0)
            state["total_exit_value"] = total_exit_value + exit_amount * price
            ctx.reduce_position(ratio=reduce_ratio)
            state["layers"] = layers[:-1]
            state["dca_count"] = max(0, len(state["layers"]) - 1)
            stack_after = [float(layer.get("price") or 0.0) for layer in state["layers"]]
            ctx.log(
                f"Exit DCA partial (LONG): reduce {reduce_ratio:.6f} @ {price} "
                f"target_price={float(last_layer.get('price') or 0.0):.6f} "
                f"target_exit={exit_price:.6f} exit_amount={exit_amount:.6f} "
                f"stack_before={stack_before} stack_after={stack_after}"
            )
            _log_state_snapshot(ctx, "long_exit_dca_after_pop")
            return

    if dca_count >= int(params["dca_max_count"]):
        ctx.log(f"LONG dca_skip max_count_reached count={dca_count}")
        return

    next_dca_price = _next_long_dca_price(ctx, params)
    ctx.log(f"LONG dca_check next_price={next_dca_price:.6f} current_price={price:.6f} count={dca_count}")
    if price <= next_dca_price:
        dca_amount = _next_dca_amount(ctx, params, is_first_dca=(dca_count == 0))
        ctx.buy(price=price, amount=dca_amount)
        new_stack = layers + [_make_layer(price, dca_amount, price, "dca")]
        avg_exit_price = _stack_average_price(new_stack)
        new_stack[-1]["exit_price"] = avg_exit_price
        state["layers"] = new_stack
        state["dca_count"] = max(0, len(state["layers"]) - 1)
        state["total_entry_value"] = total_entry_value + dca_amount * price
        state["highest_price"] = price
        state["trailing_activated"] = False
        stack_prices = [float(layer.get("price") or 0.0) for layer in new_stack]
        ctx.log(
            f"DCA add LONG #{state['dca_count']}: amount={dca_amount:.6f} @ {price} "
            f"exit_price(weighted_stack)={avg_exit_price:.6f} stack_prices={stack_prices}"
        )
        _log_state_snapshot(ctx, "long_dca_added")


def _handle_short_position(ctx, price, params):
    state = ctx._params
    entry_price = float(ctx.position["entry_price"] or 0.0)
    if entry_price <= 0:
        return

    lowest_price = min(float(state.get("lowest_price") or price), price)
    state["lowest_price"] = lowest_price

    # --- ROI tổng hợp: tính cả phần đã exit DCA ---
    # SHORT: bán cao (entry), mua lại thấp (exit DCA).
    # total_entry_value  = tổng giá trị bán vào (entry + DCA add)  = Σ amount_i * sell_price_i
    # total_exit_value   = tổng giá trị mua lại (exit DCA buyback) = Σ amount_i * buyback_price_i
    # remaining_value    = giá trị mua lại phần còn lại nếu đóng ngay = remaining * current_price
    #
    # P&L = total_entry_value - total_exit_value - remaining_value
    # ROI  = P&L / total_entry_value * 100
    #      = (total_entry_value - total_exit_value - price * remaining) / total_entry_value * 100
    layers = list(state.get("layers") or [])
    remaining_amount = sum(float(l.get("amount") or 0.0) for l in layers)
    total_entry_value = float(state.get("total_entry_value") or 0.0)
    total_exit_value = float(state.get("total_exit_value") or 0.0)
    if total_entry_value > 0.0:
        roi_pct = (total_entry_value - total_exit_value - price * remaining_amount) / total_entry_value * 100.0
    else:
        roi_pct = (1.0 - (price / entry_price)) * 100.0

    dca_count = max(0, len(layers) - 1)
    state["dca_count"] = dca_count

    was_trailing = bool(state.get("trailing_activated"))
    if roi_pct >= float(params["init_roi_pct"]):
        state["trailing_activated"] = True
    if not was_trailing and bool(state.get("trailing_activated")):
        ctx.log(f"SHORT trailing_activated: roi={roi_pct:.4f}% >= threshold={params['init_roi_pct']}% @ price={price:.6f}")

    ctx.log(
        "SHORT monitor "
        f"price={price:.6f} entry={entry_price:.6f} roi={roi_pct:.4f}% "
        f"remaining={remaining_amount:.6f} total_entry={total_entry_value:.4f} total_exit={total_exit_value:.4f} "
        f"lowest={lowest_price:.6f} trailing_active={bool(state.get('trailing_activated'))}"
    )
    _log_state_snapshot(ctx, "short_monitor")

    # TP toàn cục luôn được ưu tiên hơn exit DCA.
    if roi_pct >= float(params["init_roi_pct"]) and not bool(params["use_trailing"]):
        ctx.close_position()
        ctx.log(
            f"Take profit global (SHORT): close @ {price} "
            f"roi={roi_pct:.4f}% >= threshold={params['init_roi_pct']}%"
        )
        _log_state_snapshot(ctx, "short_take_profit_before_reset")
        _reset_runtime_state(ctx)
        return

    if bool(params["use_trailing"]) and bool(state.get("trailing_activated")):
        trailing_stop = lowest_price * (1.0 + float(params["trailing_pct"]) / 100.0)
        ctx.log(f"SHORT trailing_check stop={trailing_stop:.6f} price={price:.6f}")
        if price >= trailing_stop:
            ctx.close_position()
            ctx.log(f"Trailing stop hit (SHORT): close @ {price} roi={roi_pct:.4f}%")
            _log_state_snapshot(ctx, "short_trailing_close_before_reset")
            _reset_runtime_state(ctx)
            return

    if bool(params["use_stop_loss"]) and float(params["stop_loss_pct"]) > 0.0:
        stop_loss_price = entry_price * (1.0 + float(params["stop_loss_pct"]) / 100.0)
        ctx.log(f"SHORT stop_check hard_stop={stop_loss_price:.6f} price={price:.6f}")
        if price >= stop_loss_price:
            ctx.close_position()
            ctx.log(f"Hard stop hit (SHORT): close @ {price} roi={roi_pct:.4f}%")
            _log_state_snapshot(ctx, "short_hard_stop_before_reset")
            _reset_runtime_state(ctx)
            return

    if bool(params["use_exit_dca"]) and len(layers) > 1:
        last_layer = layers[-1]
        exit_price = float(last_layer.get("exit_price") or 0.0)
        reduce_ratio = _layer_reduce_ratio(layers, float(last_layer.get("amount") or 0.0))
        stack_before = [float(layer.get("price") or 0.0) for layer in layers]
        ctx.log(
            "SHORT exit_dca_check "
            f"trigger_price={exit_price:.6f} price={price:.6f} reduce_ratio={reduce_ratio:.6f} "
            f"layers_count={len(layers)} stack_prices={stack_before} layer={_format_layer(last_layer)}"
        )
        if last_layer.get("kind") == "dca" and exit_price > 0.0 and reduce_ratio > 0.0 and price <= exit_price:
            exit_amount = float(last_layer.get("amount") or 0.0)
            state["total_exit_value"] = total_exit_value + exit_amount * price
            ctx.reduce_position(ratio=reduce_ratio)
            state["layers"] = layers[:-1]
            state["dca_count"] = max(0, len(state["layers"]) - 1)
            stack_after = [float(layer.get("price") or 0.0) for layer in state["layers"]]
            ctx.log(
                f"Exit DCA partial (SHORT): reduce {reduce_ratio:.6f} @ {price} "
                f"target_price={float(last_layer.get('price') or 0.0):.6f} "
                f"target_exit={exit_price:.6f} exit_amount={exit_amount:.6f} "
                f"stack_before={stack_before} stack_after={stack_after}"
            )
            _log_state_snapshot(ctx, "short_exit_dca_after_pop")
            return

    if dca_count >= int(params["dca_max_count"]):
        ctx.log(f"SHORT dca_skip max_count_reached count={dca_count}")
        return

    next_dca_price = _next_short_dca_price(ctx, params)
    ctx.log(f"SHORT dca_check next_price={next_dca_price:.6f} current_price={price:.6f} count={dca_count}")
    if price >= next_dca_price:
        dca_amount = _next_dca_amount(ctx, params, is_first_dca=(dca_count == 0))
        ctx.sell(price=price, amount=dca_amount)
        new_stack = layers + [_make_layer(price, dca_amount, price, "dca")]
        avg_exit_price = _stack_average_price(new_stack)
        new_stack[-1]["exit_price"] = avg_exit_price
        state["layers"] = new_stack
        state["dca_count"] = max(0, len(state["layers"]) - 1)
        state["total_entry_value"] = total_entry_value + dca_amount * price
        state["lowest_price"] = price
        state["trailing_activated"] = False
        stack_prices = [float(layer.get("price") or 0.0) for layer in new_stack]
        ctx.log(
            f"DCA add SHORT #{state['dca_count']}: amount={dca_amount:.6f} @ {price} "
            f"exit_price(weighted_stack)={avg_exit_price:.6f} stack_prices={stack_prices}"
        )
        _log_state_snapshot(ctx, "short_dca_added")


def _open_long_position(ctx, price, params):
    entry_amount = _entry_order_amount(ctx, price, params)
    if entry_amount <= 0.0:
        return
    ctx.buy(price=price, amount=entry_amount)

    state = ctx._params
    state["grid_anchor_price"] = price
    state["dca_count"] = 0
    state["layers"] = [_make_layer(price, entry_amount, price, "entry")]
    state["highest_price"] = price
    state["lowest_price"] = price
    state["trailing_activated"] = False
    state["total_entry_value"] = entry_amount * price
    state["total_exit_value"] = 0.0

    ctx.log(
        f"Open LONG: amount={entry_amount} @ {price} "
        f"rsi entry recorded total_entry_value={state['total_entry_value']:.4f}"
    )
    _log_state_snapshot(ctx, "open_long")


def _open_short_position(ctx, price, params):
    entry_amount = _entry_order_amount(ctx, price, params)
    if entry_amount <= 0.0:
        return
    ctx.sell(price=price, amount=entry_amount)

    state = ctx._params
    state["grid_anchor_price"] = price
    state["dca_count"] = 0
    state["layers"] = [_make_layer(price, entry_amount, price, "entry")]
    state["highest_price"] = price
    state["lowest_price"] = price
    state["trailing_activated"] = False
    state["total_entry_value"] = entry_amount * price
    state["total_exit_value"] = 0.0

    ctx.log(
        f"Open SHORT: amount={entry_amount} @ {price} "
        f"total_entry_value={state['total_entry_value']:.4f}"
    )
    _log_state_snapshot(ctx, "open_short")


def _log_entry_signal_snapshot(ctx, side, price, rsi_now, rsi_prev, ma_rsi_now, ma_rsi_prev, params):
    side = str(side or "").strip().lower()
    if side == "short":
        threshold_rsi = float(params["rsi_threshold_short"])
        threshold_ma = float(params["ma_rsi_threshold_short"])
        condition_summary = (
            f"ma_now>=threshold={_format_check(ma_rsi_now >= threshold_ma)} "
            f"rsi_prev>=threshold={_format_check(rsi_prev >= threshold_rsi)} "
            f"rsi_prev>=ma_prev={_format_check(rsi_prev >= ma_rsi_prev)} "
            f"rsi_now<ma_now={_format_check(rsi_now < ma_rsi_now)}"
        )
    else:
        threshold_rsi = float(params["rsi_threshold_long"])
        threshold_ma = float(params["ma_rsi_threshold_long"])
        condition_summary = (
            f"ma_now<=threshold={_format_check(ma_rsi_now <= threshold_ma)} "
            f"rsi_prev<=threshold={_format_check(rsi_prev <= threshold_rsi)} "
            f"rsi_prev<=ma_prev={_format_check(rsi_prev <= ma_rsi_prev)} "
            f"rsi_now>ma_now={_format_check(rsi_now > ma_rsi_now)}"
        )

    ctx.log(
        f"{side.upper()} entry_signal_triggered "
        f"price={float(price or 0.0):.6f} "
        f"rsi_prev={rsi_prev:.4f} rsi_now={rsi_now:.4f} "
        f"ma_rsi_prev={ma_rsi_prev:.4f} ma_rsi_now={ma_rsi_now:.4f} "
        f"thresholds(rsi={threshold_rsi:.4f},ma_rsi={threshold_ma:.4f}) "
        f"checks({condition_summary})"
    )


def _is_long_entry_signal(rsi_now, rsi_prev, ma_rsi_now, ma_rsi_prev, params):
    return (
        ma_rsi_now <= float(params["ma_rsi_threshold_long"])
        and rsi_prev <= float(params["rsi_threshold_long"])
        and rsi_prev <= ma_rsi_prev
        and rsi_now > ma_rsi_now
    )


def _is_short_entry_signal(rsi_now, rsi_prev, ma_rsi_now, ma_rsi_prev, params):
    return (
        ma_rsi_now >= float(params["ma_rsi_threshold_short"])
        and rsi_prev >= float(params["rsi_threshold_short"])
        and rsi_prev >= ma_rsi_prev
        and rsi_now < ma_rsi_now
    )


def _required_lookback(params):
    rsi_period = int(params["rsi_period"])
    ma_rsi_period = int(params["ma_rsi_period"])
    return max(rsi_period + ma_rsi_period + 10, 50)


def _next_long_dca_price(ctx, params):
    state = ctx._params
    layers = list(state.get("layers") or [])
    anchor_price = float(state.get("grid_anchor_price") or ctx.position["entry_price"] or 0.0)
    base_step = max(float(params["dca_grid_pct"]), 0.01) / 100.0
    multiplier = max(float(params["dca_multiplier"]), 0.01)
    if len(layers) <= 1:
        step = min(base_step, 0.95)
        return anchor_price * (1.0 - step)

    last_price = float(layers[-1].get("price") or anchor_price)
    step = min(base_step * multiplier, 0.95)
    return last_price * (1.0 - step)


def _next_short_dca_price(ctx, params):
    state = ctx._params
    layers = list(state.get("layers") or [])
    anchor_price = float(state.get("grid_anchor_price") or ctx.position["entry_price"] or 0.0)
    base_step = max(float(params["dca_grid_pct"]), 0.01) / 100.0
    multiplier = max(float(params["dca_multiplier"]), 0.01)
    if len(layers) <= 1:
        return anchor_price * (1.0 + base_step)

    last_price = float(layers[-1].get("price") or anchor_price)
    step = base_step * multiplier
    return last_price * (1.0 + step)


def _calculate_rsi_series(closes, period):
    values = np.asarray(closes, dtype=float)
    length = len(values)
    out = np.full(length, np.nan, dtype=float)

    if length <= period:
        return out

    deltas = np.diff(values)
    gains = np.where(deltas > 0.0, deltas, 0.0)
    losses = np.where(deltas < 0.0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0.0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - (100.0 / (1.0 + rs))

    for idx in range(period + 1, length):
        gain = gains[idx - 1]
        loss = losses[idx - 1]
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0.0:
            out[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[idx] = 100.0 - (100.0 / (1.0 + rs))

    return out


def _calculate_ema_series(values, period):
    arr = np.asarray(values, dtype=float)
    out = np.full(len(arr), np.nan, dtype=float)

    if period <= 0:
        return out

    first_idx = -1
    for idx in range(len(arr)):
        if np.isfinite(arr[idx]):
            first_idx = idx
            break

    if first_idx < 0:
        return out

    alpha = 2.0 / (float(period) + 1.0)
    out[first_idx] = float(arr[first_idx])

    for idx in range(first_idx + 1, len(arr)):
        if not np.isfinite(arr[idx]):
            continue
        prev = out[idx - 1]
        if not np.isfinite(prev):
            prev = arr[idx]
        out[idx] = float(arr[idx]) * alpha + float(prev) * (1.0 - alpha)

    return out


def _next_dca_amount(ctx, params, is_first_dca: bool = False):
    """
    Tính amount cho lần DCA tiếp theo.

    Công thức (theo tài liệu):
      - DCA lần đầu:    entry_amount * dca_amount / 100
      - DCA tiếp theo:  last_dca_amount * dca_amount / 100 * dca_amount_multiplier

    Ví dụ với dca_amount=100, dca_amount_multiplier=1.05, entry=0.1:
      DCA 1: 0.1 * 100/100           = 0.1
      DCA 2: 0.1 * 100/100 * 1.05   = 0.105
      DCA 3: 0.105 * 100/100 * 1.05 = 0.11025
    """
    state = ctx._params
    layers = list(state.get("layers") or [])
    dca_factor = max(float(params["dca_amount"]), 0.0) / 100.0
    multiplier = max(float(params["dca_amount_multiplier"]), 0.0)
    entry_amount = _base_layer_amount(ctx)

    if is_first_dca or not layers:
        # Lần DCA đầu tiên: tính từ entry_amount, không nhân multiplier
        return entry_amount * dca_factor

    # Lần DCA tiếp theo: tính từ amount của layer DCA cuối cùng, nhân multiplier
    last_amount = float(layers[-1].get("amount") or 0.0)
    if last_amount <= 0.0:
        return entry_amount * dca_factor
    return last_amount * dca_factor * multiplier


def _base_layer_amount(ctx):
    layers = list((ctx._params or {}).get("layers") or [])
    if layers:
        base_amount = float(layers[0].get("amount") or 0.0)
        if base_amount > 0.0:
            return base_amount
    position_size = float((ctx.position or {}).get("size") or 0.0)
    if position_size > 0.0:
        return position_size
    return 0.0


def _entry_order_amount(ctx, price, params):
    price = float(price or 0.0)
    if price <= 0.0:
        return 0.0

    entry_ratio = max(float(params.get("entry_pct") or 0.0), 0.0)
    equity = max(float(ctx.equity or ctx.balance or 0.0), 0.0)
    leverage = max(float(ctx.leverage or 1.0), 1.0)
    return (equity * entry_ratio * leverage) / price


def _make_layer(price, amount, exit_price, kind):
    return {
        "price": float(price),
        "amount": float(amount),
        "exit_price": float(exit_price),
        "kind": str(kind or "dca"),
    }


def _stack_average_price(layers):
    total_amount = 0.0
    total_value = 0.0
    for layer in layers or []:
        price = float(layer.get("price") or 0.0)
        amount = float(layer.get("amount") or 0.0)
        if price > 0.0 and amount > 0.0:
            total_amount += amount
            total_value += price * amount
    if total_amount <= 0.0:
        return 0.0
    return total_value / total_amount


def _layer_reduce_ratio(layers, layer_amount):
    total_amount = 0.0
    for layer in layers:
        total_amount += max(float(layer.get("amount") or 0.0), 0.0)
    if total_amount <= 0.0 or layer_amount <= 0.0:
        return 0.0
    return max(0.0, min(float(layer_amount) / total_amount, 1.0))


def _format_layer(layer):
    return (
        "{"
        f"kind={layer.get('kind')},"
        f"price={float(layer.get('price') or 0.0):.6f},"
        f"amount={float(layer.get('amount') or 0.0):.6f},"
        f"exit={float(layer.get('exit_price') or 0.0):.6f}"
        "}"
    )


def _log_state_snapshot(ctx, label):
    state = ctx._params
    layers = list(state.get("layers") or [])
    formatted_layers = ", ".join(_format_layer(layer) for layer in layers)
    side = str(ctx.position.get("side") or "")
    size = float(ctx.position.get("size") or 0.0)
    entry_price = float(ctx.position.get("entry_price") or 0.0)
    total_entry_value = float(state.get("total_entry_value") or 0.0)
    total_exit_value = float(state.get("total_exit_value") or 0.0)
    ctx.log(
        f"[DCA_DEBUG] {label} "
        f"side={side} size={size:.6f} entry={entry_price:.6f} "
        f"grid_anchor={float(state.get('grid_anchor_price') or 0.0):.6f} "
        f"dca_count={int(state.get('dca_count') or 0)} "
        f"highest={float(state.get('highest_price') or 0.0):.6f} "
        f"lowest={float(state.get('lowest_price') or 0.0):.6f} "
        f"trailing_active={bool(state.get('trailing_activated'))} "
        f"total_entry={total_entry_value:.4f} total_exit={total_exit_value:.4f} "
        f"layers=[{formatted_layers}]"
    )


def _is_finite_signal(rsi_now, rsi_prev, ma_rsi_now, ma_rsi_prev):
    return bool(
        np.isfinite(rsi_now)
        and np.isfinite(rsi_prev)
        and np.isfinite(ma_rsi_now)
        and np.isfinite(ma_rsi_prev)
    )


def _format_check(value):
    return "yes" if bool(value) else "no"
