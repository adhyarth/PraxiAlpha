"""PraxiAlpha — Trade Model

Trade models are defined in backend/models/journal.py (Trade, TradeExit, TradeLeg).
This file is kept for backwards compatibility with the original scaffolding.
"""

from backend.models.journal import Trade, TradeExit, TradeLeg

__all__ = ["Trade", "TradeExit", "TradeLeg"]
