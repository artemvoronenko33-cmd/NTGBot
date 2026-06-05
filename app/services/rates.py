import asyncio
import logging
import math
import time

import httpx

logger = logging.getLogger(__name__)

# WestWallet ticker → CoinGecko coin ID
_GECKO_IDS: dict[str, str] = {
    "USDTTRC": "tether",
    "USDTBEP": "tether",
    "ETH":     "ethereum",
    "LTC":     "litecoin",
    "BTC":     "bitcoin",
    "BNB":     "binancecoin",
    "SOL":     "solana",
    "XMR":     "monero",
}

_CACHE_TTL = 60.0  # сек
_cache: dict[str, tuple[float, float]] = {}  # gecko_id -> (price_usd, ts)
_lock = asyncio.Lock()


async def _fetch_all_prices() -> dict[str, float]:
    """Один batch-запрос в CoinGecko по всем уникальным монетам."""
    unique_ids = sorted(set(_GECKO_IDS.values()))
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ",".join(unique_ids), "vs_currencies": "usd"},
            timeout=15,
        )
    resp.raise_for_status()
    data = resp.json()
    result: dict[str, float] = {}
    for gid in unique_ids:
        if gid in data and "usd" in data[gid]:
            result[gid] = float(data[gid]["usd"])
    return result


async def _refresh_cache_if_stale() -> None:
    now = time.time()
    unique_ids = set(_GECKO_IDS.values())
    async with _lock:
        fresh = all(
            gid in _cache and now - _cache[gid][1] < _CACHE_TTL
            for gid in unique_ids
        )
        if fresh:
            return

    try:
        prices = await _fetch_all_prices()
    except httpx.HTTPStatusError as e:
        # Не падаем если есть старый кэш — отдаём его
        logger.warning("CoinGecko %s — используем старый кэш", e.response.status_code)
        return
    except Exception as e:
        logger.warning("Ошибка CoinGecko: %s — используем старый кэш", e)
        return

    async with _lock:
        for gid, price in prices.items():
            _cache[gid] = (price, now)
    logger.info("Курсы обновлены: %s", {k: v[0] for k, v in _cache.items()})


async def get_price_usd(ticker: str) -> float:
    """Возвращает цену 1 единицы монеты в USD (кэш 60с, batch-обновление)."""
    gecko_id = _GECKO_IDS.get(ticker)
    if not gecko_id:
        raise ValueError(f"Неизвестная монета: {ticker}")

    await _refresh_cache_if_stale()

    async with _lock:
        cached = _cache.get(gecko_id)
    if not cached:
        raise RuntimeError(f"Курс {ticker} недоступен")
    return cached[0]


def usd_to_crypto(amount_usd: float, price_usd: float, decimals: int = 8) -> float:
    """Конвертирует USD в crypto, округляя ВВЕРХ (защита от недоплаты)."""
    if price_usd <= 0:
        raise ValueError("Цена должна быть положительной")
    raw = amount_usd / price_usd
    factor = 10 ** decimals
    return math.ceil(raw * factor) / factor
