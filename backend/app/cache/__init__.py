"""
BeanBox Redis caching, rate-limiting, session validity, and idempotency layer.

Follows the same interface-first Repository Pattern used across BeanBox:
- Interfaces in `app.cache.interfaces`
- Key schema in `app.cache.keys`
- Redis implementations (`RedisRateLimiter`, `RedisCatalogCache`, `RedisSessionCache`, `RedisIdempotencyStore`)
- In-memory / no-op fallbacks when Redis is disabled or temporarily unreachable
"""
