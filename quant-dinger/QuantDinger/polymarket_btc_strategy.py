"""
Polymarket BTC 15-Minute Trading Strategy
=====================================

A simplified standalone trading strategy script extracted from the 
Polymarket-BTC-15-Minute-Trading-Bot repository.

This script implements the core trading logic:
- Multi-signal processing (Spike, Sentiment, Divergence, OrderBook, Velocity, PCR)
- Signal fusion with weighted voting
- Trend filter as the main decision maker
- Risk management rules

Usage:
    python polymarket_btc_strategy.py [--live] [--test-mode]
"""

import asyncio
import argparse
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any
from collections import deque
import random
import requests
from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# Constants
# =============================================================================
MARKET_INTERVAL_SECONDS = 900  # 15-minute markets
QUOTE_MIN_SPREAD = 0.001
SPIKE_THRESHOLD = 0.05
DIVERGENCE_THRESHOLD = 0.05
ORDERBOOK_IMBALANCE_THRESHOLD = 0.30
VELOCITY_THRESHOLD_60S = 0.015
VELOCITY_THRESHOLD_30S = 0.010
BULLISH_PCR_THRESHOLD = 1.20
BEARISH_PCR_THRESHOLD = 0.70
TREND_UP_THRESHOLD = 0.60
TREND_DOWN_THRESHOLD = 0.40
MAX_POSITION_SIZE = 1.0  # $1 max per trade
MIN_LIQUIDITY = 0.02


class SignalDirection(Enum):
    BULLISH = "long"   # Buy YES (UP)
    BEARISH = "short" # Buy NO (DOWN)
    NEUTRAL = "neutral"


@dataclass
class TradingSignal:
    """Represents a trading signal from a processor."""
    source: str
    direction: SignalDirection
    score: float  # 0-100
    confidence: float  # 0.0-1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketData:
    """Current market data."""
    yes_price: float
    no_price: float
    bid: float
    ask: float
    volume: float
    timestamp: datetime
    orderbook_yes_bid: float = 0.0
    orderbook_yes_ask: float = 0.0
    orderbook_no_bid: float = 0.0
    orderbook_no_ask: float = 0.0


@dataclass
class Trade:
    """Executed trade record."""
    timestamp: datetime
    direction: str
    size_usd: float
    entry_price: float
    signal_score: float
    signal_confidence: float
    outcome: str = "PENDING"
    exit_price: Optional[float] = None
    pnl: Optional[float] = None


# =============================================================================
# Signal Processors
# =============================================================================

class SignalProcessor:
    """Base class for signal processors."""
    
    def __init__(self, name: str):
        self.name = name
        self.weight = 0.0
    
    def process(self, current_price: float, price_history: List[float], 
              metadata: Dict[str, Any]) -> Optional[TradingSignal]:
        raise NotImplementedError


class SpikeDetectionProcessor(SignalProcessor):
    """Detect sudden price spikes indicating momentum."""
    
    def __init__(self, spike_threshold: float = SPIKE_THRESHOLD, 
                 lookback_periods: int = 20):
        super().__init__("SpikeDetection")
        self.spike_threshold = spike_threshold
        self.lookback_periods = lookback_periods
    
    def process(self, current_price: float, price_history: List[float],
              metadata: Dict[str, Any]) -> Optional[TradingSignal]:
        if len(price_history) < self.lookback_periods:
            return None
        
        # Calculate recent price changes
        lookback = min(self.lookback_periods, len(price_history))
        recent_prices = price_history[-lookback:]
        
        # Check for spike in last 3 periods
        if len(recent_prices) >= 3:
            change_3p = (recent_prices[-1] - recent_prices[-3]) / recent_prices[-3]
            
            if abs(change_3p) > self.spike_threshold:
                direction = SignalDirection.BULLISH if change_3p > 0 else SignalDirection.BEARISH
                score = min(100, abs(change_3p) * 2000)  # Scale to 0-100
                confidence = min(1.0, abs(change_3p) / self.spike_threshold)
                
                return TradingSignal(
                    source=self.name,
                    direction=direction,
                    score=score,
                    confidence=confidence,
                    metadata={"change_3p": change_3p, "spike": True}
                )
        
        return None


