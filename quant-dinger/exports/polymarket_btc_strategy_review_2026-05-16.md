# Polymarket BTC Strategy Review

Date: 2026-05-16
Target: [QuantDinger/polymarket_btc_strategy.py](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:1)

## Executive Summary

This file is best understood as a standalone research prototype, not a production-ready trading bot and not an engine-compatible QuantDinger strategy script.

Overall assessment:
- Idea quality: interesting
- Architecture clarity: decent for a prototype
- Production readiness: low
- Backtest credibility: low
- Live trading readiness: very low

The strategy combines six signal families, fuses them with weights, and then uses a hard trend filter based on the Polymarket price itself. That high-level concept is coherent for a prediction market, but the current implementation has several structural issues:
- live market data plumbing is unfinished
- risk controls are only partially wired
- signal fusion is not actually the final decision maker
- simulation is synthetic and biased
- the file does not integrate with the repo's script-strategy runtime

Recommended overall verdict:
- Useful as a concept note or experimental sandbox
- Not reliable enough yet for live execution
- Not suitable yet for performance claims or capital deployment

## What The Strategy Is Trying To Do

The strategy targets a 15-minute BTC up/down Polymarket contract and tries to decide whether to buy:
- `YES/UP` when it expects the market to settle bullish
- `NO/DOWN` when it expects the market to settle bearish

Core design layers:
1. Generate signals from multiple independent processors.
2. Fuse those signals with weighted voting.
3. Apply a final trend rule using the current Polymarket price.
4. Pass the trade through a basic risk gate.

The six signal processors are:
- `SpikeDetection`: detects large short-term moves in Polymarket price.
- `SentimentAnalysis`: uses Fear & Greed Index as a contrarian overlay.
- `PriceDivergence`: compares Polymarket probability against a normalized spot BTC price.
- `OrderBookImbalance`: looks for bid/ask pressure in the top of book.
- `TickVelocity`: checks fast 30s and 60s momentum.
- `DeribitPCR`: uses BTC options put/call ratio as an institutional sentiment proxy.

Fusion weights:
- Order book: `0.30`
- Tick velocity: `0.25`
- Price divergence: `0.18`
- Spike detection: `0.12`
- Deribit PCR: `0.10`
- Sentiment: `0.05`

## Strategy Logic Walkthrough

### 1. Price history and tick buffer

The strategy stores up to 100 recent prices and separately keeps a tick buffer in the velocity processor. This is enough for short-window heuristics, but it is not a true 15-minute bar model.

### 2. Signal generation

Each processor independently emits:
- direction
- score
- confidence
- metadata

This is a reasonable modular pattern and is one of the stronger parts of the file.

### 3. Signal fusion

The fusion engine sums weighted bullish and bearish scores, then emits a consensus signal if one side exceeds `min_score=40`.

Important nuance:
- the fused signal is only used as a prerequisite
- it is not the actual trade direction authority

### 4. Final decision

The true trade direction comes from the trend filter:
- if Polymarket price `> 0.60`, buy `YES`
- if Polymarket price `< 0.40`, buy `NO`
- otherwise skip

This means the strategy is effectively:
- "only trade if at least one processor is active and fusion is actionable"
- then "follow the current market probability directly"

In practice, this makes the trend filter dominant and demotes the multi-signal system into a confirmation gate rather than a real ensemble model.

### 5. Trade execution

Execution is only simulated internally:
- a `Trade` object is appended
- in simulation mode, exit price is randomly generated
- in live mode, the code only prints that an order would be placed

There is no real Polymarket order submission path in this file.

## Strengths

### 1. Clear decomposition

The strategy is easy to read and reason about. Signal processors, fusion, risk, and execution are separated into understandable blocks.

### 2. Good prototype structure

For research work, this file is organized sensibly:
- signal abstractions are reusable
- metadata is preserved
- fusion weights are explicit
- constants are centralized

### 3. Cross-domain signal idea is interesting

Using multiple signal classes from:
- market microstructure
- momentum
- derivatives sentiment
- broad crypto sentiment

is directionally sensible for a prediction-market strategy.

### 4. Pragmatic skip zone

The `0.40 - 0.60` neutral band is a good idea conceptually. In prediction markets, avoiding coin-flip territory can be more important than forcing activity.

## Critical Weaknesses

### 1. The file is not actually connected to live market data

The helper `_fetch_market_data()` currently returns `None` as a placeholder, and `run_strategy()` uses random synthetic prices instead of real Polymarket market snapshots.

Impact:
- the script does not perform real decisioning on real market state
- live mode is only a console label, not genuine live trading

Code references:
- [polymarket_btc_strategy.py:663](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:663)
- [polymarket_btc_strategy.py:911](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:911)

### 2. Signal fusion does not control the final direction

Even after building a fused signal, the strategy discards its direction and follows the price threshold instead.

Example:
- fused output may be bearish
- if current price is `0.62`, the strategy still buys `YES`

Impact:
- the six-signal architecture has less real effect than the file suggests
- the strategy description overstates how much the ensemble decides

Code references:
- [polymarket_btc_strategy.py:735](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:735)
- [polymarket_btc_strategy.py:750](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:750)

### 3. Risk engine is only partially wired

`RiskEngine.open_positions` is checked in validation, but no executed trades are added into `risk_engine.open_positions`, and exit checks are never used in the runner.

Impact:
- max open positions logic is effectively dead
- exposure control is not truly enforced
- stop-loss / take-profit logic is defined but unused in the actual strategy loop

Code references:
- [polymarket_btc_strategy.py:570](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:570)
- [polymarket_btc_strategy.py:572](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:572)
- [polymarket_btc_strategy.py:590](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:590)
- [polymarket_btc_strategy.py:801](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:801)

