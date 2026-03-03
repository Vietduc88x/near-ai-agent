"""Shared API helpers for NEAR AI marketplace.

Both bidder.py and deliverer.py import from here to avoid duplication (M-6).
Includes retry logic with exponential backoff for 503/5xx errors.
"""

import logging
import time

import requests

from config import API_BASE, HEADERS

log = logging.getLogger("autobidder")

# Retry config — market.near.ai returns 503 frequently via Fastly CDN
_MAX_RETRIES = 5
_RETRY_BACKOFF = 1.5  # seconds, multiplied each retry
_RETRYABLE_CODES = {502, 503, 504, 429}


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """Make an HTTP request with exponential backoff on transient errors."""
    delay = _RETRY_BACKOFF
    last_exc = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            r = requests.request(method, url, **kwargs)
            if r.status_code not in _RETRYABLE_CODES or attempt == _MAX_RETRIES:
                return r
            log.warning(f"  Retry {attempt+1}/{_MAX_RETRIES}: {method} {url} → {r.status_code}")
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt == _MAX_RETRIES:
                raise
            log.warning(f"  Retry {attempt+1}/{_MAX_RETRIES}: {method} {url} → {e}")

        time.sleep(delay)
        delay *= 2  # exponential backoff: 1.5s, 3s, 6s, 12s, 24s

    # Should not reach here, but just in case
    if last_exc:
        raise last_exc
    return r


def api_get(path: str, params: dict = None) -> dict | list | None:
    """Make authenticated GET request with retry."""
    try:
        r = _request_with_retry(
            "GET", f"{API_BASE}{path}",
            headers=HEADERS, params=params, timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"GET {path} failed: {e}")
        return None


def api_post(path: str, data: dict) -> dict | None:
    """Make authenticated POST request with retry.

    Returns parsed JSON on success, a dict with 'error' and 'status_code'
    keys on 409 (duplicate bid), or None on other failures.
    """
    try:
        r = _request_with_retry(
            "POST", f"{API_BASE}{path}",
            headers=HEADERS, json=data, timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        body = e.response.text[:200]
        if status == 409:
            log.debug(f"POST {path}: 409 duplicate bid")
            return {"error": "duplicate", "status_code": 409}
        log.error(f"POST {path} failed: {status} {body}")
        return None
    except Exception as e:
        log.error(f"POST {path} failed: {e}")
        return None


def get_my_bids() -> list[dict]:
    """Fetch our current bids from the marketplace."""
    bids = api_get("/v1/agents/me/bids")
    return bids or []
