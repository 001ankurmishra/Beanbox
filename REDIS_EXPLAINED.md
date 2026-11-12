# BeanBox Redis Architecture & Hands-On Guide (`REDIS_EXPLAINED.md`)

> A clean, practical learning guide to how **Redis** powers BeanBox's sliding-window rate limiting, versioned catalog caching, 30-second session validity cache, checkout idempotency keys, and live observability.

---

## 1. What Redis Is & Why It Is Fast

- **In-memory data structure store**: Data lives in RAM rather than spinning disk / SSD B-trees, avoiding disk seeks for hot reads and counters (`< 1 ms` local latency).
- **Single-threaded command execution**: Redis processes commands sequentially on one main event loop using OS I/O multiplexing (`epoll` / `kqueue`). Because two commands never mutate the same key simultaneously, Redis avoids mutexes, context switches, and lock contention.
- **Why Lua scripts are atomic**: When Redis executes a Lua script (`SCRIPT LOAD` + `EVALSHA`), the entire script runs from start to finish before the event loop handles any other client's command. No interleaved request can read or modify the sorted set in the middle of checking a rate limit.
- **Persistence (RDB & AOF) and why caches lose data**:
  - **RDB**: Periodic point-in-time snapshots saved to disk (fast restarts, loses writes since the last snapshot).
  - **AOF (Append-Only File)**: Logs every write command (`everysec` default loses up to ~1s on crash; `always` slows throughput).
  - **Golden rule for BeanBox**: Treat Redis as **ephemeral acceleration**, never the source of truth. Postgres (`Supabase`) owns all durable state (users, sessions, stock, orders, payments). If Redis wipes on restart, BeanBox degrades gracefully and warms up again.
- **Never store secrets or PII in Redis**: BeanBox stores only public catalog responses, anonymized IP rate-limit buckets, numeric counters, opaque session IDs (`"1"`), and idempotent response envelopes. Passwords, JWT secrets, OAuth tokens, and private account tokens never enter Redis.

---

## 2. Redis Data Types Used in BeanBox

| Redis Data Type | Commands Used | Used By BeanBox Feature | Why This Type? |
| :--- | :--- | :--- | :--- |
| **String (JSON / Flag / Lock)** | `GET`, `SET EX`, `SET NX EX`, `DEL` | Catalog Cache, Stampede Lock, Session Cache, Idempotency Store | O(1) lookup by key with native per-key `EX` expiration and atomic `NX` acquire |
| **String (Integer Counter)** | `INCR`, `MGET`, `EXPIRE` | Cache namespace version (`products:ver`), observability metrics (`hits`, `misses`, `blocks`, `replays`) | Atomic single-command increment without read-modify-write races |
| **Sorted Set (`ZSET`)** | `ZREMRANGEBYSCORE`, `ZCARD`, `ZRANGE`, `ZADD`, `PEXPIRE` | Sliding-window Rate Limiter (`Lua`) | Keeps request timestamps ordered by epoch ms score so expired windows prune cleanly in O(log N + M) |
| **Hash (Reference Note)** | `HSET`, `HGET`, `HINCRBY` | *(Documented pattern for multi-field objects)* | Useful when updating single fields inside a struct independently; BeanBox uses JSON strings for whole-payload GET/SET and atomic version counters |

---

## 3. Complete Inventory of Redis Keys in BeanBox

All keys are built inside [`backend/app/cache/keys.py`](backend/app/cache/keys.py) under `KEY_PREFIX = "beanbox:{APP_ENV}:"` (`development`, `test`, or `production`). **Every key has a positive TTL.**

