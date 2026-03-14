"""
PraxiAlpha — EODHD Data Fetcher

Handles all interactions with the EODHD API:
- Fetch list of all US exchange tickers
- Fetch daily OHLCV history for a ticker
- Fetch dividends and splits
- Rate-limit compliant (100K calls/day, 1K calls/min)

EODHD API docs: https://eodhd.com/financial-apis/
"""

import logging
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---- Constants ----
EODHD_BASE_URL = "https://eodhd.com/api"
US_EXCHANGES = ["US"]  # EODHD uses "US" for all US exchanges (NYSE, NASDAQ, AMEX)
REQUEST_TIMEOUT = 30.0


class EODHDFetcher:
    """
    Fetches market data from EODHD API.

    Usage:
        fetcher = EODHDFetcher()
        tickers = await fetcher.fetch_us_tickers()
        ohlcv = await fetcher.fetch_daily_ohlcv("AAPL", start="1990-01-01")
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.eodhd_api_key
        if not self.api_key:
            raise ValueError("EODHD API key not set. Set EODHD_API_KEY in .env file.")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    async def _request(self, endpoint: str, params: dict | None = None) -> Any:
        """
        Make an authenticated request to EODHD API.

        Args:
            endpoint: API endpoint path (e.g., "/eod/AAPL.US")
            params: Additional query parameters

        Returns:
            Parsed JSON response
        """
        client = await self._get_client()
        url = f"{EODHD_BASE_URL}{endpoint}"

        request_params = {
            "api_token": self.api_key,
            "fmt": "json",
        }
        if params:
            request_params.update(params)

        logger.debug(f"EODHD request: {endpoint}")
        response = await client.get(url, params=request_params)
        response.raise_for_status()
        return response.json()

    # ============================================================
    # Ticker List
    # ============================================================
    async def fetch_us_tickers(self) -> list[dict]:
        """
        Fetch all active US exchange tickers from EODHD.

        Returns:
            List of dicts with keys: Code, Name, Country, Exchange, Currency, Type, Isin
        """
        logger.info("Fetching all US tickers from EODHD...")
        data = await self._request("/exchange-symbol-list/US")
        logger.info(f"Fetched {len(data)} US tickers from EODHD")
        return data

    # ============================================================
    # Daily OHLCV
    # ============================================================
    async def fetch_daily_ohlcv(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV data for a single ticker.

        Args:
            ticker: Stock ticker (e.g., "AAPL" — will append ".US" automatically)
            start: Start date in YYYY-MM-DD format (default: earliest available)
            end: End date in YYYY-MM-DD format (default: today)

        Returns:
            DataFrame with columns: date, open, high, low, close, adjusted_close, volume
        """
        # Ensure .US suffix
        eodhd_code = f"{ticker}.US" if ".US" not in ticker.upper() else ticker

        params = {}
        if start:
            params["from"] = start
        if end:
            params["to"] = end

        logger.info(f"Fetching OHLCV for {eodhd_code} (from={start}, to={end})")

        try:
            data = await self._request(f"/eod/{eodhd_code}", params=params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"No data found for {eodhd_code}")
                return pd.DataFrame()
            raise

        if not data:
            logger.warning(f"Empty response for {eodhd_code}")
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.rename(columns={"adjusted_close": "adjusted_close"})

        # Ensure proper column order
        expected_cols = ["date", "open", "high", "low", "close", "adjusted_close", "volume"]
        for col in expected_cols:
            if col not in df.columns:
                logger.warning(f"Missing column {col} in OHLCV data for {eodhd_code}")

        logger.info(
            f"Fetched {len(df)} OHLCV records for {eodhd_code} "
            f"({df['date'].min()} to {df['date'].max()})"
        )
        return df

    # ============================================================
    # Dividends
    # ============================================================
    async def fetch_dividends(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Fetch dividend history for a ticker."""
        eodhd_code = f"{ticker}.US" if ".US" not in ticker.upper() else ticker
        params = {}
        if start:
            params["from"] = start
        if end:
            params["to"] = end

        try:
            data = await self._request(f"/div/{eodhd_code}", params=params)
        except httpx.HTTPStatusError:
            return pd.DataFrame()

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df

    # ============================================================
    # Splits
    # ============================================================
    async def fetch_splits(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Fetch stock split history for a ticker."""
        eodhd_code = f"{ticker}.US" if ".US" not in ticker.upper() else ticker
        params = {}
        if start:
            params["from"] = start
        if end:
            params["to"] = end

        try:
            data = await self._request(f"/splits/{eodhd_code}", params=params)
        except httpx.HTTPStatusError:
            return pd.DataFrame()

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df

    # ============================================================
    # Bulk EOD (for daily updates — fetches ALL tickers for a date)
    # ============================================================
    async def fetch_bulk_eod(
        self,
        exchange: str = "US",
        date_str: str | None = None,
    ) -> pd.DataFrame:
        """
        Fetch bulk end-of-day data for all tickers on a given date.
        More efficient than per-ticker requests for daily updates.

        Args:
            exchange: Exchange code (default "US")
            date_str: Date in YYYY-MM-DD format (default: latest trading day)

        Returns:
            DataFrame with all tickers' OHLCV for that date
        """
        params = {"type": "eod"}
        if date_str:
            params["date"] = date_str

        logger.info(f"Fetching bulk EOD for {exchange} (date={date_str})")
        data = await self._request(f"/eod-bulk-last-day/{exchange}", params=params)

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        logger.info(f"Fetched bulk EOD: {len(df)} tickers")
        return df