### 4. Simulation results are not trustworthy

The current simulation exits trades with random price moves:
- long trades get movement from `-2%` to `+8%`
- short trades get movement from `-8%` to `+2%`

That gives both sides a favorable average drift.

Impact:
- PnL output is structurally optimistic
- win rate and total PnL from this script should not be treated as evidence

Code references:
- [polymarket_btc_strategy.py:809](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:809)
- [polymarket_btc_strategy.py:812](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:812)

### 5. The divergence model is conceptually weak

The script compares Polymarket probability to a normalized spot BTC price using a fixed assumed range `$20k-$120k`.

This is a fragile transformation because:
- Polymarket contract probability is not linearly equivalent to normalized spot price
- the "correct" mapping depends on the event definition and remaining time to expiry
- fixed bounds can distort signal meaning

Impact:
- divergence may reflect bad normalization more than real mispricing

Code references:
- [polymarket_btc_strategy.py:245](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:245)

### 6. It is not a native QuantDinger strategy script

This file does not expose the repo's normal script-strategy shape:
- no `on_init(ctx)`
- no `on_bar(ctx, bar)`
- no `ctx.buy/sell/close_position`

Impact:
- you cannot directly plug it into the existing strategy runtime/backtest engine
- meaningful integration work is still required

## Medium-Risk Issues

### 1. Timeframe mismatch inside the logic

The file is branded as a 15-minute strategy, but several processors use:
- 30s velocity
- 60s velocity
- 3-period spike logic over the in-memory price history

That can be valid, but only if there is a consistent multi-timescale design. Right now it feels mixed rather than deliberately calibrated.

### 2. Data dependency fragility

The strategy relies on several external public APIs:
- Alternative.me
- Coinbase
- Deribit
- Polymarket CLOB

There is little resilience around:
- missing data
- stale data
- timestamp alignment
- rate limits
- partial failures

The processors often just return `None`, which silently changes model behavior.

### 3. Order book logic may be noisy

The order book processor only sums top-5 bid and ask sizes and uses a fixed minimum volume threshold.

Without:
- symbol-specific calibration
- spread filtering
- spoofing resistance
- market-depth normalization

this signal can be unstable.

### 4. Position sizing is trivial

Every trade uses `MAX_POSITION_SIZE = $1`.

As a safety default this is fine, but strategically it means:
- no conviction scaling
- no dynamic risk budgeting
- no liquidity-aware sizing

## Signal-By-Signal Assessment

### SpikeDetection

Pros:
- simple
- fast
- interpretable

Concerns:
- only checks a 3-step move
- no volatility normalization
- likely sensitive to noise

### SentimentAnalysis

Pros:
- easy contrarian overlay
- cached for efficiency

Concerns:
- Fear & Greed is slow-moving and broad
- weak fit for a 15-minute binary market
- likely too low-frequency for this use case

### PriceDivergence

Pros:
- tries to compare prediction price to external reference

Concerns:
- normalization model is simplistic
- event probability is not spot-price percentile

### OrderBookImbalance

Pros:
- microstructure signal can be useful in short-duration markets

Concerns:
- may be spoof-prone
- top-of-book only
- no spread or execution-cost modeling

### TickVelocity

Pros:
- good match for short-term contracts
- probably one of the more relevant processors

Concerns:
- depends on high-quality real tick data, which the current runner does not provide

### DeribitPCR

Pros:
- adds cross-market positioning context

Concerns:
- options sentiment is slow and aggregate
- weak temporal alignment with 15-minute prediction outcomes

## Readiness Assessment

### Research Readiness

Moderate.

It is useful for:
- discussing hypotheses
- prototyping architecture
- exploring which signals are worth keeping

### Backtest Readiness

Low.

Reasons:
- no real historical market replay
- no true order simulation
- no accurate fill model
- exits are random

### Paper Trading Readiness

Low.

It needs:
- real market data ingestion
- deterministic decision loop
- true position ledger
- proper exit state machine

### Live Trading Readiness

Very low.

The file currently does not place orders and does not maintain live trade state robustly enough for production use.

## Verification Notes

Checks performed:
- static code review of the full file
- syntax check with `python3 -m py_compile`
- attempted runtime invocation with `python3 QuantDinger/polymarket_btc_strategy.py --test-mode`

Runtime limitation:
- direct execution failed in this environment because `python-dotenv` is missing

Error observed:
- `ModuleNotFoundError: No module named 'dotenv'`

## Final Evaluation

Overall score by category:
- Strategy concept: `7/10`
- Implementation quality as prototype: `6/10`
- Quantitative rigor: `4/10`
- Risk control wiring: `3/10`
- Backtest validity: `2/10`
- Live trading readiness: `1/10`

Bottom line:
- The idea is promising enough to continue researching.
- The current code should not be used as evidence of profitability.
- Before any serious testing, the next step should be converting it into a real engine-compatible strategy or a properly wired standalone executor with real data, real state, and deterministic simulation.

## Recommended Next Steps

1. Decide the target architecture.
   Either convert this into a QuantDinger `on_init/on_bar` script, or build it as a real standalone Polymarket executor. Do not keep it half-way between both.

2. Replace the random simulator.
   Use recorded Polymarket market history and deterministic fills.

3. Make fusion truly matter.
   Either let fusion determine direction, or explicitly redefine the strategy as "trend-led with signal confirmation".

4. Wire risk state correctly.
   Track open positions, exits, stop-loss, take-profit, and cooldown explicitly.

5. Rework the divergence model.
   Compare Polymarket price to an event-aware reference, not a fixed normalized BTC range.

6. Add observability.
   Log which processors fired, which were missing, and why a trade was accepted or blocked.