| Key Pattern | Type | TTL | Who Writes | Who Reads | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `beanbox:{env}:ratelimit:{bucket}:{subject}` | `ZSET` | `60s` or `900s` (`window_seconds`) | `RedisRateLimiter` (Lua) | `RedisRateLimiter` (Lua) | Sliding-window request log (`score=now_ms`, `member=now_ms:uuid`) |
| `beanbox:{env}:cache:products:ver` | `STRING` (int) | `7 days` (`604800s`) | `RedisCatalogCache.invalidate_catalog` / lazy init | `RedisCatalogCache` | Namespace version bumped via `INCR` on product/inventory/order changes |
| `beanbox:{env}:cache:products:list:v{ver}:{hash}` | `STRING` (JSON) | `60s` | `RedisCatalogCache.get_or_set_list` | `RedisCatalogCache` | Cached `GET /api/products` list payload keyed by normalized query SHA-256 |
| `beanbox:{env}:cache:products:detail:v{ver}:{slug}` | `STRING` (JSON) | `300s` | `RedisCatalogCache.get_or_set_detail` | `RedisCatalogCache` | Cached `GET /api/products/{slug}` product detail payload |
| `beanbox:{env}:lock:{digest}` | `STRING` (token) | `5s` | `RedisCatalogCache` (`SET NX EX 5`) | `RedisCatalogCache` | Stampede mutex so concurrent misses only run 1 DB query |
| `beanbox:{env}:session:active:{sid}` | `STRING` (`"1"`) | `30s` | `require_user` -> `RedisSessionCache` | `require_user` | Fast session-active check; immediately `DEL`eted on any revocation |
| `beanbox:{env}:idem:{user_id}:{route}:{key}` | `STRING` (JSON) | `86400s` (24h) | `RedisIdempotencyStore` | `RedisIdempotencyStore` | Stores `in_progress` or final JSON response for `POST /orders` & `POST /payments/checkout-session` |
| `beanbox:{env}:stats:cache_hits` | `STRING` (int) | `7 days` | `RedisCatalogCache` | `/api/admin/cache-stats` | Cumulative catalog cache hit count |
| `beanbox:{env}:stats:cache_misses` | `STRING` (int) | `7 days` | `RedisCatalogCache` | `/api/admin/cache-stats` | Cumulative catalog cache miss count |
| `beanbox:{env}:stats:ratelimit_blocks` | `STRING` (int) | `7 days` | `RedisRateLimiter` | `/api/admin/cache-stats` | Cumulative HTTP 429 rate-limit blocks |
| `beanbox:{env}:stats:idempotent_replays` | `STRING` (int) | `7 days` | `RedisIdempotencyStore` | `/api/admin/cache-stats` | Cumulative replayed idempotent checkout responses |

> **Why Checkout, Cart & Stock Never Read the Cache**: Both `CartService.hydrate()` and `OrderService._resolve_cart_order_items()` always query `ProductRepository` directly. Cached catalog data may lag up to 60–300s between updates or Redis failures, whereas cart pricing and stock reservation require live authoritative DB rows.

---

## 4. Architecture & Flow Diagrams

### A. Versioned Cache-Aside + Stampede Lock (`GET /api/products/{slug}`)
```text
Client                    FastAPI (ProductService)                Redis                       Postgres
  |-- GET /products/chik --->|                                      |                            |
  |                          |-- GET cache:products:ver ----------->| (returns v3)               |
  |                          |-- GET products:detail:v3:chik ------>|                            |
  |                          |<-- nil (MISS) -----------------------|                            |
  |                          |                                      |                            |
  |  (20 parallel misses)    |-- SET lock:chik <tok> NX EX 5 ------>|                            |
  |   Thread 1 wins lock --->|                                      |                            |
  |   Threads 2..20 wait --->|-- poll GET detail every 20ms ------->|                            |
  |                          |-- SELECT product WHERE slug='chik' ------------------------------>|
  |                          |<-- Product row ---------------------------------------------------|
  |                          |-- SET detail:v3:chik JSON EX 300 --->|                            |
  |                          |-- INCR stats:cache_misses ---------->|                            |
  |                          |-- DEL lock:chik (if token matches) ->|                            |
  |<-- 200 X-Cache: MISS ----|                                      |                            |
  |   Waiters wake on poll ->|<-- JSON (now cached!) ---------------| (returns HIT, 0 extra DB)  |

Mutation (Admin inventory / Order reserve / Order cancel):
  Admin/OrderService ------->|-- INCR cache:products:ver ---------->| (v3 -> v4; old v3 keys TTL out!)
```

