from __future__ import annotations

from datetime import datetime
from math import sqrt
from uuid import uuid4

from django.utils import timezone

from .indicators import calculate_bollinger_bands, calculate_ema, calculate_rsi
from .model_analysis import analyze_model
from .market_data import SYNTHETIC_SOURCE, candle_data_source
from .strategy_registry import strategy_contract_for, strategy_engine_for


TRADING_PERIODS_PER_YEAR = {
    "1m": 525600,
    "5m": 105120,
    "15m": 35040,
    "1h": 8760,
    "4h": 2190,
    "1d": 365,
}
MIN_BACKTEST_CANDLES = 50
MIN_WALK_FORWARD_CANDLES = 120
WALK_FORWARD_TRAIN_FRACTION = 0.5
WALK_FORWARD_TEST_FRACTION = 0.2


def _enabled_strategy_ids(agent: dict) -> list[str]:
    return [s.get("id", "") for s in agent.get("strategies", []) if s.get("enabled")]


def _uses_trend_breakout(agent: dict) -> bool:
    return strategy_engine_for(agent) == "trend_breakout_v1"


def run_backtest(payload: dict, candles: list[dict]) -> dict:
    validated_candles = validate_candles(candles)
    if len(validated_candles) < MIN_BACKTEST_CANDLES:
        raise ValueError("At least 50 candles are required to run a backtest.")
    data_source = candle_data_source(candles)
    if data_source == SYNTHETIC_SOURCE:
        raise ValueError(
            "Synthetic demo candles cannot be used to validate a trading strategy. "
            "Connect a real market-data source before running this backtest."
        )

    symbol = payload["symbol"].upper()
    timeframe = payload["timeframe"]
    raw_settings = payload.get("settings", {}) or {}
    settings = {
        "startingBalance": raw_settings.get("startingBalance", 10000),
        "feeRate": raw_settings.get("feeRate", 0.001),
        "slippageRate": raw_settings.get("slippageRate", 0.0005),
        "positionSizeFraction": raw_settings.get("positionSizeFraction", 0.95),
        # Realistic-execution extensions (all optional, backward compatible).
        "spreadPips": raw_settings.get("spreadPips"),
        "riskPct": raw_settings.get("riskPct", 0.01),
        "atrStopMultiplier": raw_settings.get("atrStopMultiplier", 1.5),
        "rewardRiskMultiple": raw_settings.get("rewardRiskMultiple", 2.0),
        "allowShort": raw_settings.get("allowShort", True),
    }
    agent = payload["agent"].copy()
    agent["id"] = str(agent.get("id") or uuid4())

    strategy_contract = strategy_contract_for(agent)
    use_trend = strategy_contract["engine"] == "trend_breakout_v1"
    if use_trend:
        result = _simulate_trend_breakout(symbol, timeframe, agent, settings, validated_candles)
        strategy_version = "trend-breakout-v1/1.0.0"
    else:
        result = _simulate_backtest(symbol, timeframe, agent, settings, validated_candles)
        strategy_version = "legacy/ema-bb-1.0"
    walk_forward = _calculate_walk_forward(symbol, timeframe, agent, settings, validated_candles, use_trend=use_trend)
    model_analysis = analyze_model(validated_candles, timeframe, settings)
    # Diagnostics: per-module robustness (trend engine only; legacy keeps prior shape).
    diagnostics: dict = {"modules": _enabled_strategy_ids(agent)}
    if use_trend:
        closed_profits = [float(t.get("profit", 0)) for t in result.get("trades", []) if "profit" in t]
        diagnostics["monteCarlo"] = _monte_carlo_summary(closed_profits)
        diagnostics["sensitivity"] = _sensitivity_grid(symbol, timeframe, agent, settings, validated_candles)
        diagnostics["excursion"] = result.get("excursionStats", {})
    warnings = list(walk_forward["warnings"])
    if use_trend:
        mc = diagnostics.get("monteCarlo", {})
        if mc.get("available") and mc.get("probProfitable", 100) < 60:
            warnings.append(f"Monte Carlo: only {mc['probProfitable']}% of resampled paths profitable — edge is fragile.")
        sens = diagnostics.get("sensitivity", {})
        if sens.get("available") and sens.get("fragile"):
            warnings.append("Sensitivity grid: profit factor swings across adjacent ATR/RR cells — do not optimize, freeze rules first.")
        exc = diagnostics.get("excursion", {})
        if exc.get("count", 0) and exc.get("losersThatReachedPlus1R", 0) > exc.get("count", 0) * 0.3:
            warnings.append(f"Excursion: {exc['losersThatReachedPlus1R']}/{exc['count']} losers reached +1R first — consider earlier partials, not wider stops.")

    if data_source in {"unknown", "mixed"}:
        warnings.append("Candle source is unknown or mixed; results are exploratory and not eligible for strategy promotion.")
    if len(validated_candles) < 200:
        warnings.append("Fewer than 200 candles: EMA200 macro bias is unstable; treat trend signals as exploratory.")
    if result["metrics"]["totalTrades"] == 0:
        warnings.append("No trades executed: strategy produced no aligned signals in this window.")
    if use_trend and result.get("regimeStats"):
        rs = result["regimeStats"]
        warnings.append(
            f"Regime gate: {rs.get('trendingBars',0)} trending bars, {rs.get('rangeBars',0)} range/chop bars blocked, "
            f"{rs.get('blockedByRegime',0)} signals vetoed by consolidation."
        )

    if walk_forward["available"] and walk_forward["averageTestExcessReturnPct"] < 0:
        warnings.append("Walk-forward test windows underperformed buy-and-hold on average.")
    if walk_forward["available"] and walk_forward["benchmarkBeatRatePct"] == 0:
        warnings.append("No out-of-sample walk-forward window beat buy-and-hold.")
    if model_analysis["available"] and model_analysis["performance"]["testAccuracyPct"] < 55:
        warnings.append("Baseline model test accuracy is still weak on the held-out slice.")
    if not model_analysis["available"]:
        warnings.extend(model_analysis["explanation"]["caveats"])

    result["validation"] = {
        "candlesChecked": len(validated_candles),
        "isSorted": True,
        "dataSource": data_source,
        "strategyVersion": strategy_version,
        "strategyContract": strategy_contract,
        "warnings": warnings,
        "diagnostics": diagnostics,
    }
    result["walkForward"] = walk_forward
    result["modelAnalysis"] = model_analysis
    result["createdAt"] = timezone.now().isoformat()
    return result


