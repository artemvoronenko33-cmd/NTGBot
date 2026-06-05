import hashlib
import hmac
import json
import time
from dataclasses import dataclass

import httpx

from config import settings

_BASE = "https://api.westwallet.io"


def _headers(data: dict | None) -> dict:
    ts = int(time.time())
    body = json.dumps(data, ensure_ascii=False) if data else ""
    sign = hmac.new(
        settings.WW_PRIVATE_KEY.encode(),
        f"{ts}{body}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-API-KEY": settings.WW_PUBLIC_KEY,
        "X-ACCESS-SIGN": sign,
        "X-ACCESS-TIMESTAMP": str(ts),
        "Content-Type": "application/json",
    }


@dataclass
class InvoiceResult:
    token: str
    url: str


async def create_invoice(
    order_id: int,
    amount_usd: float,
    currencies: list[str] | None = None,
) -> InvoiceResult:
    if currencies is None:
        currencies = settings.WW_CURRENCIES

    ipn_url = f"{settings.WEBHOOK_BASE_URL}/webhook/ipn"

    data = {
        "currencies": currencies,
        "amount": round(amount_usd, 2),
        "amount_in_usd": True,
        "ipn_url": ipn_url,
        "label": str(order_id),
        "description": f"Order #{order_id}",
        "ttl": 90,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_BASE}/address/create_invoice",
            content=json.dumps(data, ensure_ascii=False),
            headers=_headers(data),
            timeout=15,
        )
    resp.raise_for_status()
    body = resp.json()
    if body.get("error") != "ok":
        raise RuntimeError(f"WestWallet: {body.get('error')}")
    return InvoiceResult(token=body["token"], url=body["url"])


@dataclass
class AddressResult:
    address: str
    dest_tag: str
    currency: str
    label: str


async def generate_address(label: str, currency: str = "USDTTRC") -> AddressResult:
    """Генерирует одноразовый адрес для пополнения баланса."""
    ipn_url = f"{settings.WEBHOOK_BASE_URL}/webhook/ipn"
    data = {
        "currency": currency,
        "ipn_url": ipn_url,
        "label": label,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_BASE}/address/generate",
            content=json.dumps(data, ensure_ascii=False),
            headers=_headers(data),
            timeout=15,
        )
    resp.raise_for_status()
    body = resp.json()
    if body.get("error") != "ok":
        raise RuntimeError(f"WestWallet: {body.get('error')}")
    return AddressResult(
        address=body["address"],
        dest_tag=body.get("dest_tag", ""),
        currency=body.get("currency", currency),
        label=body.get("label", label),
    )


async def verify_transaction(label: str) -> dict:
    """Проверяет транзакцию через API для защиты от спуфинга IPN."""
    data = {"label": label}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_BASE}/wallet/transaction",
            content=json.dumps(data, ensure_ascii=False),
            headers=_headers(data),
            timeout=15,
        )
    resp.raise_for_status()
    return resp.json()