### B. Atomic Lua Sliding-Window Rate Limiter
```text
Request (IP=1.2.3.4) ---> FastAPI ---> RedisRateLimiter.check("login:1.2.3.4", limit=15, win=900s)
                                            |
                                            v (1 atomic EVALSHA call in Redis single thread)
                                     +-----------------------------------------------------+
                                     | 1. ZREMRANGEBYSCORE key -inf (now_ms - 900_000)     |
                                     | 2. count = ZCARD key                                |
                                     | 3. oldest = ZRANGE key 0 0 WITHSCORES -> reset_at   |
                                     | 4. IF count >= 15: PEXPIRE 900_000; RETURN {0,0,rst}|
                                     | 5. ZADD key now_ms member; PEXPIRE 900_000          |
                                     |    RETURN {1, 15 - count - 1, reset_at}             |
                                     +-----------------------------------------------------+
                                            |
                       allowed=1 -----------+----------- allowed=0
                           |                                 |
                           v                                 v
             Headers: X-RateLimit-Limit/Remaining/Reset    INCR stats:ratelimit_blocks
                                                           HTTP 429 + Retry-After header
```

### C. 30-Second Session Validity Cache & Immediate Revocation
```text
Normal Authenticated API Call:
  JWT verified (HS256) --> GET beanbox:{env}:session:active:{sid}
                                |
              HIT ("1") --------+-------- MISS (nil)
                  |                           |
                  v                           v
      Skip DB sessions lookup!       SELECT * FROM sessions WHERE id=sid
      Load user from DB              If valid -> SET session:active:{sid} "1" EX 30
      (require_admin ALWAYS loads role + totp_enabled fresh from DB!)

Any Revocation (logout, logout-all, revoke session, pw change/reset, role change, reuse):
  1. Collect target session ID(s) -> Revoke rows in Postgres `sessions`
  2. Immediately DEL beanbox:{env}:session:active:{sid...} in Redis
     (Tradeoff: if Redis DEL fails, log error; 30s TTL is max stale window)
```

### D. Checkout Idempotency State Machine (`POST /api/orders` & `/api/payments/checkout-session`)
```text
Client sends: Idempotency-Key: <uuid>
   |
   v
SET idem:{uid}:{route}:{key} {"state":"in_progress","bodyHash":H} NX EX 86400
   |
   +-- Acquired (1) --> Run create_order / create_session
   |                       |-- Succeeds -> SET key {"state":"done","bodyHash":H,"statusCode":201,"body":...} EX 86400
   |                       +-- Fails    -> DEL key (abort so user can retry cleanly)
   |
   +-- Exists (0) ----> GET key
                           |-- state == "in_progress" & hash == H --> 409 Conflict
                           |-- hash != H --------------------------> 422 Unprocessable Entity
                           +-- state == "done" & hash == H --------> INCR stats:idempotent_replays
                                                                     Return stored status + body
                                                                     Header: Idempotent-Replay: true
```

---

## 5. Failure Behavior Matrix