def validate_candles(candles: list[dict]) -> list[dict]:
    if not candles:
        raise ValueError("Candle data is required.")

    validated: list[dict] = []
    previous_time: datetime | None = None
    for index, candle in enumerate(candles):
        missing_keys = [key for key in ("time", "open", "high", "low", "close", "volume") if key not in candle]
        if missing_keys:
            raise ValueError(f"Candle at index {index} is missing fields: {', '.join(missing_keys)}.")

        timestamp = trade_timestamp(str(candle["time"]))
        open_price = float(candle["open"])
        high_price = float(candle["high"])
        low_price = float(candle["low"])
        close_price = float(candle["close"])
        volume = float(candle["volume"])

        if min(open_price, high_price, low_price, close_price, volume) < 0:
            raise ValueError(f"Candle at index {index} contains negative values.")
        if high_price < max(open_price, close_price) or low_price > min(open_price, close_price):
            raise ValueError(f"Candle at index {index} has inconsistent OHLC values.")
        if previous_time is not None and timestamp <= previous_time:
            raise ValueError("Candle timestamps must be strictly increasing.")

        validated.append(
            {
                "time": timestamp.isoformat(),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }
        )
        previous_time = timestamp

    return validated


def trade_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _simulate_backtest(symbol: str, timeframe: str, agent: dict, settings: dict, candles: list[dict]) -> dict:
    close_prices = [entry["close"] for entry in candles]
    ema_fast = calculate_ema(close_prices, 9)
    ema_slow = calculate_ema(close_prices, 21)
    rsi = calculate_rsi(close_prices, 14)
    _, upper_band, lower_band = calculate_bollinger_bands(close_prices, 20, 2)

    cash = settings["startingBalance"]
    quantity_held = 0.0
    entry_price = 0.0
    entry_fee = 0.0
    trades: list[dict] = []
    equity_curve: list[dict] = []
    strategies = [strategy for strategy in agent["strategies"] if strategy["enabled"]]
    bars_in_market = 0

    for index in range(30, len(candles)):
        candle = candles[index]
        buy_signal = _should_buy(index, candles, strategies, ema_fast, ema_slow, rsi, lower_band)
        sell_signal = _should_sell(index, candles, strategies, ema_fast, ema_slow, rsi, upper_band)

        if buy_signal and quantity_held == 0:
            deployable_capital = cash * settings["positionSizeFraction"]
            execution_price = candle["close"] * (1 + settings["slippageRate"])
            quantity = deployable_capital / execution_price
            notional = quantity * execution_price
            fee_paid = notional * settings["feeRate"]

            if quantity > 0 and cash >= notional + fee_paid:
                cash -= notional + fee_paid
                quantity_held = quantity
                entry_price = execution_price
                entry_fee = fee_paid
                trades.append(
                    {
                        "id": str(uuid4()),
                        "type": "buy",
                        "price": _round(execution_price),
                        "time": candle["time"],
                        "quantity": _round(quantity, 8),
                        "notional": _round(notional),
                        "feePaid": _round(fee_paid),
                        "reason": "Strategy entry signal confirmed.",
                    }
                )

        elif sell_signal and quantity_held > 0:
            execution_price = candle["close"] * (1 - settings["slippageRate"])
            notional = quantity_held * execution_price
            fee_paid = notional * settings["feeRate"]
            gross_profit = (execution_price - entry_price) * quantity_held
            net_profit = gross_profit - fee_paid - entry_fee

            cash += notional - fee_paid
            trades.append(
                {
                    "id": str(uuid4()),
                    "type": "sell",
                    "price": _round(execution_price),
                    "time": candle["time"],
                    "quantity": _round(quantity_held, 8),
                    "notional": _round(notional),
                    "feePaid": _round(fee_paid),
                    "profit": _round(net_profit),
                    "reason": "Strategy exit conditions met.",
                }
            )
            quantity_held = 0
            entry_price = 0
            entry_fee = 0

        if quantity_held > 0:
            bars_in_market += 1

        equity_curve.append(
            {
                "time": candle["time"],
                "value": _round(cash + quantity_held * candle["close"]),
            }
        )

    ending_balance = _round(cash + quantity_held * candles[-1]["close"])
    total_profit = _round(ending_balance - settings["startingBalance"])
    total_return_pct = _round((total_profit / settings["startingBalance"]) * 100)
    max_drawdown_pct = _calculate_max_drawdown(equity_curve)
    sell_trades = [trade for trade in trades if trade["type"] == "sell"]
    winning_trades = [trade for trade in sell_trades if trade.get("profit", 0) > 0]
    total_trades = len(sell_trades)
    win_rate = _round((len(winning_trades) / total_trades) * 100) if total_trades else 0
    sharpe_ratio = _calculate_sharpe_ratio(equity_curve, timeframe)
    benchmark = _calculate_buy_and_hold(candles, settings)
    profit_factor = _calculate_profit_factor(sell_trades)
    expectancy = _calculate_expectancy(sell_trades)
    exposure_time_pct = _round((bars_in_market / max(1, len(equity_curve))) * 100)

    return {
        "id": str(uuid4()),
        "symbol": symbol,
        "timeframe": timeframe,
        "agent": agent,
        "settings": settings,
        "metrics": {
            "totalReturnPct": total_return_pct,
            "totalProfit": total_profit,
            "maxDrawdownPct": max_drawdown_pct,
            "sharpeRatio": sharpe_ratio,
            "winRate": win_rate,
            "totalTrades": total_trades,
            "endingBalance": ending_balance,
            "benchmarkReturnPct": benchmark["returnPct"],
            "benchmarkEndingBalance": benchmark["endingBalance"],
            "excessReturnPct": _round(total_return_pct - benchmark["returnPct"]),
            "profitFactor": profit_factor,
            "expectancy": expectancy,
            "exposureTimePct": exposure_time_pct,
        },
        "equityCurve": equity_curve,
        "trades": trades,
    }


