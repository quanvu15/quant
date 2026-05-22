# Polymarket BTC Strategy Re-Evaluation From Upstream Repo

Date: 2026-05-16
Upstream repo reviewed: `aulekator/Polymarket-BTC-15-Minute-Trading-Bot`
Reference local extracted file: [QuantDinger/polymarket_btc_strategy.py](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py:1)

## Executive Verdict

After reviewing the upstream codebase instead of only the extracted local file, the strategy should be re-rated upward on concept and partial implementation quality, but still not treated as a production-ready bot in the strict sense.

Updated overall assessment:
- Strategy concept: good
- Signal design: materially better than the local extracted file suggests
- System ambition: high
- Engineering consistency: mixed
- Production readiness: moderate at best, not high
- Backtest / evaluation credibility: still weak

The upstream repo is not "just a toy script". It contains:
- a larger Nautilus/Polymarket integration path
- multiple signal processors with more careful reasoning
- a real risk/execution/monitoring scaffold
- a late-window trading thesis that is clearer than the local extracted file

But the README still overstates maturity. There are meaningful gaps between:
- documented architecture
- implemented behavior
- tested reliability

Bottom line:
- The upstream project is a serious prototype / semi-built system
- not a fake repo
- but also not yet a clean, validated, production-grade trading stack

## What Changed In My Assessment

Compared with the first review based only on the local extracted file:

1. The divergence logic is much better upstream.
   The upstream processor explicitly rejects the naive "probability vs BTC dollar price" comparison and replaces it with a more defensible momentum/mispricing framework.

2. The core strategy thesis is clearer upstream.
   The real bot logic in `bot.py` explains that the actual edge is not early prediction, but late-window trend reading near market resolution.

3. The architecture is broader than the extracted file implied.
   There is meaningful scaffolding for:
   - risk tracking
   - execution
   - monitoring
   - learning hooks
   - Redis mode switching
   - order-book and tick-velocity signals

4. However, maturity is still overstated.
   README language such as "production-grade" is stronger than the actual quality bar demonstrated by the repo.

## Core Trading Thesis In The Upstream Repo

The real strategic idea is:

- do not trade early in the 15-minute market when price is near `0.50`
- wait until late in the interval, around minute `13-14`
- treat the Polymarket probability itself as the strongest summary of the near-resolved outcome
- use other signals as context / confirmation
- only trade when the market already shows a sufficiently strong directional lean

This late-window thesis appears in [bot.py](/tmp/tmp.ahZSWNATbU/repo/bot.py:707) and [bot.py](/tmp/tmp.ahZSWNATbU/repo/bot.py:906).

Practical rule:
- if YES price `> 0.60`, buy YES
- if YES price `< 0.40`, buy NO
- otherwise skip

That is a very different claim from "predict BTC direction from diverse signals from scratch".
It is more like:
- wait until the market is already telling you something useful
- avoid coin-flip territory
- use microstructure and external context as supplemental evidence

This is a more coherent strategy than the local simplified file initially suggested.

## Stronger Parts Of The Upstream Design

### 1. Divergence processor is fixed conceptually

The upstream divergence processor explicitly says:
- probability and dollar price are incomparable
- do not subtract them directly
- instead compare Polymarket pricing against spot momentum / probability extremes

See [divergence_processor.py](/tmp/tmp.ahZSWNATbU/repo/core/strategy_brain/signal_processors/divergence_processor.py:1).

This is a major improvement over the local extracted file's simplistic normalization model.

### 2. Tick velocity and orderbook signals fit the use case

For a 15-minute binary market, the most relevant edge is often:
- short-horizon order flow
- velocity in the market's own probability
- liquidity imbalance

The upstream repo includes:
- `TickVelocityProcessor`
- `OrderBookImbalanceProcessor`
- `DeribitPCRProcessor`

This makes the strategy more plausible as a short-duration prediction-market bot than the simplified local file did.

