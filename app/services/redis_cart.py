# app/services/redis_cart.py
import json
import redis.asyncio as aioredis
from config import settings

# Подключаемся к Redis
redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def add_to_cart(tg_id: int, product_id: int):
    """Добавить товар в корзину"""
    key = f"cart:{tg_id}"
    current_cart = await redis_client.get(key)
    cart_list = json.loads(current_cart) if current_cart else []

    # Проверяем, есть ли уже такой товар (увеличиваем кол-во, если да)
    for item in cart_list:
        if item['product_id'] == product_id:
            item['qty'] += 1
            await redis_client.set(key, json.dumps(cart_list))
            return

    cart_list.append({"product_id": product_id, "qty": 1})
    await redis_client.set(key, json.dumps(cart_list))


async def get_cart(tg_id: int) -> list:
    """Получить корзину"""
    key = f"cart:{tg_id}"
    val = await redis_client.get(key)
    return json.loads(val) if val else []


async def clear_cart(tg_id: int):
    """Очистить корзину"""
    await redis_client.delete(f"cart:{tg_id}")