def _spread_half_cost(symbol: str, reference_price: float, spread_pips_override=None) -> float:
    """Half-spread in price units. Crypto uses absolute units, FX uses pip size."""
    from .trend_breakout import classify_symbol

    spec = classify_symbol(symbol, reference_price)
    if spread_pips_override is not None:
        sp = float(spread_pips_override)
    else:
        try:
            from .market_data import FOREX_SPREADS_PIPS
            from .market_data import normalize_symbol as _norm

            sp = float(FOREX_SPREADS_PIPS.get(_norm(symbol), 1.2))
        except Exception:
            sp = 1.2
    if spec["is_crypto"]:
        # For crypto, spreadPips is an absolute price spread (e.g. $2 on BTC).
        return sp / 2.0
    return (sp * spec["pip_size"]) / 2.0


def _resample_higher_timeframe(candles: list[dict], factor: int = 4) -> list[dict]:
    """Aggregate completed lower-timeframe bars into higher-timeframe bars (e.g. 4x = 15m->1h or 1h->4h) with zero lookahead."""
    if factor <= 1 or len(candles) < factor:
        return candles
    usable = (len(candles) // factor) * factor
    if usable < factor:
        return []
    out: list[dict] = []
    for i in range(0, usable, factor):
        chunk = candles[i : i + factor]
        out.append({
            "time": chunk[-1]["time"],
            "open": float(chunk[0]["open"]),
            "high": max(float(c["high"]) for c in chunk),
            "low": min(float(c["low"]) for c in chunk),
            "close": float(chunk[-1]["close"]),
            "volume": sum(float(c.get("volume", 0.0)) for c in chunk),
        })
    return out


def _simulate_trend_breakout(symbol: str, timeframe: str, agent: dict, settings: dict, candles: list[dict]) -> dict:
    """Realistic trend/breakout simulation. Same rules as the live scanner.

    - Signal on completed bar i via trend_breakout.single_timeframe_signal
    - Entry at NEXT bar open (no lookahead) with spread + slippage
    - ATR stop (default 1.5x) and 2R target, intrabar SL-first handling
    - Risk-based sizing: min(capital fraction, riskPct/SL distance)
    - Longs + shorts (shorts optional via allowShort), fees on both legs
    """
    from .trend_breakout import STRATEGY_VERSION, classify_symbol, single_timeframe_signal

    starting = float(settings.get("startingBalance", 10000))
    fee_rate = float(settings.get("feeRate", 0.001))
    slip = float(settings.get("slippageRate", 0.0005))
    size_frac = float(settings.get("positionSizeFraction", 0.95))
    risk_pct = float(settings.get("riskPct", 0.01))
    atr_mult = float(settings.get("atrStopMultiplier", 1.5))
    rr_mult = float(settings.get("rewardRiskMultiple", 2.0))
    allow_short = bool(settings.get("allowShort", True))
    spread_override = settings.get("spreadPips")

    norm_sym = symbol.replace("/", "").replace("_", "").upper()
    spec = classify_symbol(norm_sym, candles[-1]["close"])
    decimals = spec["decimals"]
    half_spread = _spread_half_cost(norm_sym, candles[-1]["close"], spread_override)

    cash = starting
    position = None  # {side: long|short, qty, entry, sl, tp, entry_fee, entry_time}
    trades: list[dict] = []
    equity_curve: list[dict] = []
    bars_in_market = 0
    closed_round_trips: list[dict] = []  # exit trades with profit, for metrics
    trending_bars = 0
    range_bars = 0
    blocked_by_regime = 0

    warmup = max(50, min(60, len(candles) - 1))
    if len(candles) <= warmup + 1:
        warmup = max(30, len(candles) - 2)

    # Accounting model:
    # - Long (spot proxy): cash is spent at entry, returned at exit.
    #   Equity = cash + qty * current_price.
    # - Short (CFD proxy): cash is NOT spent at entry (only entry fee is paid).
    #   Notional must fit within cash*size_frac as a margin proxy.
    #   Equity = cash + qty * (entry - current_price).

    for sig_idx in range(warmup, len(candles) - 1):
        exe_bar = candles[sig_idx + 1]
        # Pure signal on completed bars only (no lookahead into exe_bar).
        try:
            sig = single_timeframe_signal(candles[: sig_idx + 1], symbol=norm_sym, include_votes=False)
        except Exception:
            continue
        if sig["regime"] == "trending":
            trending_bars += 1
        else:
            range_bars += 1

        exe_open = float(exe_bar["open"])
        exe_high = float(exe_bar["high"])
        exe_low = float(exe_bar["low"])

        # 1) Manage open position on execution bar (SL-first, then TP).
        if position is not None:
            # Track excursion before exit checks (intrabar high/low).
            if position["side"] == "long":
                position["mfe"] = max(position.get("mfe", 0.0), exe_high - position["entry"])
                position["mae"] = min(position.get("mae", 0.0), exe_low - position["entry"])
            else:
                position["mfe"] = max(position.get("mfe", 0.0), position["entry"] - exe_low)
                position["mae"] = min(position.get("mae", 0.0), position["entry"] - exe_high)
            exited = None
            exit_reason = ""
            if position["side"] == "long":
                sl_hit = exe_low <= position["sl"]
                tp_hit = exe_high >= position["tp"]
                if sl_hit:
                    exited = position["sl"] - half_spread - position["sl"] * slip
                    exit_reason = f"stop-loss {atr_mult}x ATR (trend-breakout-v1 {STRATEGY_VERSION})"
                elif tp_hit:
                    exited = position["tp"] - half_spread - position["tp"] * slip
                    exit_reason = f"take-profit {rr_mult}R (trend-breakout-v1 {STRATEGY_VERSION})"
            else:
                sl_hit = exe_high >= position["sl"]
                tp_hit = exe_low <= position["tp"]
                if sl_hit:
                    exited = position["sl"] + half_spread + position["sl"] * slip
                    exit_reason = f"stop-loss {atr_mult}x ATR (trend-breakout-v1 {STRATEGY_VERSION})"
                elif tp_hit:
                    exited = position["tp"] + half_spread + position["tp"] * slip
                    exit_reason = f"take-profit {rr_mult}R (trend-breakout-v1 {STRATEGY_VERSION})"
            # Opposite-signal exit at open (before SL/TP if both? SL takes precedence
            # only if already hit; otherwise opposite signal closes at open).
            opposite = (position["side"] == "long" and sig.get("side") == "sell") or (
                position["side"] == "short" and sig.get("side") == "buy"
            )
            if exited is None and opposite:
                if position["side"] == "long":
                    exited = exe_open - half_spread - exe_open * slip
                else:
                    exited = exe_open + half_spread + exe_open * slip
                exit_reason = f"opposite signal (trend-breakout-v1 {STRATEGY_VERSION})"
            if exited is not None:
                qty = position["qty"]
                entry = position["entry"]
                exit_notional = qty * exited
                exit_fee = exit_notional * fee_rate
                if position["side"] == "long":
                    gross = (exited - entry) * qty
                    cash += exit_notional - exit_fee  # return spent capital + P&L minus fee
                    exit_type = "sell"
                else:
                    gross = (entry - exited) * qty
                    # CFD short: cash was never spent; add net P&L minus fees.
                    cash = cash + gross - exit_fee
                    exit_type = "buy"
                net = gross - exit_fee - position["entry_fee"]
                sl_d = position.get("sl_dist") or abs(position["entry"] - position["sl"]) or 1.0
                exit_trade = {
                    "id": str(uuid4()),
                    "type": exit_type,
                    "price": _round(exited),
                    "time": exe_bar["time"],
                    "quantity": _round(qty, 8),
                    "notional": _round(exit_notional),
                    "feePaid": _round(exit_fee),
                    "profit": _round(net),
                    "reason": exit_reason,
                    "mfe": _round(position.get("mfe", 0.0)),
                    "mae": _round(position.get("mae", 0.0)),
                    "mfeR": _round(position.get("mfe", 0.0) / sl_d) if sl_d else 0,
                    "maeR": _round(position.get("mae", 0.0) / sl_d) if sl_d else 0,
                }
                trades.append(exit_trade)
                closed_round_trips.append(exit_trade)
                position = None
            elif settings.get("breakevenAt1R", True) and not position.get("be_moved"):
                # Automated +1R Breakeven Protection (matches live TradeMonitorService.auto_manage_open_positions)
                sl_d = position.get("sl_dist") or 0.0
                if sl_d > 0 and position.get("mfe", 0.0) >= sl_d * 1.0:
                    if position["side"] == "long":
                        position["sl"] = max(position["sl"], position["entry"] + half_spread + position["entry"] * slip)
                    else:
                        position["sl"] = min(position["sl"], position["entry"] - half_spread - position["entry"] * slip)
                    position["be_moved"] = True

        # 2) New entry at execution-bar open if flat and signal aligned (with HTF 4x structural check).
        if position is None:
            side = sig.get("side")  # buy/sell or None (vetoed)
            if side is not None and len(candles[: sig_idx + 1]) >= 80:
                from .trend_breakout import _calculate_ema as _htf_ema, h4_bias as _htf_bias

                htf_bars = _resample_higher_timeframe(candles[: sig_idx + 1], factor=4)
                if len(htf_bars) >= 20:
                    htf_closes = [c["close"] for c in htf_bars]
                    htf_e50 = _htf_ema(htf_closes, min(50, max(2, len(htf_closes) - 1)))[-1]
                    htf_e200 = _htf_ema(htf_closes, min(200, max(2, len(htf_closes) - 1)))[-1]
                    htf_macro = _htf_bias(htf_closes[-1], htf_e50, htf_e200)
                    if (side == "buy" and htf_macro == "BEARISH") or (side == "sell" and htf_macro == "BULLISH"):
                        side = None
            if side is None:
                if sig.get("direction") in ("long", "short"):
                    blocked_by_regime += 1
                # equity mark
                equity_curve.append({"time": exe_bar["time"], "value": _round(cash)})
                continue
            if side == "sell" and not allow_short:
                equity_curve.append({"time": exe_bar["time"], "value": _round(cash)})
                continue
            atr_dist = float(sig.get("atr_distance") or 0.0)
            # Re-scale ATR distance with configured multiplier (signal used default 1.5x).
            # sig atr_distance already = max(atr*1.5, min). Rescale proportionally.
            if atr_mult != 1.5 and atr_dist:
                # Approximate: back out base then re-apply. base = dist/1.5 when dist > min.
                atr_dist = atr_dist / 1.5 * atr_mult
            if not atr_dist or atr_dist <= 0:
                equity_curve.append({"time": exe_bar["time"], "value": _round(cash)})
                continue
            if side == "buy":
                entry_px = exe_open + half_spread + exe_open * slip
                sl = entry_px - atr_dist
                tp = entry_px + atr_dist * rr_mult
            else:
                entry_px = exe_open - half_spread - exe_open * slip
                sl = entry_px + atr_dist
                tp = entry_px - atr_dist * rr_mult
            if entry_px <= 0:
                equity_curve.append({"time": exe_bar["time"], "value": _round(cash)})
                continue
            equity_now = cash  # flat, so equity == cash
            risk_capital = equity_now * risk_pct
            qty_risk = risk_capital / atr_dist if atr_dist else 0
            qty_cap = (equity_now * size_frac) / entry_px if entry_px else 0
            qty = min(qty_risk, qty_cap)
            if qty <= 0:
                equity_curve.append({"time": exe_bar["time"], "value": _round(cash)})
                continue
            notional = qty * entry_px
            entry_fee = notional * fee_rate
            if side == "buy":
                if cash < notional + entry_fee or qty <= 0:
                    equity_curve.append({"time": exe_bar["time"], "value": _round(cash)})
                    continue
                cash -= notional + entry_fee
                entry_type = "buy"
            else:
                # Short CFD: require margin proxy, don't spend cash.
                if notional > cash * size_frac:
                    # Scale down to margin limit.
                    qty = (cash * size_frac) / entry_px
                    notional = qty * entry_px
                    entry_fee = notional * fee_rate
                if qty <= 0:
                    equity_curve.append({"time": exe_bar["time"], "value": _round(cash)})
                    continue
                cash -= entry_fee  # pay entry fee only
                entry_type = "sell"
            position = {
                "side": "long" if side == "buy" else "short",
                "qty": qty,
                "entry": entry_px,
                "sl": sl,
                "tp": tp,
                "sl_dist": atr_dist,
                "entry_fee": entry_fee,
                "notional": notional,
                "entry_time": exe_bar["time"],
                "mfe": 0.0,
                "mae": 0.0,
            }
            trades.append(
                {
                    "id": str(uuid4()),
                    "type": entry_type,
                    "price": _round(entry_px),
                    "time": exe_bar["time"],
                    "quantity": _round(qty, 8),
                    "notional": _round(notional),
                    "feePaid": _round(entry_fee),
                    "reason": f"trend-breakout-v1 {STRATEGY_VERSION} {sig['macro_bias']} {sig['direction']} conf {sig['confidence']}",
                }
            )
            bars_in_market += 1
            # Mark equity right after entry at execution close.
            close_px = float(exe_bar["close"])
            if position["side"] == "long":
                eq = cash + position["qty"] * close_px
            else:
                eq = cash + position["qty"] * (position["entry"] - close_px)
            equity_curve.append({"time": exe_bar["time"], "value": _round(eq)})
        else:
            bars_in_market += 1
            close_px = float(exe_bar["close"])
            if position["side"] == "long":
                eq = cash + position["qty"] * close_px
            else:
                eq = cash + position["qty"] * (position["entry"] - close_px)
            equity_curve.append({"time": exe_bar["time"], "value": _round(eq)})

    # Close any open position at final close (realistic: market-on-close, with costs).
    if position is not None:
        last = candles[-1]
        px = float(last["close"])
        qty = position["qty"]
        entry = position["entry"]
        if position["side"] == "long":
            exited = px - half_spread - px * slip
            exit_notional = qty * exited
            exit_fee = exit_notional * fee_rate
            gross = (exited - entry) * qty
            cash += exit_notional - exit_fee
            exit_type = "sell"
        else:
            exited = px + half_spread + px * slip
            exit_notional = qty * exited
            exit_fee = exit_notional * fee_rate
            gross = (entry - exited) * qty
            cash = cash + gross - exit_fee
            exit_type = "buy"
        net = gross - exit_fee - position["entry_fee"]
        sl_d = position.get("sl_dist") or abs(position["entry"] - position["sl"]) or 1.0
        exit_trade = {
            "id": str(uuid4()),
            "type": exit_type,
            "price": _round(exited),
            "time": last["time"],
            "quantity": _round(qty, 8),
            "notional": _round(exit_notional),
            "feePaid": _round(exit_fee),
            "profit": _round(net),
            "reason": f"end of data (trend-breakout-v1 {STRATEGY_VERSION})",
            "mfe": _round(position.get("mfe", 0.0)),
            "mae": _round(position.get("mae", 0.0)),
            "mfeR": _round(position.get("mfe", 0.0) / sl_d) if sl_d else 0,
            "maeR": _round(position.get("mae", 0.0) / sl_d) if sl_d else 0,
        }
        trades.append(exit_trade)
        closed_round_trips.append(exit_trade)
        position = None
        if equity_curve:
            equity_curve[-1] = {"time": last["time"], "value": _round(cash)}

    ending_balance = _round(cash)
    total_profit = _round(ending_balance - starting)
    total_return_pct = _round((total_profit / starting) * 100) if starting else 0
    max_drawdown_pct = _calculate_max_drawdown(equity_curve)
    winning = [t for t in closed_round_trips if t.get("profit", 0) > 0]
    total_trades = len(closed_round_trips)
    win_rate = _round((len(winning) / total_trades) * 100) if total_trades else 0
    sharpe_ratio = _calculate_sharpe_ratio(equity_curve, timeframe)
    benchmark = _calculate_buy_and_hold(candles, settings)
    profit_factor = _calculate_profit_factor(closed_round_trips)
    expectancy = _calculate_expectancy(closed_round_trips)
    exposure = _round((bars_in_market / max(1, len(equity_curve))) * 100)
    excursion = _summarize_excursions(closed_round_trips)

    return {
        "id": str(uuid4()),
        "symbol": symbol,
        "timeframe": timeframe,
        "agent": agent,
        "settings": settings,
        "metrics": {
            "totalReturnPct": total_return_pct,
            "totalProfit": total_profit,
            "maxDrawdownPct": max_drawdown_pct,
            "sharpeRatio": sharpe_ratio,
            "winRate": win_rate,
            "totalTrades": total_trades,
            "endingBalance": ending_balance,
            "benchmarkReturnPct": benchmark["returnPct"],
            "benchmarkEndingBalance": benchmark["endingBalance"],
            "excessReturnPct": _round(total_return_pct - benchmark["returnPct"]),
            "profitFactor": profit_factor,
            "expectancy": expectancy,
            "exposureTimePct": exposure,
        },
        "equityCurve": equity_curve,
        "trades": trades,
        "regimeStats": {
            "trendingBars": trending_bars,
            "rangeBars": range_bars,
            "blockedByRegime": blocked_by_regime,
            "strategyVersion": STRATEGY_VERSION,
        },
        "excursionStats": excursion,
    }


def _summarize_excursions(closed_trades: list[dict]) -> dict:
    if not closed_trades:
        return {
            "avgMfeR": 0, "avgMaeR": 0, "winnersThatWentMinus1R": 0,
            "losersThatReachedPlus1R": 0, "count": 0,
        }
    mfe_rs = [float(t.get("mfeR", 0) or 0) for t in closed_trades]
    mae_rs = [float(t.get("maeR", 0) or 0) for t in closed_trades]
    winners = [t for t in closed_trades if t.get("profit", 0) > 0]
    losers = [t for t in closed_trades if t.get("profit", 0) <= 0]
    w_bad = sum(1 for t in winners if float(t.get("maeR", 0) or 0) <= -1.0)
    l_good = sum(1 for t in losers if float(t.get("mfeR", 0) or 0) >= 1.0)
    return {
        "avgMfeR": _round(sum(mfe_rs) / len(mfe_rs)),
        "avgMaeR": _round(sum(mae_rs) / len(mae_rs)),
        "winnersThatWentMinus1R": w_bad,
        "losersThatReachedPlus1R": l_good,
        "count": len(closed_trades),
    }


def _monte_carlo_summary(profits: list[float], n_paths: int = 500, seed: int = 7) -> dict:
    """Bootstrap resample of trade profits. Fast, no re-simulation."""
    import random

    if len(profits) < 5:
        return {
            "available": False, "paths": 0,
            "medianProfit": 0, "p5Profit": 0, "probProfitable": 0,
            "note": "Need at least 5 closed trades for Monte Carlo.",
        }
    rng = random.Random(seed)
    totals = []
    for _ in range(n_paths):
        totals.append(sum(rng.choice(profits) for _ in profits))
    totals.sort()
    median = totals[n_paths // 2]
    p5 = totals[int(n_paths * 0.05)]
    prob = sum(1 for t in totals if t > 0) / n_paths
    return {
        "available": True, "paths": n_paths,
        "medianProfit": _round(median), "p5Profit": _round(p5),
        "probProfitable": _round(prob * 100),
        "note": "Resampled trade order with replacement; costs already in profits.",
    }


def _sensitivity_grid(symbol: str, timeframe: str, agent: dict, settings: dict, candles: list[dict]) -> dict:
    """Small ATR/RR grid on the same data. Skipped on large windows for speed."""
    if len(candles) > 600:
        return {"available": False, "rows": [], "note": "Skipped: >600 candles (too slow). Narrow the window."}
    combos = [(1.0, 1.5), (1.5, 2.0), (2.0, 2.0), (1.5, 1.5)]
    rows = []
    for atr_m, rr_m in combos:
        s = dict(settings)
        s["atrStopMultiplier"] = atr_m
        s["rewardRiskMultiple"] = rr_m
        try:
            r = _simulate_trend_breakout(symbol, timeframe, agent, s, candles)
            rows.append({
                "atrStopMultiplier": atr_m, "rewardRiskMultiple": rr_m,
                "totalReturnPct": r["metrics"]["totalReturnPct"],
                "totalTrades": r["metrics"]["totalTrades"],
                "profitFactor": r["metrics"]["profitFactor"],
                "maxDrawdownPct": r["metrics"]["maxDrawdownPct"],
            })
        except Exception as exc:
            rows.append({"atrStopMultiplier": atr_m, "rewardRiskMultiple": rr_m, "error": str(exc)})
    base_pf = next((x.get("profitFactor", 0) for x in rows if x.get("atrStopMultiplier") == 1.5), 0)
    fragile = all(abs((x.get("profitFactor", 0) or 0) - base_pf) > 0.5 for x in rows if x.get("atrStopMultiplier") != 1.5)
    return {
        "available": True, "rows": rows,
        "fragile": fragile,
        "note": "If profit flips sign across adjacent cells, the edge is parameter-fragile.",
    }


def _simulate_for_engine(symbol: str, timeframe: str, agent: dict, settings: dict, candles: list[dict], use_trend: bool) -> dict:
    if use_trend:
        return _simulate_trend_breakout(symbol, timeframe, agent, settings, candles)
    return _simulate_backtest(symbol, timeframe, agent, settings, candles)


def _calculate_walk_forward(symbol: str, timeframe: str, agent: dict, settings: dict, candles: list[dict], use_trend: bool = False) -> dict:
    if len(candles) < MIN_WALK_FORWARD_CANDLES:
        return {
            "available": False,
            "verdict": "insufficient_data",
            "trainCandlesPerWindow": 0,
            "testCandlesPerWindow": 0,
            "windowCount": 0,
            "benchmarkBeatRatePct": 0,
            "profitableWindowPct": 0,
            "averageTestReturnPct": 0,
            "averageTestBenchmarkReturnPct": 0,
            "averageTestExcessReturnPct": 0,
            "averageTestSharpeRatio": 0,
            "averageTestDrawdownPct": 0,
            "warnings": [f"Walk-forward validation needs at least {MIN_WALK_FORWARD_CANDLES} candles."],
            "windows": [],
        }

    train_size = max(MIN_BACKTEST_CANDLES, int(len(candles) * WALK_FORWARD_TRAIN_FRACTION))
    test_size = max(MIN_BACKTEST_CANDLES, int(len(candles) * WALK_FORWARD_TEST_FRACTION))
    max_start = len(candles) - train_size - test_size

    if train_size < MIN_BACKTEST_CANDLES or test_size < MIN_BACKTEST_CANDLES or max_start < 0:
        return {
            "available": False,
            "verdict": "insufficient_data",
            "trainCandlesPerWindow": max(train_size, 0),
            "testCandlesPerWindow": max(test_size, 0),
            "windowCount": 0,
            "benchmarkBeatRatePct": 0,
            "profitableWindowPct": 0,
            "averageTestReturnPct": 0,
            "averageTestBenchmarkReturnPct": 0,
            "averageTestExcessReturnPct": 0,
            "averageTestSharpeRatio": 0,
            "averageTestDrawdownPct": 0,
            "warnings": ["Walk-forward validation could not find a train/test split for this candle window."],
            "windows": [],
        }

    start_indices = _walk_forward_start_indices(len(candles), train_size, test_size)
    windows = []
    for index, start in enumerate(start_indices, start=1):
        train_slice = candles[start : start + train_size]
        test_slice = candles[start + train_size : start + train_size + test_size]
        train_result = _simulate_for_engine(symbol, timeframe, agent, settings, train_slice, use_trend)
        test_result = _simulate_for_engine(symbol, timeframe, agent, settings, test_slice, use_trend)
        test_metrics = test_result["metrics"]
        windows.append(
            {
                "index": index,
                "trainStart": train_slice[0]["time"],
                "trainEnd": train_slice[-1]["time"],
                "testStart": test_slice[0]["time"],
                "testEnd": test_slice[-1]["time"],
                "trainReturnPct": train_result["metrics"]["totalReturnPct"],
                "trainBenchmarkReturnPct": train_result["metrics"]["benchmarkReturnPct"],
                "testReturnPct": test_metrics["totalReturnPct"],
                "testBenchmarkReturnPct": test_metrics["benchmarkReturnPct"],
                "testExcessReturnPct": test_metrics["excessReturnPct"],
                "testSharpeRatio": test_metrics["sharpeRatio"],
                "testMaxDrawdownPct": test_metrics["maxDrawdownPct"],
                "testTotalTrades": test_metrics["totalTrades"],
            }
        )

    benchmark_beats = sum(1 for window in windows if window["testExcessReturnPct"] >= 0)
    profitable_windows = sum(1 for window in windows if window["testReturnPct"] > 0)
    average_test_return = _round(sum(window["testReturnPct"] for window in windows) / len(windows))
    average_test_benchmark = _round(sum(window["testBenchmarkReturnPct"] for window in windows) / len(windows))
    average_test_excess = _round(sum(window["testExcessReturnPct"] for window in windows) / len(windows))
    average_test_sharpe = _round(sum(window["testSharpeRatio"] for window in windows) / len(windows))
    average_test_drawdown = _round(sum(window["testMaxDrawdownPct"] for window in windows) / len(windows))
    benchmark_beat_rate = _round((benchmark_beats / len(windows)) * 100)
    profitable_window_rate = _round((profitable_windows / len(windows)) * 100)

    warnings = []
    if len(windows) < 2:
        warnings.append("Walk-forward validation produced only one out-of-sample window.")

    return {
        "available": True,
        "verdict": _walk_forward_verdict(average_test_excess, benchmark_beat_rate, profitable_window_rate),
        "trainCandlesPerWindow": train_size,
        "testCandlesPerWindow": test_size,
        "windowCount": len(windows),
        "benchmarkBeatRatePct": benchmark_beat_rate,
        "profitableWindowPct": profitable_window_rate,
        "averageTestReturnPct": average_test_return,
        "averageTestBenchmarkReturnPct": average_test_benchmark,
        "averageTestExcessReturnPct": average_test_excess,
        "averageTestSharpeRatio": average_test_sharpe,
        "averageTestDrawdownPct": average_test_drawdown,
        "warnings": warnings,
        "windows": windows,
    }


def _walk_forward_start_indices(total_candles: int, train_size: int, test_size: int) -> list[int]:
    max_start = total_candles - train_size - test_size
    if max_start <= 0:
        return [0]

    starts = [0]
    candidate = test_size
    while candidate <= max_start:
        starts.append(candidate)
        candidate += test_size

    if starts[-1] != max_start:
        starts.append(max_start)
    return sorted(set(starts))


def _walk_forward_verdict(average_test_excess: float, benchmark_beat_rate: float, profitable_window_rate: float) -> str:
    if average_test_excess >= 0 and benchmark_beat_rate >= 60:
        return "pass"
    if average_test_excess >= -5 or profitable_window_rate >= 50:
        return "mixed"
    return "fail"


def _should_buy(index: int, candles: list[dict], strategies: list[dict], ema_fast: list[float], ema_slow: list[float], rsi: list[float], lower_band: list[float]) -> bool:
    for strategy in strategies:
        if strategy["id"] == "trend-following":
            if ema_fast[index] > ema_slow[index] and ema_fast[index - 1] <= ema_slow[index - 1]:
                return True
        if strategy["id"] == "mean-reversion":
            if candles[index]["close"] < lower_band[index] and rsi[index] < 35:
                return True
    return False


def _should_sell(index: int, candles: list[dict], strategies: list[dict], ema_fast: list[float], ema_slow: list[float], rsi: list[float], upper_band: list[float]) -> bool:
    for strategy in strategies:
        if strategy["id"] == "trend-following":
            if ema_fast[index] < ema_slow[index] and ema_fast[index - 1] >= ema_slow[index - 1]:
                return True
        if strategy["id"] == "mean-reversion":
            if candles[index]["close"] > upper_band[index] or rsi[index] > 65:
                return True
    return False


def _calculate_max_drawdown(equity_curve: list[dict]) -> float:
    if not equity_curve:
        return 0
    peak = equity_curve[0]["value"]
    max_drawdown = 0.0
    for point in equity_curve:
        peak = max(peak, point["value"])
        if peak == 0:
            continue
        max_drawdown = max(max_drawdown, ((peak - point["value"]) / peak) * 100)
    return _round(max_drawdown)


def _calculate_sharpe_ratio(equity_curve: list[dict], timeframe: str) -> float:
    if len(equity_curve) < 2:
        return 0

    returns = []
    for index in range(1, len(equity_curve)):
        previous = equity_curve[index - 1]["value"]
        current = equity_curve[index]["value"]
        if previous == 0:
            continue
        returns.append((current - previous) / previous)
    if not returns:
        return 0

    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    standard_deviation = sqrt(variance)
    if standard_deviation == 0:
        return 0

    annualization = sqrt(TRADING_PERIODS_PER_YEAR.get(timeframe, 365))
    return _round((mean / standard_deviation) * annualization)


def _calculate_buy_and_hold(candles: list[dict], settings: dict) -> dict:
    first_close = candles[0]["close"]
    last_close = candles[-1]["close"]
    quantity = settings["startingBalance"] / first_close
    ending_balance = _round(quantity * last_close)
    return_pct = _round(((ending_balance - settings["startingBalance"]) / settings["startingBalance"]) * 100)
    return {"endingBalance": ending_balance, "returnPct": return_pct}


def _calculate_profit_factor(sell_trades: list[dict]) -> float:
    gross_profit = sum(max(trade.get("profit", 0), 0) for trade in sell_trades)
    gross_loss = abs(sum(min(trade.get("profit", 0), 0) for trade in sell_trades))
    if gross_loss == 0:
        return _round(gross_profit) if gross_profit > 0 else 0
    return _round(gross_profit / gross_loss)


def _calculate_expectancy(sell_trades: list[dict]) -> float:
    if not sell_trades:
        return 0
    return _round(sum(trade.get("profit", 0) for trade in sell_trades) / len(sell_trades))


def _round(value: float, precision: int = 4) -> float:
    return round(value, precision)
