"""
api.py — Cardmarket API v2.0 client with HMAC-SHA1 OAuth signing.

API docs: https://www.cardmarket.com/en/Developer/API

Requires the user to register a developer application at:
  https://www.cardmarket.com/en/Developer
"""

from __future__ import annotations

import time
import json
import logging
from typing import Any
from urllib.parse import urlencode

import requests
from requests_oauthlib import OAuth1

logger = logging.getLogger(__name__)

API_BASE = "https://api.cardmarket.com/ws/v2.0/output.json"


class CardmarketAPI:
    """Thin wrapper around the Cardmarket REST API v2.0."""

    def __init__(self, app_token: str, app_secret: str,
                 access_token: str, access_secret: str,
                 request_delay: float = 1.0):
        self._auth = OAuth1(
            app_token, app_secret, access_token, access_secret,
            signature_type="AUTH_HEADER",
        )
        self._delay = request_delay
        self._last_call = 0.0
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "MTGPriceTracker/1.0",
        })

    # -----------------------------------------------------------------
    # Rate-limited request
    # -----------------------------------------------------------------

    def _request(self, method: str, path: str,
                 params: dict | None = None,
                 data: dict | None = None) -> dict[str, Any]:
        """Make a rate-limited signed API call."""
        elapsed = time.time() - self._last_call
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        url = f"{API_BASE}{path}"
        logger.debug("→ %s %s", method, url)

        resp = self._session.request(
            method, url,
            auth=self._auth,
            params=params,
            json=data,
            timeout=30,
        )
        self._last_call = time.time()

        if resp.status_code == 429:
            retry = int(resp.headers.get("Retry-After", 10))
            logger.warning("Rate limited — waiting %ds", retry)
            time.sleep(retry)
            return self._request(method, path, params, data)

        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str, **params) -> dict[str, Any]:
        return self._request("GET", path, params=params or None)

    # -----------------------------------------------------------------
    # Product endpoints
    # -----------------------------------------------------------------

    def find_product(self, search: str, game: int = 1) -> list[dict]:
        """
        Search products by name.
        game=1 → Magic: The Gathering.
        Returns a list of product dicts on success.
        """
        data = self._get("/products/find", search=search, idGame=game,
                         idLanguage=1, start=0, maxResults=20)
        return data.get("product", [])

    def get_product(self, product_id: int) -> dict[str, Any] | None:
        """
        Full product details including price guides.
        Returns None if not found.
        """
        data = self._get(f"/products/{product_id}")
        return data.get("product")

    def get_product_prices(self, product_id: int) -> dict[str, Any] | None:
        """
        Price guide for a single product.
        Fields: AVG, TREND, LOW, 30DAYAVG, LOWEX.
        """
        prod = self.get_product(product_id)
        if not prod:
            return None
        return {
            "id": product_id,
            "name": prod.get("enName"),
            "price_avg": prod.get("priceGuide", {}).get("AVG"),
            "price_trend": prod.get("priceGuide", {}).get("TREND"),
            "price_low": prod.get("priceGuide", {}).get("LOW"),
            "price_30day": prod.get("priceGuide", {}).get("30DAYAVG"),
            "listings_count": prod.get("countArticles"),
            "currency": prod.get("currency", "EUR"),
        }

    def verify_credentials(self) -> bool:
        """Quick check: fetch account info to verify API credentials."""
        try:
            data = self._get("/account")
            return "account" in data
        except Exception as exc:
            logger.error("Credential check failed: %s", exc)
            return False