### 3. The late-window trade thesis is internally consistent

The strongest part of the repo is not the multi-signal ensemble itself. It is the late-window execution thesis in [bot.py](/tmp/tmp.ahZSWNATbU/repo/bot.py:708):

- trade at minute `13-14`
- use price itself as the final verdict
- avoid the `0.40-0.60` zone

This is actually a reasonable market-structure hypothesis.

### 4. Real scaffolding exists

Unlike the extracted local file, the upstream repo does contain real modules for:
- risk engine
- execution engine
- Polymarket client
- performance tracking
- Grafana exporter
- learning hooks

So this is not just a single demo script pretending to be a system.

## Where The Upstream Repo Is Still Weak

### 1. Fusion is still mostly context, not the real trade gate

Even upstream, the fused signal is not the final authority. The code says this explicitly:
- fusion is informational context
- trend gate is the real filter

See [bot.py](/tmp/tmp.ahZSWNATbU/repo/bot.py:889) and [bot.py](/tmp/tmp.ahZSWNATbU/repo/bot.py:907).

Implication:
- the system is not truly "ensemble-driven"
- it is trend-led with contextual confirmation

That is not necessarily bad, but README messaging should be clearer about it.

### 2. README and repo contents are inconsistent

There are clear documentation mismatches:
- README tells users to run `python run_bot.py --test-mode`, but `run_bot.py` does not exist
- README references `.env.example`, but that file is not present in the cloned repo snapshot
- README presents a polished structure that does not fully match the actual top-level files

References:
- README command mention [README.md](/tmp/tmp.ahZSWNATbU/repo/README.md:151)
- actual runner present: [15m_bot_runner.py](/tmp/tmp.ahZSWNATbU/repo/15m_bot_runner.py:1)

This hurts trust and is a real maintainability issue.

### 3. Tests are not trustworthy enough as evidence

There are signs that tests are stale or inconsistent with current risk settings.

Example:
- `execution/test_execution.py` validates a `$50` position as acceptable
- but `risk_engine.py` defaults to `$1 max position size`

References:
- expected valid `$50`: [execution/test_execution.py](/tmp/tmp.ahZSWNATbU/repo/execution/test_execution.py:48)
- actual max `$1`: [execution/risk_engine.py](/tmp/tmp.ahZSWNATbU/repo/execution/risk_engine.py:68)

That means the test layer is not a reliable proof of correctness.

### 4. Some "production" paths are still placeholder or incomplete

Examples:
- `PolymarketClient.get_btc_market()` is explicitly marked not fully implemented
- some adapters or providers still contain placeholder behavior
- several auxiliary data sources fail open by returning `None`

Reference:
- [execution/polymarket_client.py](/tmp/tmp.ahZSWNATbU/repo/execution/polymarket_client.py:135)

This is normal for a prototype, but inconsistent with a strong "production-grade" claim.

### 5. Paper trading remains structurally optimistic

Even in the upstream bot, paper trading still simulates exits with asymmetric random movement:
- bullish signal gets movement from `-2%` to `+8%`
- bearish signal gets movement from `-8%` to `+2%`

See [bot.py](/tmp/tmp.ahZSWNATbU/repo/bot.py:983).

This means paper-trade win rate and PnL are still not credible as validation.

### 6. System complexity is higher than actual verification coverage

The repo contains many moving parts:
- Nautilus integration
- Redis control
- Grafana
- live execution
- external data sources
- patches

But there is not enough high-confidence evidence that the entire chain has been exercised robustly under realistic conditions.

## Assessment Of The Signal Stack

### SpikeDetection

Upstream version is clearly improved.

It now distinguishes:
- MA deviation mean reversion
- short-term velocity continuation

This is much more thoughtful than the simplified local file.

Reference:
- [spike_detector.py](/tmp/tmp.ahZSWNATbU/repo/core/strategy_brain/signal_processors/spike_detector.py:1)

