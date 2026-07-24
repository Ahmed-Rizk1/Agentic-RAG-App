import hashlib
import json
import logging
import time
from typing import Optional, Any
import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._memory_cache: dict[str, tuple[float, Any]] = {}
        self._redis_available: bool = False

    async def initialize(self):
        """Connects to Redis with automatic fallback to in-memory dict."""
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2.0
            )
            await self._redis.ping()
            self._redis_available = True
            logger.info("Connected to Redis server successfully.")
        except Exception as e:
            self._redis_available = False
            logger.warning(f"Redis unavailable ({e}). Falling back to in-memory caching.")

    async def get(self, key: str) -> Optional[Any]:
        if self._redis_available and self._redis:
            try:
                data = await self._redis.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.error(f"Redis GET error for key '{key}': {e}")
        
        # In-memory fallback check
        if key in self._memory_cache:
            exp_time, value = self._memory_cache[key]
            if time.time() < exp_time:
                return value
            else:
                del self._memory_cache[key]
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> bool:
        serialized = json.dumps(value)
        if self._redis_available and self._redis:
            try:
                await self._redis.set(key, serialized, ex=ttl_seconds)
                return True
            except Exception as e:
                logger.error(f"Redis SET error for key '{key}': {e}")

        # In-memory fallback set
        exp_time = time.time() + ttl_seconds
        self._memory_cache[key] = (exp_time, value)
        return True

    def hash_text(self, text: str) -> str:
        """Helper to create a deterministic SHA256 key from query or chunk text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def get_embedding(self, text: str) -> Optional[list[float]]:
        key = f"emb:{self.hash_text(text)}"
        return await self.get(key)

    async def set_embedding(self, text: str, embedding: list[float], ttl_seconds: int = 86400):
        key = f"emb:{self.hash_text(text)}"
        await self.set(key, embedding, ttl_seconds=ttl_seconds)

cache_service = CacheService()
