"""
PraxiAlpha — FRED Data Fetcher

Handles all interactions with the FRED (Federal Reserve) API:
- Fetch macro indicator time-series (Treasury yields, VIX, DXY, etc.)
- FRED API is free — no rate limit concerns for our usage

FRED API docs: https://fred.stlouisfed.org/docs/api/fred/
"""

import logging

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import get_settings
from backend.models.macro import FRED_SERIES

logger = logging.getLogger(__name__)
settings = get_settings()

# ---- Constants ----
FRED_BASE_URL = "https://api.stlouisfed.org/fred"
REQUEST_TIMEOUT = 30.0


class FREDFetcher:
    """
    Fetches macroeconomic data from the FRED API.

    Usage:
        fetcher = FREDFetcher()
        df = await fetcher.fetch_series("DGS10", start="1990-01-01")
        all_data = await fetcher.fetch_all_series()
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.fred_api_key
        if not self.api_key:
            raise ValueError("FRED API key not set. Set FRED_API_KEY in .env file.")
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
    async def _request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make an authenticated request to FRED API."""
        client = await self._get_client()
        url = f"{FRED_BASE_URL}{endpoint}"

        request_params = {
            "api_key": self.api_key,
            "file_type": "json",
        }
        if params:
            request_params.update(params)

        logger.debug(f"FRED request: {endpoint}")
        response = await client.get(url, params=request_params)
        response.raise_for_status()
        return response.json()

    async def fetch_series(
        self,
        series_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """
        Fetch a FRED time-series.

        Args:
            series_id: FRED series ID (e.g., "DGS10")
            start: Start date YYYY-MM-DD (default: earliest available)
            end: End date YYYY-MM-DD (default: latest available)

        Returns:
            DataFrame with columns: date, value
        """
        params = {"series_id": series_id}
        if start:
            params["observation_start"] = start
        if end:
            params["observation_end"] = end

        logger.info(f"Fetching FRED series: {series_id}")

        data = await self._request("/series/observations", params=params)
        observations = data.get("observations", [])

        if not observations:
            logger.warning(f"No observations for FRED series {series_id}")
            return pd.DataFrame()

        df = pd.DataFrame(observations)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        # FRED returns "." for missing values
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df[["date", "value"]].copy()
        df["series_id"] = series_id

        logger.info(
            f"Fetched {len(df)} observations for {series_id} "
            f"({df['date'].min()} to {df['date'].max()})"
        )
        return df

    async def fetch_all_series(
        self,
        start: str | None = "1990-01-01",
        end: str | None = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch all registered FRED series.

        Returns:
            Dict mapping series_id to DataFrame
        """
        results = {}
        for series_id, meta in FRED_SERIES.items():
            try:
                df = await self.fetch_series(series_id, start=start, end=end)
                if not df.empty:
                    results[series_id] = df
                    logger.info(f"✅ {series_id} ({meta['name']}): {len(df)} records")
                else:
                    logger.warning(f"⚠️ {series_id} ({meta['name']}): no data")
            except Exception as e:
                logger.error(f"❌ {series_id} ({meta['name']}): {e}")

        logger.info(f"Fetched {len(results)}/{len(FRED_SERIES)} FRED series")
        return results

    async def fetch_series_info(self, series_id: str) -> dict:
        """Get metadata about a FRED series."""
        data = await self._request("/series", params={"series_id": series_id})
        return data.get("seriess", [{}])[0]