| Failure Scenario | What Happens Inside Redis Layer | What Users / App Experience |
| :--- | :--- | :--- |
| **Redis is down at boot** (`auto`) | `PING` fails; logs 1 warning and initializes `InMemoryRateLimiter` + no-op caches. | App boots and works 100% normally against Postgres/memory. `/api/health` shows `redis.enabled=false`. |
| **Redis goes down mid-run** (`SHUTDOWN` / dead port) | `RedisError` caught in each adapter (`ThrottledWarningLogger` warns at most once/60s). | Rate limiter falls back to process `InMemoryRateLimiter`; catalog goes straight to DB (`X-Cache: MISS`); auth reads DB `sessions`; idempotency bypasses safely. Zero 500 errors. |
| **Redis is slow (> 2s)** | Shared `ConnectionPool` enforces `socket_timeout=2`, `socket_connect_timeout=2`. | Fast 2s fail-open fallback prevents hanging worker threads or DB pool exhaustion. |
| **Redis restarts (empty memory)** | All keys gone; `products:ver` lazily re-initializes to `1`; counters reset cleanly. | Next reads see cache `MISS` and re-warm Redis automatically from Postgres. |
| **Redis `maxmemory` full** | With `allkeys-lru`, oldest cache/session keys evict gracefully; with `noeviction`, writes error -> fallback engages. | Recommend `allkeys-lru` so Redis drops cold entries instead of throwing OOM write errors. |

---

## 6. Eviction Policies: Why `allkeys-lru` Is Right for Caches (Not `noeviction`)

When Redis reaches `maxmemory`:
- **`noeviction`** (Redis default): Returns an error on EVERY write (`SET`, `INCR`, `ZADD`) once RAM is full. For a cache/rate-limiter tier, this turns memory pressure into constant write errors and fallback storms.
- **`volatile-lru`**: Evicts least-recently-used keys only among keys with a TTL (okay here since all BeanBox keys have TTLs, though any non-TTL key would still block eviction).
- **`allkeys-lru`** (**Recommended for BeanBox**): Evicts the least-recently-used key across the whole instance cleanly so hot products, active rate-limit windows, and fresh idempotency records stay in RAM while cold catalog queries drop naturally and fall back to Postgres.
- **`allkeys-lfu`**: Evicts least-frequently-used keys (also strong for hot catalog reads; requires tuning decay if traffic shifts).

---

## 7. REDIS LAB — 10 Hands-On Exercises (`redis-cli`)

Start Redis locally (e.g. `redis-server --port 6379` or `brew services start redis`), ensure `REDIS_URL=redis://localhost:6379/0` in `backend/.env`, and run both BeanBox backend & frontend.

### Exercise 1: Watch Live Commands with `MONITOR`
- **Run**: `redis-cli MONITOR` in Terminal 1 while clicking `/shop` and logging in on the site.
- **Expected output**: Live `GET "beanbox:development:cache:products:ver"`, `GET "beanbox:development:cache:products:list:v1:..."`, `EVALSHA ...`, and `SET "beanbox:development:session:active:..." "1" EX 30`. *(Stop `MONITOR` with `Ctrl+C` afterwards—never leave `MONITOR` running in production as it halves throughput!)*

### Exercise 2: Safely List Keys with `SCAN` (Never `KEYS *`)
- **Run**: `redis-cli SCAN 0 MATCH "beanbox:*" COUNT 100`
- **Expected output**: Cursor + array of keys like `"beanbox:development:cache:products:list:v1:..."` and `"beanbox:development:stats:cache_misses"`.

### Exercise 3: Inspect Remaining TTLs
- **Run**: `redis-cli TTL beanbox:development:cache:products:ver` and `redis-cli TTL <one-list-key>`
- **Expected output**: Integer seconds remaining (e.g. `604782` for version, `<= 60` for list, `<= 300` for product detail). Never `-1` (no TTL)!

### Exercise 4: Compare `X-Cache: MISS` vs `X-Cache: HIT`
- **Run**:
  ```bash
  curl -i http://localhost:4000/api/products | grep -i x-cache
  curl -i http://localhost:4000/api/products | grep -i x-cache
  ```
- **Expected output**: First prints `x-cache: MISS`; second prints `x-cache: HIT`.

### Exercise 5: Inspect Cached Product JSON with `GET`
- **Run**: `redis-cli GET "beanbox:development:cache:products:detail:v1:chikmagalur-baba-budangiri-arabica"`
- **Expected output**: Compact JSON string of the public product + variants (`pricePaise`, `stock`, `slug`) with zero customer PII.

