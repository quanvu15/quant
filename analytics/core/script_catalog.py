"""
Script catalog — maps logical script names to absolute paths.

Validates that all registered scripts exist at startup.
Supports both venv-numpy1 and venv-numpy2 scripts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class ScriptCatalog:
    """
    Registry of all Python scripts used by the API.

    Scripts are registered with a logical name and a path relative to SCRIPTS_DIR.
    The catalog validates existence at startup and provides path resolution.
    """

    def __init__(self):
        self._registry: Dict[str, str] = {}
        self._register_all()

    def _register_all(self):
        """Register all known scripts."""

        # ── Phase 1: AI Agents ────────────────────────────────────────────────
        # finagent_core/main.py hỗ trợ --stdin natively
        self.register("agents.main", "agents/finagent_core/main.py")

        # ── Phase 2: Market Data ──────────────────────────────────────────────
        self.register("market.yfinance", "api_bridge/market_bridge.py")
        self.register("market.polygon", "api_bridge/market_bridge.py")   # fallback to yfinance
        self.register("market.finnhub", "api_bridge/market_bridge.py")
        self.register("market.alphavantage", "api_bridge/market_bridge.py")
        self.register("market.stooq", "api_bridge/market_bridge.py")

        # ── Phase 2: Equity Research ──────────────────────────────────────────
        self.register("equity.dcf", "api_bridge/market_bridge.py")
        self.register("equity.financials", "api_bridge/market_bridge.py")
        self.register("equity.news", "api_bridge/analytics_bridge.py")
        self.register("equity.relationships", "api_bridge/analytics_bridge.py")

        # ── Phase 2: Portfolio ────────────────────────────────────────────────
        self.register("portfolio.optimize", "api_bridge/analytics_bridge.py")
        self.register("portfolio.quantstats", "api_bridge/analytics_bridge.py")
        self.register("portfolio.sparklines", "api_bridge/analytics_bridge.py")

        # ── Phase 2: Derivatives ──────────────────────────────────────────────
        self.register("derivatives.pricing", "api_bridge/quant_bridge.py")
        self.register("derivatives.greeks_daemon", "api_bridge/quant_bridge.py")
        self.register("derivatives.fii_dii", "api_bridge/analytics_bridge.py")

        # ── Phase 2: Technical Analysis ───────────────────────────────────────
        self.register("technical.compute", "api_bridge/analytics_bridge.py")
        self.register("technical.talipp", "api_bridge/analytics_bridge.py")

        # ── Phase 3: QuantLib / FinancePy ─────────────────────────────────────
        self.register("quant.financepy", "api_bridge/financepy_bridge.py")
        self.register("quant.derivatives", "api_bridge/quant_bridge.py")

        # ── Phase 4: Global Intelligence ─────────────────────────────────────
        self.register("intel.acled", "api_bridge/intelligence_bridge.py")
        self.register("intel.hdx", "api_bridge/intelligence_bridge.py")
        self.register("intel.marinetraffic", "api_bridge/intelligence_bridge.py")
        self.register("intel.aisstream", "api_bridge/intelligence_bridge.py")
        self.register("intel.fred", "api_bridge/intelligence_bridge.py")
        self.register("intel.worldbank", "api_bridge/intelligence_bridge.py")
        self.register("intel.imf", "api_bridge/intelligence_bridge.py")
        self.register("intel.oecd", "api_bridge/intelligence_bridge.py")
        self.register("intel.economic_calendar", "api_bridge/intelligence_bridge.py")
        self.register("intel.ecb", "api_bridge/intelligence_bridge.py")
        self.register("intel.boj", "api_bridge/intelligence_bridge.py")
        self.register("intel.boe", "api_bridge/intelligence_bridge.py")
        self.register("intel.rba", "api_bridge/intelligence_bridge.py")
        self.register("intel.bls", "api_bridge/intelligence_bridge.py")
        self.register("intel.census", "api_bridge/intelligence_bridge.py")
        self.register("intel.eurostat", "api_bridge/intelligence_bridge.py")
        self.register("intel.eia", "api_bridge/intelligence_bridge.py")
        self.register("intel.relationship_map", "api_bridge/intelligence_bridge.py")

        # ── Phase 5: AI Quant Lab ─────────────────────────────────────────────
        self.register("qlab.service", "api_bridge/qlab_bridge.py")
        self.register("qlab.backtest", "api_bridge/qlab_bridge.py")
        self.register("qlab.rl", "api_bridge/qlab_bridge.py")
        self.register("qlab.portfolio_opt", "api_bridge/qlab_bridge.py")
        self.register("qlab.feature_eng", "api_bridge/qlab_bridge.py")
        self.register("qlab.evaluation", "api_bridge/qlab_bridge.py")
        self.register("qlab.reporting", "api_bridge/qlab_bridge.py")
        self.register("qlab.models", "api_bridge/qlab_bridge.py")

    def register(self, name: str, relative_path: str) -> None:
        """Register a script by logical name and relative path."""
        self._registry[name] = relative_path

    def resolve(self, name: str) -> Optional[Path]:
        """
        Resolve a logical script name to an absolute Path.
        Returns None if the name is not registered.
        """
        relative = self._registry.get(name)
        if relative is None:
            return None
        scripts_dir = Path(settings.SCRIPTS_DIR)
        return scripts_dir / relative

    def path(self, name: str) -> str:
        """
        Return the relative path string for a registered script.
        Raises KeyError if not found.
        """
        if name not in self._registry:
            raise KeyError(f"Script '{name}' not in catalog. Register it in ScriptCatalog._register_all()")
        return self._registry[name]

    def validate(self) -> List[str]:
        """
        Check all registered scripts exist on disk.
        Returns list of missing script names (empty = all OK).
        """
        scripts_dir = Path(settings.SCRIPTS_DIR)
        missing = []

        if not scripts_dir.exists():
            logger.error("script_catalog.scripts_dir_missing", path=str(scripts_dir))
            return list(self._registry.keys())

        for name, relative in self._registry.items():
            full_path = scripts_dir / relative
            if not full_path.exists():
                missing.append(f"{name} → {relative}")
                logger.debug("script_catalog.missing", name=name, path=str(full_path))

        if missing:
            logger.warning(
                "script_catalog.validation_failed",
                missing_count=len(missing),
                total=len(self._registry),
            )
        else:
            logger.info(
                "script_catalog.validation_ok",
                total=len(self._registry),
            )

        return missing

    def list_all(self) -> Dict[str, str]:
        """Return a copy of the full registry."""
        return dict(self._registry)


# Module-level singleton
catalog = ScriptCatalog()