class SentimentProcessor(SignalProcessor):
    """Process Fear & Greed Index sentiment."""
    
    def __init__(self, extreme_fear_threshold: int = 25, extreme_greed_threshold: int = 75):
        super().__init__("SentimentAnalysis")
        self.extreme_fear_threshold = extreme_fear_threshold
        self.extreme_greed_threshold = extreme_greed_threshold
        self._cached_sentiment: Optional[Dict] = None
        self._cache_time: float = 0
    
    def _fetch_fear_greed_index(self) -> Optional[int]:
        """Fetch Fear & Greed Index from alternative.me API."""
        current_time = time.time()
        
        # Use cached if less than 5 minutes old
        if self._cached_sentiment and (current_time - self._cache_time) < 300:
            return self._cached_sentiment
        
        try:
            response = requests.get(
                "https://api.alternative.me/fng/",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    value = int(data["data"][0]["value"])
                    self._cached_sentiment = value
                    self._cache_time = current_time
                    return value
        except Exception:
            pass
        
        return self._cached_sentiment
    
    def process(self, current_price: float, price_history: List[float],
              metadata: Dict[str, Any]) -> Optional[TradingSignal]:
        sentiment = self._fetch_fear_greed_index()
        
        if sentiment is None:
            return None
        
        # Extreme fear (0-25) → potential bottom → BUY
        # Extreme greed (75-100) → potential top → SELL
        if sentiment <= self.extreme_fear_threshold:
            direction = SignalDirection.BULLISH
            score = (25 - sentiment) * 4  # More extreme = higher score
            confidence = (25 - sentiment) / 25
        elif sentiment >= self.extreme_greed_threshold:
            direction = SignalDirection.BEARISH
            score = (sentiment - 75) * 4
            confidence = (sentiment - 75) / 25
        else:
            return None
        
        return TradingSignal(
            source=self.name,
            direction=direction,
            score=min(100, score),
            confidence=min(1.0, confidence),
            metadata={"sentiment": sentiment}
        )


class PriceDivergenceProcessor(SignalProcessor):
    """Detect price divergence between Polymarket and spot."""
    
    def __init__(self, divergence_threshold: float = DIVERGENCE_THRESHOLD):
        super().__init__("PriceDivergence")
        self.divergence_threshold = divergence_threshold
    
    def _fetch_spot_btc_price(self) -> Optional[float]:
        """Fetch BTC spot price from Coinbase."""
        try:
            response = requests.get(
                "https://api.coinbase.com/v2/prices/BTC-USD/spot",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return float(data["data"]["amount"])
        except Exception:
            pass
        return None
    
    def process(self, current_price: float, price_history: List[float],
              metadata: Dict[str, Any]) -> Optional[TradingSignal]:
        spot_price = metadata.get("spot_price") or self._fetch_spot_btc_price()
        
        if spot_price is None:
            return None
        
        # Convert spot price to 0-1 probability scale
        # Assuming reasonable BTC range: $20,000-$120,000
        normalized_spot = (spot_price - 20000) / 100000
        normalized_spot = max(0.0, min(1.0, normalized_spot))
        
        # Calculate divergence
        divergence = current_price - normalized_spot
        
        if abs(divergence) > self.divergence_threshold:
            direction = SignalDirection.BULLISH if divergence > 0 else SignalDirection.BEARISH
            score = min(100, abs(divergence) * 2000)
            confidence = min(1.0, abs(divergence) / self.divergence_threshold)
            
            return TradingSignal(
                source=self.name,
                direction=direction,
                score=score,
                confidence=confidence,
                metadata={
                    "divergence": divergence,
                    "spot_price": spot_price,
                    "normalized_spot": normalized_spot
                }
            )
        
        return None


class OrderBookImbalanceProcessor(SignalProcessor):
    """Detect order book imbalance for real-time liquidity."""
    
    def __init__(self, imbalance_threshold: float = ORDERBOOK_IMBALANCE_THRESHOLD,
                 min_book_volume: float = 50.0):
        super().__init__("OrderBookImbalance")
        self.imbalance_threshold = imbalance_threshold
        self.min_book_volume = min_book_volume
    
    def _fetch_orderbook(self, token_id: str) -> Optional[Dict]:
        """Fetch order book from Polymarket CLOB API."""
        try:
            response = requests.get(
                f"https://clob.polymarket.com/markets/{token_id}/orderbook",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None
    
    def process(self, current_price: float, price_history: List[float],
              metadata: Dict[str, Any]) -> Optional[TradingSignal]:
        token_id = metadata.get("yes_token_id")
        
        if not token_id:
            return None
        
        orderbook = metadata.get("orderbook") or self._fetch_orderbook(token_id)
        
        if not orderbook:
            return None
        
        # Calculate bid/ask volumes
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        
        bid_vol = sum(float(b.get("size", 0)) for b in bids[:5])
        ask_vol = sum(float(a.get("size", 0)) for a in asks[:5])
        
        total_vol = bid_vol + ask_vol
        
        if total_vol < self.min_book_volume:
            return None
        
        # Calculate imbalance
        imbalance = (bid_vol - ask_vol) / total_vol
        
        if abs(imbalance) > self.imbalance_threshold:
            direction = SignalDirection.BULLISH if imbalance > 0 else SignalDirection.BEARISH
            score = min(100, abs(imbalance) * 200)
            confidence = min(1.0, abs(imbalance) / self.imbalance_threshold)
            
            return TradingSignal(
                source=self.name,
                direction=direction,
                score=score,
                confidence=confidence,
                metadata={
                    "imbalance": imbalance,
                    "bid_vol": bid_vol,
                    "ask_vol": ask_vol
                }
            )
        
        return None


class TickVelocityProcessor(SignalProcessor):
    """Detect fast price momentum in last 60s/30s."""
    
    def __init__(self, velocity_threshold_60s: float = VELOCITY_THRESHOLD_60S,
                 velocity_threshold_30s: float = VELOCITY_THRESHOLD_30S):
        super().__init__("TickVelocity")
        self.velocity_threshold_60s = velocity_threshold_60s
        self.velocity_threshold_30s = velocity_threshold_30s
        self.tick_buffer: deque = deque(maxlen=500)
    
    def add_tick(self, price: float, timestamp: datetime):
        """Add a new price tick to the buffer."""
        self.tick_buffer.append({"price": price, "timestamp": timestamp})
    
    def process(self, current_price: float, price_history: List[float],
              metadata: Dict[str, Any]) -> Optional[TradingSignal]:
        tick_buffer = metadata.get("tick_buffer") or list(self.tick_buffer)
        
        if len(tick_buffer) < 10:
            return None
        
        current_time = datetime.now(timezone.utc)
        
        # Find ticks from 30s and 60s ago
        ticks_30s_ago = None
        ticks_60s_ago = None
        
        for tick in tick_buffer:
            age = (current_time - tick["timestamp"]).total_seconds()
            if age >= 30 and ticks_30s_ago is None:
                ticks_30s_ago = tick["price"]
            if age >= 60 and ticks_60s_ago is None:
                ticks_60s_ago = tick["price"]
        
        # Check 60s velocity
        if ticks_60s_ago:
            change_60s = (current_price - ticks_60s_ago) / ticks_60s_ago
            if abs(change_60s) > self.velocity_threshold_60s:
                direction = SignalDirection.BULLISH if change_60s > 0 else SignalDirection.BEARISH
                score = min(100, abs(change_60s) * 5000)
                confidence = min(1.0, abs(change_60s) / self.velocity_threshold_60s)
                
                return TradingSignal(
                    source=self.name,
                    direction=direction,
                    score=score,
                    confidence=confidence,
                    metadata={"change_60s": change_60s, "velocity": "60s"}
                )
        
        # Check 30s velocity
        if ticks_30s_ago:
            change_30s = (current_price - ticks_30s_ago) / ticks_30s_ago
            if abs(change_30s) > self.velocity_threshold_30s:
                direction = SignalDirection.BULLISH if change_30s > 0 else SignalDirection.BEARISH
                score = min(100, abs(change_30s) * 10000)
                confidence = min(1.0, abs(change_30s) / self.velocity_threshold_30s)
                
                return TradingSignal(
                    source=self.name,
                    direction=direction,
                    score=score,
                    confidence=confidence,
                    metadata={"change_30s": change_30s, "velocity": "30s"}
                )
        
        return None


class DeribitPCRProcessor(SignalProcessor):
    """Detect institutional sentiment from Deribit put/call ratio."""
    
    def __init__(self, bullish_pcr_threshold: float = BULLISH_PCR_THRESHOLD,
                 bearish_pcr_threshold: float = BEARISH_PCR_THRESHOLD,
                 max_days_to_expiry: int = 2,
                 cache_seconds: int = 300):
        super().__init__("DeribitPCR")
        self.bullish_pcr_threshold = bullish_pcr_threshold
        self.bearish_pcr_threshold = bearish_pcr_threshold
        self.max_days_to_expiry = max_days_to_expiry
        self.cache_seconds = cache_seconds
        self._cached_pcr: Optional[float] = None
        self._cache_time: float = 0
    
    def _fetch_pcr(self) -> Optional[float]:
        """Fetch put/call ratio from Deribit API."""
        current_time = time.time()
        
        if self._cached_pcr and (current_time - self._cache_time) < self.cache_seconds:
            return self._cached_pcr
        
        try:
            # Get BTC options data
            response = requests.get(
                "https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
                {"currency": "BTC", "kind": "option"},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("result"):
                    # Calculate PCR
                    puts = 0.0
                    calls = 0.0
                    for item in data["result"]:
                        if item.get("currency") == "BTC":
                            if item.get("option_type") == "put":
                                puts += item.get("volume", 0)
                            else:
                                calls += item.get("volume", 0)
                    
                    if calls > 0:
                        pcr = puts / calls
                        self._cached_pcr = pcr
                        self._cache_time = current_time
                        return pcr
        except Exception:
            pass
        
        return self._cached_pcr
    
    def process(self, current_price: float, price_history: List[float],
              metadata: Dict[str, Any]) -> Optional[TradingSignal]:
        pcr = metadata.get("pcr") or self._fetch_pcr()
        
        if pcr is None:
            return None
        
        if pcr > self.bullish_pcr_threshold:
            # High PCR =bearish (more puts than calls)
            direction = SignalDirection.BEARISH
            score = min(100, (pcr - self.bullish_pcr_threshold) * 500)
            confidence = min(1.0, (pcr - self.bullish_pcr_threshold) / 0.5)
        elif pcr < self.bearish_pcr_threshold:
            # Low PCR = bullish (more calls than puts)
            direction = SignalDirection.BULLISH
            score = min(100, (self.bearish_pcr_threshold - pcr) * 500)
            confidence = min(1.0, (self.bearish_pcr_threshold - pcr) / 0.5)
        else:
            return None
        
        return TradingSignal(
            source=self.name,
            direction=direction,
            score=score,
            confidence=confidence,
            metadata={"pcr": pcr}
        )


# =============================================================================
# Signal Fusion Engine
# =============================================================================

class SignalFusion:
    """Combine multiple signals with weighted voting."""
    
    def __init__(self):
        self.processors: Dict[str, SignalProcessor] = {}
        self.weights: Dict[str, float] = {}
    
    def add_processor(self, processor: SignalProcessor, weight: float):
        """Add a signal processor with its weight."""
        self.processors[processor.name] = processor
        self.weights[processor.name] = weight
    
    def set_weight(self, name: str, weight: float):
        """Update weight for a processor."""
        self.weights[name] = weight
    
    def fuse_signals(self, signals: List[TradingSignal], 
                    min_signals: int = 1, 
                    min_score: float = 40.0) -> Optional[TradingSignal]:
        """Fuse multiple signals into one consensus decision."""
        if len(signals) < min_signals:
            return None
        
        # Calculate weighted scores
        bullish_score = 0.0
        bearish_score = 0.0
        total_confidence = 0.0
        total_weight = 0.0
        
        for signal in signals:
            weight = self.weights.get(signal.source, 0.1)
            total_weight += weight
            
            if signal.direction == SignalDirection.BULLISH:
                bullish_score += signal.score * weight
            elif signal.direction == SignalDirection.BEARISH:
                bearish_score += signal.score * weight
            
            total_confidence += signal.confidence * weight
        
        # Determine consensus
        if bullish_score > bearish_score and bullish_score >= min_score:
            return TradingSignal(
                source="Fusion",
                direction=SignalDirection.BULLISH,
                score=bullish_score,
                confidence=min(1.0, total_confidence / total_weight),
                metadata={"num_signals": len(signals)}
            )
        elif bearish_score > bullish_score and bearish_score >= min_score:
            return TradingSignal(
                source="Fusion",
                direction=SignalDirection.BEARISH,
                score=bearish_score,
                confidence=min(1.0, total_confidence / total_weight),
                metadata={"num_signals": len(signals)}
            )
        
        return None


# =============================================================================
# Risk Engine
# =============================================================================

class RiskEngine:
    """Risk management and position validation."""
    
    def __init__(self, max_position_size: float = MAX_POSITION_SIZE,
                 stop_loss_pct: float = 0.30,
                 take_profit_pct: float = 0.20):
        self.max_position_size = max_position_size
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.open_positions: List[Trade] = []
    
    def validate_new_position(self, size: float, direction: str,
                        current_price: float) -> tuple[bool, Optional[str]]:
        """Validate if new position is allowed."""
        # Check max position size
        if size > self.max_position_size:
            return False, f"Position size ${size} exceeds max ${self.max_position_size}"
        
        # Check max open positions
        if len(self.open_positions) >= 5:
            return False, "Maximum open positions reached"
        
        # Check exposure
        total_exposure = sum(p.size_usd for p in self.open_positions)
        if total_exposure + size > self.max_position_size * 3:
            return False, "Total exposure limit reached"
        
        return True, None
    
    def check_exit_conditions(self, trade: Trade, current_price: float) -> Optional[str]:
        """Check if position should be exited."""
        if trade.direction.upper() == "LONG":
            pnl_pct = (current_price - trade.entry_price) / trade.entry_price
        else:
            pnl_pct = (trade.entry_price - current_price) / trade.entry_price
        
        if pnl_pct <= -self.stop_loss_pct:
            return "STOP_LOSS"
        elif pnl_pct >= self.take_profit_pct:
            return "TAKE_PROFIT"
        
        return None


# =============================================================================
# Trading Strategy
# =============================================================================

class PolymarketBTCStrategy:
    """
    Simplified Polymarket BTC 15-Minute Trading Strategy.
    
    Core logic extracted from the original 7-phase architecture:
    1. Multi-signal processing (6 processors)
    2. Signal fusion with weighted voting
    3. Trend filter (main decision maker)
    4. Risk management
    """
    
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.price_history: List[float] = []
        self.trades: List[Trade] = []
        
        # Initialize signal processors
        self.spike_detector = SpikeDetectionProcessor()
        self.sentiment_processor = SentimentProcessor()
        self.divergence_processor = PriceDivergenceProcessor()
        self.orderbook_processor = OrderBookImbalanceProcessor()
        self.tick_velocity_processor = TickVelocityProcessor()
        self.deribit_pcr_processor = DeribitPCRProcessor()
        
        # Initialize fusion engine with weights
        self.fusion_engine = SignalFusion()
        self.fusion_engine.add_processor(self.orderbook_processor, 0.30)
        self.fusion_engine.add_processor(self.tick_velocity_processor, 0.25)
        self.fusion_engine.add_processor(self.divergence_processor, 0.18)
        self.fusion_engine.add_processor(self.spike_detector, 0.12)
        self.fusion_engine.add_processor(self.deribit_pcr_processor, 0.10)
        self.fusion_engine.add_processor(self.sentiment_processor, 0.05)
        
        # Initialize risk engine
        self.risk_engine = RiskEngine()
        
        print("=" * 60)
        print("POLYMARKET BTC 15-MIN TRADING STRATEGY INITIALIZED")
        print("  Signal Processors: 6 (Spike, Sentiment, Divergence, OB, Velocity, PCR)")
        print("  Fusion: Weighted voting")
        print("  Trend Filter: UP > 0.60, DOWN < 0.40")
        print(f"  Max Position: ${MAX_POSITION_SIZE}")
        print(f"  Test Mode: {test_mode}")
        print("=" * 60)
    
    def update_price_history(self, price: float):
        """Update price history buffer."""
        self.price_history.append(price)
        if len(self.price_history) > 100:
            self.price_history.pop(0)
        
        # Update tick velocity processor
        self.tick_velocity_processor.add_tick(price, datetime.now(timezone.utc))
    
    def _fetch_market_data(self, market_slug: str) -> Optional[MarketData]:
        """Fetch current market data from Polymarket API."""
        try:
            response = requests.get(
                f"https://clob.polymarket.com/markets/{market_slug}",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                # Note: This is a simplified response handler
                # Actual API response structure may vary
                return None  # Placeholder
        except Exception:
            pass
        return None
    
    def _process_signals(self, current_price: float, 
                       metadata: Dict[str, Any]) -> List[TradingSignal]:
        """Process all signals."""
        signals = []
        
        # Process each signal processor
        for processor in [
            self.spike_detector,
            self.sentiment_processor,
            self.divergence_processor,
            self.orderbook_processor,
            self.tick_velocity_processor,
            self.deribit_pcr_processor
        ]:
            signal = processor.process(
                current_price=current_price,
                price_history=self.price_history,
                metadata=metadata
            )
            if signal:
                signals.append(signal)
                print(f"  [{signal.source}] {signal.direction.value}: "
                      f"score={signal.score:.1f}, confidence={signal.confidence:.2%}")
        
        return signals
    
    def make_trading_decision(self, current_price: float,
                         metadata: Dict[str, Any] = None) -> Optional[TradingSignal]:
        """
        Make trading decision using the core strategy.
        
        This implements the TREND FILTER which is the main decision maker:
        - price > 0.60 → buy YES (UP)
        - price < 0.40 → buy NO (DOWN)
        - price 0.40-0.60 → SKIP (too close to call)
        """
        if metadata is None:
            metadata = {}
        
        # Check minimum history
        if len(self.price_history) < 20:
            print(f"Not enough price history ({len(self.price_history)}/20)")
            return None
        
        print(f"Current price: ${current_price:.4f}")
        
        # Process signals
        signals = self._process_signals(current_price, metadata)
        
        if not signals:
            print("No signals generated — no trade this interval")
            return None
        
        print(f"Generated {len(signals)} signal(s)")
        
        # Fuse signals
        fused = self.fusion_engine.fuse_signals(signals, min_signals=1, min_score=40.0)
        
        if not fused:
            print("Fusion produced no actionable signal")
            return None
        
        print(f"FUSED SIGNAL: {fused.direction.value} "
              f"(score={fused.score:.1f}, confidence={fused.confidence:.2%})")
        
        # =================================================================
        # TREND FILTER — THE MAIN DECISION MAKER
        # =================================================================
        # At minute 13, the Polymarket price IS the market's verdict.
        # We follow the price directly:
        
        if current_price > TREND_UP_THRESHOLD:
            direction = SignalDirection.BULLISH
            confidence = current_price
            print(f"TREND: UP ({current_price:.2%}) → buying YES")
        elif current_price < TREND_DOWN_THRESHOLD:
            direction = SignalDirection.BEARISH
            confidence = 1.0 - current_price
            print(f"TREND: DOWN ({current_price:.2%}) → buying NO")
        else:
            print(f"⏭ TREND: NEUTRAL ({current_price:.2%}) — "
                  f"SKIPPING (coin flip territory)")
            return None
        
        # Validate with risk engine
        is_valid, error = self.risk_engine.validate_new_position(
            size=MAX_POSITION_SIZE,
            direction=direction.value,
            current_price=current_price
        )
        
        if not is_valid:
            print(f"Risk engine blocked trade: {error}")
            return None
        
        return TradingSignal(
            source="TrendFilter",
            direction=direction,
            score=100.0,
            confidence=confidence,
            metadata={"fused_signal": fused}
        )
    
    def execute_trade(self, signal: TradingSignal, current_price: float,
                     is_simulation: bool = True) -> Optional[Trade]:
        """Execute a trade based on the signal."""
        if signal.direction == SignalDirection.BULLISH:
            direction = "LONG"
        elif signal.direction == SignalDirection.BEARISH:
            direction = "SHORT"
        else:
            return None
        
        trade = Trade(
            timestamp=datetime.now(timezone.utc),
            direction=direction,
            size_usd=MAX_POSITION_SIZE,
            entry_price=current_price,
            signal_score=signal.score,
            signal_confidence=signal.confidence
        )
        
        self.trades.append(trade)
        
        if is_simulation:
            # Simulate exit after interval
            interval = timedelta(minutes=1) if self.test_mode else timedelta(minutes=15)
            exit_time = datetime.now(timezone.utc) + interval
            
            # Simulate price movement
            if direction == "LONG":
                movement = random.uniform(-0.02, 0.08)
            else:
                movement = random.uniform(-0.08, 0.02)
            
            exit_price = current_price * (1.0 + movement)
            exit_price = max(0.01, min(0.99, exit_price))
            
            trade.exit_price = exit_price
            
            if direction == "LONG":
                pnl = MAX_POSITION_SIZE * (exit_price - current_price) / current_price
            else:
                pnl = MAX_POSITION_SIZE * (current_price - exit_price) / current_price
            
            trade.pnl = pnl
            trade.outcome = "WIN" if pnl > 0 else "LOSS"
            
            print("=" * 60)
            print(f"[{'SIMULATION' if is_simulation else 'LIVE'}] TRADE EXECUTED")
            print(f"  Direction: {direction}")
            print(f"  Size: ${MAX_POSITION_SIZE}")
            print(f"  Entry: ${current_price:.4f}")
            print(f"  Exit: ${exit_price:.4f}")
            print(f"  P&L: ${pnl:+.2f} ({movement*100:+.2f}%)")
            print(f"  Outcome: {trade.outcome}")
            print("=" * 60)
        else:
            # Live trading would call Polymarket API here
            print("=" * 60)
            print("[LIVE] TRADE EXECUTED")
            print(f"  Direction: {direction}")
            print(f"  Size: ${MAX_POSITION_SIZE}")
            print(f"  Price: ${current_price:.4f}")
            print("  (Actual order would be placed via API)")
            print("=" * 60)
        
        return trade
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get trading statistics."""
        if not self.trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0
            }
        
        completed = [t for t in self.trades if t.pnl is not None]
        
        if not completed:
            return {
                "total_trades": len(self.trades),
                "completed": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0
            }
        
        wins = sum(1 for t in completed if t.outcome == "WIN")
        total_pnl = sum(t.pnl for t in completed)
        
        return {
            "total_trades": len(completed),
            "wins": wins,
            "losses": len(completed) - wins,
            "win_rate": wins / len(completed) if completed else 0.0,
            "total_pnl": total_pnl
        }


# =============================================================================
# Main Runner
# =============================================================================

async def run_strategy(market_slug: str = "btc-updown-15m",
                     simulation: bool = True,
                     test_mode: bool = False,
                     max_iterations: int = 3):
    """Run the trading strategy."""
    strategy = PolymarketBTCStrategy(test_mode=test_mode)
    
    interval = 60 if test_mode else MARKET_INTERVAL_SECONDS
    
    print(f"\nStarting strategy...")
    print(f"  Market: {market_slug}")
    print(f"  Mode: {'SIMULATION' if simulation else 'LIVE'}")
    print(f"  Interval: {interval}s")
    print(f"  Max iterations: {max_iterations}")
    print()
    
    # Generate synthetic price data for demo
    if len(strategy.price_history) < 20:
        base_price = 0.50
        for _ in range(20):
            change = random.uniform(-0.03, 0.03)
            base_price = max(0.01, min(0.99, base_price * (1 + change)))
            strategy.update_price_history(base_price)
    
    iteration = 0
    try:
        while iteration < max_iterations:
            iteration += 1
            # Simulate current price (in real usage, fetch from API)
            current_price = random.uniform(0.35, 0.65)
            strategy.update_price_history(current_price)
            
            # Make trading decision
            signal = strategy.make_trading_decision(current_price)
            
            if signal:
                strategy.execute_trade(signal, current_price, is_simulation=simulation)
            
            # Print statistics
            stats = strategy.get_statistics()
            if stats["total_trades"] > 0:
                print(f"\nStatistics: {stats}")
            
            # Skip sleep in demo mode
            if iteration < max_iterations:
                await asyncio.sleep(0.1)  # Small delay for demo
            
    except KeyboardInterrupt:
        print("\nStopping strategy...")
        
        # Final statistics
        stats = strategy.get_statistics()
        print(f"\nFinal Statistics:")
        print(f"  Total Trades: {stats['total_trades']}")
        print(f"  Win Rate: {stats['win_rate']*100:.1f}%")
        print(f"  Total P&L: ${stats['total_pnl']:+.2f}")


def main():
    parser = argparse.ArgumentParser(description="Polymarket BTC 15-Min Strategy")
    parser.add_argument("--live", action="store_true",
                      help="Run in LIVE mode (real money)")
    parser.add_argument("--test-mode", action="store_true",
                      help="Run in TEST MODE (trade every minute)")
    parser.add_argument("--market", type=str, default="btc-updown-15m",
                      help="Market slug")
    
    args = parser.parse_args()
    
    simulation = not args.live
    test_mode = args.test_mode
    
    if not simulation:
        print("=" * 60)
        print("⚠ LIVE TRADING MODE — REAL MONEY AT RISK!")
        print("=" * 60)
    else:
        mode = "TEST MODE" if test_mode else "SIMULATION"
        print(f"Running in {mode} mode")
    
    asyncio.run(run_strategy(
        market_slug=args.market,
        simulation=simulation,
        test_mode=test_mode,
        max_iterations=3  # Run 3 iterations then exit for demo
    ))


if __name__ == "__main__":
    main()