Assessment: solid prototype logic.

### SentimentAnalysis

Still relatively weak for a 15-minute market.
Fear & Greed is too slow-moving to be a primary edge here, so its low weight is sensible.

Assessment: okay as low-weight context, not a core signal.

### PriceDivergence

This is one of the biggest upstream improvements.
The conceptual framing is much more defensible.

Assessment: useful and substantially less naive than the extracted local version.

### OrderBookImbalance

Potentially valuable, especially in a late-window market where local liquidity pressure matters.
Still vulnerable to spoofing/noise, but directionally appropriate.

Assessment: relevant, but execution-quality dependent.

### TickVelocity

Probably one of the strongest signals in the whole stack for this use case.
If the tick data is good, this is highly aligned with the market microstructure.

Assessment: strong fit.

### DeribitPCR

Interesting context signal, but likely lower-frequency and more indirect than order flow / velocity.
Still useful as a low-weight macro/options overlay.

Assessment: reasonable secondary feature.

## Realism Of The "Production-Grade" Claim

My updated view is:

- `production-grade architecture`: partially fair as an aspiration
- `production-grade implementation`: too strong

Why not fully fair:
- README/repo mismatches
- incomplete or placeholder components
- stale/inconsistent tests
- simulated evaluation still unrealistic
- no convincing evidence of rigorous historical validation

Why not totally unfair:
- the repo is larger and more serious than a throwaway script
- there is real engineering effort in risk/execution/monitoring structure
- several processors were clearly revised with better domain thinking

Best label:
- advanced prototype
- semi-integrated live-trading experiment
- not yet fully production-grade

## Updated Comparison: Local Extracted File vs Upstream Repo

### Local extracted file

Strength:
- easier to read

Weakness:
- understates the real architecture
- preserves some weaker earlier logic
- makes the strategy look more simplistic than it is upstream

### Upstream repo

Strength:
- richer and more coherent
- better divergence model
- clearer late-window thesis
- broader execution/risk infrastructure

Weakness:
- still uneven
- still partly aspirational
- still not strongly validated

## Verification Notes

Checks performed on the upstream clone:
- README review
- strategy core review
- signal processor review
- risk and execution review
- test review
- static compile check across all Python files

Static result:
- `py_compile` passed for all Python files in the cloned repo

Important caveat:
- successful compilation does not imply functional correctness
- especially in a repo with many external API and infrastructure dependencies

## Final Re-Rating

Updated scores:
- Strategy concept: `8/10`
- Signal design: `7/10`
- Architecture ambition: `8/10`
- Code consistency: `5/10`
- Risk/execution implementation: `6/10`
- Testing credibility: `4/10`
- Backtest / paper-trade credibility: `3/10`
- Live-production readiness: `4/10`

## Final Conclusion

The upstream repo materially improves the picture.

This strategy is not just a naive "multi-signal toy". It has a clearer real edge hypothesis:
- trade late
- trust the market's own price when it is already informative
- use microstructure/context signals as confirmation

That is a respectable trading idea.

But the repo still falls short of being truly production-grade because:
- documentation is inconsistent
- some paths are incomplete
- paper-trade evaluation is not trustworthy
- tests do not convincingly prove the current behavior

Practical takeaway:
- worth studying further
- worth extracting ideas from
- not yet trustworthy enough to deploy with confidence without additional validation and cleanup

## Recommended Next Steps

1. Align README with reality.
   Fix entrypoint names, missing files, and setup instructions.

2. Define the strategy honestly.
   Rename it from "multi-signal fusion bot" to something closer to "late-window trend-following with confirmation signals".

3. Replace random paper-trade exits.
   Use market replay or deterministic market-state-based settlement.

4. Repair the test suite.
   Bring tests in line with actual risk limits and current signal semantics.

5. Separate stable core from experimental modules.
   Mark placeholders clearly and reduce production claims until the live path is verifiably complete.
