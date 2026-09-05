"""Ограниченные запросы к фиксированным провайдерам, без пользовательских URL."""

import math
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx


class ProviderError(RuntimeError):
    def __init__(self, code, message, *, provider, retryable=False):
        super().__init__(message)
        self.code, self.provider, self.retryable = code, provider, retryable


def get_json(url, *, params=None, provider, timeout=30):
    for attempt in range(3):
        try:
            response = httpx.get(
                url,
                params=params,
                timeout=timeout,
                follow_redirects=False,
                headers={"User-Agent": "TerraLens/0.1 (agricultural research prototype)"},
            )
        except httpx.RequestError as exc:
            if attempt < 2:
                time.sleep(0.5 * 2**attempt + random.uniform(0, 0.25))
                continue
            raise ProviderError(
                "provider_timeout", "Источник не ответил вовремя", provider=provider, retryable=True
            ) from exc
        if response.status_code in (401, 403):
            raise ProviderError(
                "provider_auth_required", "Источник требует настройки доступа", provider=provider
            )
        if response.status_code == 429 or response.status_code >= 500:
            retry_after = response.headers.get("Retry-After", "1")
            try:
                delay = float(retry_after)
            except ValueError:
                try:
                    delay = max(0, (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds())
                except (ValueError, TypeError):
                    delay = 1
            if not math.isfinite(delay):
                delay = 11
            if attempt < 2 and delay <= 10:
                time.sleep(max(delay, 0.5 * 2**attempt) + random.uniform(0, 0.25))
                continue
            raise ProviderError(
                "provider_rate_limited" if response.status_code == 429 else "provider_unavailable",
                "Источник временно недоступен",
                provider=provider,
                retryable=True,
            )
        if not response.is_success:
            raise ProviderError(
                "provider_schema_changed", f"Источник вернул HTTP {response.status_code}", provider=provider
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(
                "provider_schema_changed", "Источник вернул некорректный JSON", provider=provider
            ) from exc


def snapshot(provider, query, data, warnings=None):
    return {
        "provider": provider,
        "query": query,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "data": data,
        "warnings": warnings or [],
    }