### Exercise 6: Bump Cache Version & Watch Old Keys Become Invisible
- **Run**: `redis-cli GET beanbox:development:cache:products:ver` then `redis-cli DEL beanbox:development:cache:products:ver` (or `INCR`), then `curl -i http://localhost:4000/api/products | grep -i x-cache`.
- **Expected output**: Even though old `v1` keys still exist briefly until their 60s TTL expires, the next request sees `X-Cache: MISS` immediately with zero `SCAN`-delete!

### Exercise 7: Inspect Sliding-Window Limiter ZSET (`ZRANGE`)
- **Run**: Trigger 2 requests to `/api/products`, then run:
  `redis-cli ZRANGE "beanbox:development:ratelimit:general:127.0.0.1" 0 -1 WITHSCORES`
- **Expected output**: Alternating `member` (`"<ms>:<hex>"`) and `score` (`"<epoch_ms>"`) pairs showing exact timestamps in milliseconds.

### Exercise 8: Trigger 429 Rate Limit & Check Headers
- **Run**: Hit `/api/auth/login` rapidly > `RATE_LIMIT_LOGIN_MAX` times with `curl -i`:
  `for i in {1..16}; do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:4000/api/auth/login -H "Content-Type: application/json" -d '{"email":"x@y.in","password":"wrong"}'; done`
- **Expected output**: First 15 return `401`, 16th returns `429` with `X-RateLimit-Remaining: 0` and `Retry-After`.

### Exercise 9: Verify Idempotency Replay (`Idempotent-Replay: true`)
- **Run**: Send two identical `POST /api/orders` calls with the same `Idempotency-Key: demo-1234`, then run `redis-cli GET "beanbox:development:idem:<userId>:orders:create:demo-1234"`.
- **Expected output**: First order succeeds `201`; second returns exact same JSON with header `Idempotent-Replay: true`; `GET` shows `{"state":"done","bodyHash":...,"statusCode":201,...}`.

### Exercise 10: `SHUTDOWN` Redis & Watch BeanBox Keep Working
- **Run**: `redis-cli SHUTDOWN NOSAVE`, then browse `/shop`, check `curl http://localhost:4000/api/health`, and visit `/admin/cache`.
- **Expected output**: `health` returns `"redis": {"enabled": ..., "connected": false, "latencyMs": null}` (`enabled: false` if `auto` at boot, `true` if started `true` or connected before shutdown); products still load (`X-Cache: MISS`), auth falls back to Postgres `sessions`, and zero 500 errors occur!

---

## 8. What Companies Add Beyond This

1. **Redis Cluster vs Redis Sentinel**:
   - **Sentinel** adds high-availability leader/replica monitoring and automatic failover for a single primary dataset.
   - **Redis Cluster** shards keys across 16,384 hash slots over multiple nodes for horizontal RAM/throughput scaling (requires `{hash_tag}` key naming so multi-key Lua scripts hit the same slot).
2. **Redis Streams (`XADD` / `XREADGROUP`)**: Durable append-only event logs with consumer groups, ACKs, and replay for order events, email dispatch, and analytics pipelines.
3. **Pub/Sub (`PUBLISH` / `SUBSCRIBE`)**: Fire-and-forget real-time broadcasting (live inventory UI updates, cross-instance local L1 cache invalidation).
4. **Distributed Locks (`SET NX PX` vs Redlock)**: A single-node lock + Lua release works for short advisory stampede control. Multi-node **Redlock** attempts majority quorum locking across independent masters — famously debated by Martin Kleppmann vs Antirez over GC pauses and clock drift, which is why strict correctness uses **fencing tokens** checked by Postgres rather than locks alone.
5. **Background Job Queues**: Tools like **ARQ**, **Celery**, or **BullMQ** store retryable async jobs (receipt PDFs, emails, webhooks) in Redis lists/sorted sets/streams with dead-letter queues.
