# BeanBox Background Jobs & Distributed Task Queue (`Celery + Redis`)

A production-grade, observable background job processing architecture for BeanBox built with **Celery 5.6**, **Redis 7 (DB 1)**, **FastAPI**, and **PostgreSQL**.

---

## 1. What a Job Queue Is & Why Work Moves Out of the Request

In a synchronous web request, the client (browser or mobile app) opens an HTTP connection and blocks waiting for the backend to respond.

```text
SYNCHRONOUS (SLOW & FRAGILE):
Client ──[ POST /api/orders ]──► FastAPI ──► Insert DB
                                              │
                                              ├─► Call Stripe API (350ms)
                                              ├─► Connect SMTP & Send Email (900ms)
                                              └─► Flush Audit Logs (50ms)
Client ◄──[ 201 Created (1.3s) ]──────────────┘
(If SMTP or Stripe times out, the user gets a 500 error even though order was placed!)

ASYNCHRONOUS WITH JOB QUEUE (FAST & BULLETPROOF):
Client ──[ POST /api/orders ]──► FastAPI ──► Insert DB
                                              │
                                              ├─► LPUSH emails queue (1ms)
Client ◄──[ 201 Created (15ms) ]──────────────┘
                                              │
                    Redis Broker (DB 1) ──────┘
                         │
                         ▼ (Pulls in background)
                   Celery Worker ──► Send Email with Retries & Deduplication
```

### Why Background Jobs Exist:
1. **Request Latency Reduction**: Moves slow network calls (emails, PDFs, digests, inventory scans) out of the critical path so API endpoints respond in <20ms.
2. **Failure Isolation & High Availability**: If the mail server is down or slow, the customer's checkout or signup **never** fails with a 500 error.
3. **Resilience & Automatic Retries**: Network glitches, third-party API rate limits, or transient database disconnects are retried automatically with exponential backoff and jitter.
4. **Traffic Smoothing**: During a sale or marketing spike, 10,000 orders can be placed in minutes without overloading external APIs. The worker processes tasks at a sustained, bounded concurrency rate.

---

## 2. ASCII Task Lifecycle Diagram

```text
+------------------------------------------------------------------------------------+
|                                 FASTAPI PRODUCER                                    |
|  enqueue_email("welcome", {"user_id": "u-123"})                                     |
|  - Validates IDs only (Zero PII / Passwords)                                        |
|  - Injects correlation request_id                                                  |
|  - Serializes to JSON (Kombu)                                                      |
+------------------------------------------------------------------------------------+
                                           |
                                           |  1. redis.rpush("emails", task_json)
                                           v
+------------------------------------------------------------------------------------+
|                                REDIS BROKER (DB 1)                                  |
|  List: "emails"        [ task_3, task_2, task_1 ]                                  |
|  ZSet: "unacked"       [ (task_1, expiry_timestamp) ] (visibility_timeout=3600)    |
+------------------------------------------------------------------------------------+
                                           |
                                           |  2. BRPOPLPUSH / Fetch task
                                           v
+------------------------------------------------------------------------------------+
|                                CELERY PREFORK WORKER                               |
|  Process 1 (Child Process, PID 48210, Prefetch=1):                                  |
|  - Forks from supervisor (worker_process_init resets pools)                         |
|  - Opens lazy DB pool (max_size=2) & Redis connection                              |
|  - Checks deduplication key: SET NX EX 86400 email:welcome:u-123                   |
|    * If False -> Return {"status": "skipped", "reason": "duplicate"}               |
|    * If True  -> Dispatch email via ConsoleEmailService                            |
|  - Logs: task_id, task_name, attempt number, duration_ms                            |
+------------------------------------------------------------------------------------+
                                           |
                                           |  3. ACK message (task_acks_late=True)
                                           v
+------------------------------------------------------------------------------------+
|  Redis removes task from unacked set. If worker dies before step 3,               |
|  Redis redelivers task automatically after visibility timeout!                     |
+------------------------------------------------------------------------------------+
```

---

## 3. At-Least-Once Delivery & Idempotency

BeanBox configures Celery for **at-least-once delivery**:
- `task_acks_late = True`: The worker sends the acknowledgment **only after** the task successfully finishes executing.
- `task_reject_on_worker_lost = True`: If a worker child process is killed (`SIGKILL`, OOM, server reboot) mid-task, Celery rejects the unacknowledged message so another worker can re-claim it.
- `broker_transport_options = {"visibility_timeout": 3600}`: If a task remains unacknowledged for 1 hour, Redis makes it visible to other workers.

### Why Duplicates Happen in Distributed Queues:
1. **Worker crash right after completion**: The worker finished sending an email, but crashed before sending the ACK to Redis.
2. **Network partition during ACK**: The task finished, but a transient network dropout caused the ACK packet to drop.
3. **Task duration exceeds visibility timeout**: If a task hangs or takes longer than `visibility_timeout`, the broker assumes the worker died and delivers a duplicate to another worker.

### How Every BeanBox Task Achieves Idempotency:

| Task Name | Queue | Idempotency Mechanism | Duplicate Delivery Result |
| :--- | :--- | :--- | :--- |
| `send_email_task` | `emails` | Redis `SET NX EX 86400 email:{kind}:{id}` before sending | Second delivery returns `{"status": "skipped", "reason": "duplicate"}`. Zero duplicate emails sent. |
| `expire_unpaid_orders` | `maintenance` | Atomic conditional UPDATE: `WHERE status='pending' AND stock_released=false RETURNING *` | First claim returns 1 row and releases stock. Subsequent runs return 0 rows and do nothing. |
| `cleanup_expired_auth_data` | `maintenance` | Conditional DELETE query: `WHERE expires_at < NOW()` | If already purged, deletes 0 rows and logs `0 cleaned`. |
| `low_stock_digest` | `maintenance` | Protected by Redis distributed lock (`SET NX EX 300`) | Second run fails to acquire lock and exits cleanly without duplicating digest. |

---

## 4. Retries, Exponential Backoff, Jitter & Dead Letters

Transient network blips and third-party API rate limits should retry automatically. However, naive retries immediately stampede downstream services. BeanBox uses **exponential backoff with randomized jitter**.

### Retry Timeline:
```text
Failure 1 ──► Retry 1 (~1s + jitter) ──► Retry 2 (~2s + jitter) ──► Retry 3 (~4s + jitter) ──► Retry 4 (~8s + jitter) ──► Retry 5 (~16s + jitter) ──► DEAD LETTER TABLE
   (0s)               (1.23s)                   (2.45s)                   (4.88s)                   (9.12s)                  (17.41s)               (failed_jobs)
```

- **Exponential Backoff**: Each delay doubles ($2^{\text{attempt}}$).
- **Randomized Jitter**: Prevents the **Thundering Herd** problem where 500 tasks that failed at the exact same second all retry simultaneously, bringing the downstream service back down.
- **Max Retries**: Capped at 5 attempts.

### Dead Letters (`failed_jobs` table):
When all 5 retries are exhausted, the task executes Celery's `on_failure` hook in `TrackedTask`.
It writes a dead-letter row to the PostgreSQL `failed_jobs` table:
- `id`: UUID primary key.
- `task_name`: Full task namespace (e.g. `app.worker.tasks_email.send_email_task`).
- `args_json`: Sanitized task arguments (contains **IDs only**; passwords, tokens, and PII are redacted).
- `error_message`: Concise exception summary.
- `traceback`: Full Python stack trace, truncated to 4KB (4,096 bytes) to protect DB storage.
- `attempts`: 5.
- `queue`: `emails` or `maintenance`.
- `created_at`: ISO 8601 timestamp.
- `resolved_at`: `NULL` until re-enqueued by an admin.

Admins can view all dead letters on the **Admin Jobs Dashboard** (`/admin/jobs`) and click **"Retry Task"** to re-dispatch the job to its original queue via `POST /api/admin/jobs/failed/{id}/retry`.

---

## 5. The Expire-vs-Webhook Race Condition

When a customer initiates checkout, BeanBox reserves stock and marks the order as `status='pending'`.
If the order is not paid within `PENDING_ORDER_TTL_MINUTES=30`, the `expire_unpaid_orders` job runs to release reserved stock.

What happens if the customer completes payment at the exact millisecond the expiry job runs?

```text
       THREAD A (Scheduled Expiry)               THREAD B (Payment Webhook)
                   │                                         │
                   ▼                                         ▼
   UPDATE orders                               UPDATE orders
   SET status='cancelled',                     SET status='paid',
       stock_released=true,                        paid_at=NOW()
       cancel_reason='payment_timeout'         WHERE id=%s
   WHERE id=%s                                   AND status='pending'
     AND status='pending'                      RETURNING *;
     AND stock_released=false
   RETURNING *;
                   │                                         │
                   ├─────────────────────────────────────────┤
                   │       POSTGRES ROW-LEVEL LOCK           │
                   │  Only ONE transaction can acquire row   │
                   └─────────────────────────────────────────┘
```

### Two Possible Race Outcomes:
1. **Payment Webhook wins first**:
   - Webhook updates status to `paid`.
   - Expiry job query runs second: the `WHERE status='pending'` clause finds 0 rows.
   - Result: Order stays `paid`, stock is kept, customer gets confirmation email.
2. **Expiry Job wins first**:
   - Expiry job sets status to `cancelled`, releases stock and coupon, returns 1 row.
   - Payment Webhook arrives late: the `WHERE status='pending'` clause returns 0 rows.
   - **Late-Payment Handling**: The webhook service detects that money was captured for an already-cancelled order. It:
     1. Records the payment event idempotently in `payment_events`.
     2. Triggers an automatic refund via `payment_provider.refund_payment`.
     3. Updates order `payment_status='refunded'`.
     4. Dispatches an `order_refunded` customer notification email explaining the timeout.
     5. Writes an audit log record: `order.late_payment_refunded`.

---

## 6. Celery Beat Periodic Scheduler & Overlap Protection

Celery Beat is a clock process that monitors the schedule in `celery_app.py` and pushes task messages to Redis at specified intervals:
- `expire_unpaid_orders`: Every 60 seconds (`schedule=60.0`).
- `cleanup_expired_auth_data`: Hourly at minute `:00` (`crontab(minute=0)`).
- `low_stock_digest`: Daily at 09:00 IST (`crontab(hour=9, minute=0)` with `timezone="Asia/Kolkata"`).

> [!IMPORTANT]
> **Beat MUST run as exactly ONE instance.**
> Beat has no built-in leader election. If two Beat processes are started, both will push periodic ticks to Redis, doubling task volume.

### Overlap Protection via Distributed Lock (`locks.py`)
What if an expiry scan takes 70 seconds to finish, but Beat triggers every 60 seconds? Or what if an operator accidentally launches two Beat instances?
BeanBox wraps all scheduled tasks in `task_lock`:
```python
with task_lock(redis_client, "expire_unpaid_orders", timeout=55) as acquired:
    if not acquired:
        logger.warning("Another instance of expire_unpaid_orders is currently running; skipping.")
        return {"status": "skipped", "reason": "lock_held"}
    ...
```
- **Acquire**: Redis `SET beanbox:locks:{name} {token} NX EX {timeout}` (atomic).
- **Release**: Atomic Lua script that compares the stored token against the process's token before deleting, preventing a slow process from deleting another process's newly-acquired lock.

---

## 7. Fork Safety Architecture: Why Pools Are Lazy

Celery's default `prefork` pool operates by importing Python modules in a master supervisor process, then calling the POSIX system call `os.fork()` to create child workers.

```text
Supervisor Process (PID 1000)
 ├── Imports celery_app.py, repositories, database connection pools
 ├── Opens TCP socket to Postgres (FD 3) & Redis (FD 4)
 └── Forks child processes:
      ├── Child 1 (PID 1001) inherits FD 3 & FD 4
      └── Child 2 (PID 1002) inherits FD 3 & FD 4
```

> [!CAUTION]
> If connection pools are opened before `os.fork()`, Child 1 and Child 2 will read and write to the **exact same TCP socket** at the same time. This causes intermittent SSL protocol corruption, packet interleaving, and broken connections.

### BeanBox Fork-Safety Implementation:
1. We listen to Celery's `worker_process_init` signal in `celery_app.py`.
2. The signal handler invokes `reset_worker_state()`, resetting all inherited connection variables to `None`.
3. Database connection pools and Redis clients are opened **lazily** inside each child process.
4. **Worker DB Pool `max_size=2`**:
   - Each worker child process runs 1 task at a time (`prefetch_multiplier=1`).
   - `max_size=2` provides 1 connection for the task query plus at most 1 spare connection for dead-letter/audit logging.
   - This prevents a cluster of 20 Celery workers from exhausting PostgreSQL connection limits (e.g. Supabase connection ceilings).

---

## 8. Failure Matrix

| Failure Scenario | Immediate System Reaction | Recovery & Data Consistency Guarantee |
| :--- | :--- | :--- |
| **Worker killed mid-task (`kill -9`)** | Process dies before sending ACK. Redis keeps message in `unacked` ZSet. | When `visibility_timeout=3600` expires (or worker supervisor restarts), Redis redelivers task. Idempotency guarantees safe re-execution. |
| **Redis Broker down during request** | `enqueue_email()` catches `redis.exceptions.ConnectionError`. | Logs warning and immediately dispatches email inline as fallback. Checkout and signup **never** fail. |
| **Task raises unhandled Exception** | `TrackedTask` captures exception, increments attempt count. | Retries with exponential backoff + jitter up to 5 times. If all fail, records dead-letter row to `failed_jobs` table. |
| **Duplicate task delivery** | Worker receives identical message twice from Redis. | Redis `SET NX EX` dedupe key check (`email:{kind}:{id}`) detects prior execution and drops duplicate with 0 side effects. |
| **Beat instance dies** | Scheduled tasks pause (no ticks pushed to broker). | When Beat restarts, scheduled jobs resume immediately. Distributed locks prevent stampede. |
| **Two Beat instances started accidentally** | Both instances push ticks to Redis queues. | Tasks take `task_lock` (`SET NX EX`). First worker acquires lock; second worker skips run. |
| **Heavy queue backlog** | Tasks accumulate in Redis lists (`emails`, `default`). | Workers drain tasks steadily without crashing the API or exceeding PostgreSQL connection limits. |

---

## 9. Distributed Job Queue Comparison

| Feature | Celery (Our Choice) | ARQ | RQ | BullMQ | AWS SQS |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Language** | Python | Python (asyncio) | Python | Node.js / TypeScript | Language-agnostic |
| **Broker** | Redis, RabbitMQ, SQS | Redis | Redis | Redis | AWS Managed SQS |
| **Concurrency Model** | Prefork (multiprocess), Threads, Gevent | Asyncio event loop | Forking process per job | Node event loop / Worker threads | Polling HTTP workers |
| **Periodic Scheduler** | Built-in (Celery Beat) | Built-in cron | `rq-scheduler` | Built-in repeatable jobs | EventBridge / CloudWatch |
| **Prefetch & Acks Late** | Yes (`prefetch=1`, `acks_late=True`) | No (simple pop) | No | Yes | Yes (Visibility Timeout) |
| **Dead-Letter Storage** | Pluggable (custom table / queue) | Manual | FailedJobRegistry | Built-in DLQ | Dead-Letter Queue (DLQ) |
| **Best Used For** | Production Python microservices & backends | Lightweight pure async Python apps | Simple Python scripting | Node.js / TypeScript ecosystems | Serverless AWS Lambda architectures |

---

## 10. The JOBS LAB: 8 Hands-on Exercises

Run these exercises locally to verify and observe production queue mechanics firsthand.

### Exercise 1: Run Worker with Debug Logs & Place an Order
**Goal**: Observe JSON task serialization, `task_start`, and duration logging.
```bash
# Terminal 1: Run worker with debug logs
celery -A app.worker.celery_app worker -l debug -Q default,emails,maintenance -c 2

# Terminal 2: Place an order via API or test script
curl -X POST http://localhost:4000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"arjun@beanbox.in","password":"Coffee@1234"}'
```
**Expected Output in Worker Logs**:
```text
[INFO] beanbox.worker: task_start task_id=8fa21e task=app.worker.tasks_email.send_email_task attempt=1 req_id=req_c09
[INFO] [BeanBox Mock Email] -> To: arjun@beanbox.in | Subject: Welcome to BeanBox
[INFO] beanbox.worker: task_success task_id=8fa21e task=app.worker.tasks_email.send_email_task attempt=1 duration=0.003s req_id=req_c09
```

---

### Exercise 2: Kill Worker Mid-Task & Watch Redelivery
**Goal**: Verify `task_acks_late=True` and `task_reject_on_worker_lost=True`.
```bash
# 1. Enqueue a task
python -c "from app.worker.tasks_email import send_email_task; send_email_task.apply_async(kwargs={'kind':'welcome','payload_ids':{'user_id':'22222222-2222-4222-8222-222222222222'}}, queue='emails')"

# 2. Kill the Celery child worker process with SIGKILL while it is running:
pkill -9 -f "celery.*worker"
```
**Expected Result**:
The supervisor or next worker startup detects unacknowledged messages and re-executes the task without losing data.

---

### Exercise 3: Stop Redis & Place an Order (Inline Fallback)
**Goal**: Verify that checkout and signup never fail when Redis is down.
```bash
# 1. Stop Redis temporarily
brew services stop redis  # (or docker stop redis)

# 2. Place an order or trigger an email enqueue
python -c "from app.worker.tasks_email import enqueue_email; from app.services.email_service import ConsoleEmailService; enqueue_email('welcome', {'user_id':'22222222-2222-4222-8222-222222222222'}, email_service=ConsoleEmailService())"

# 3. Restart Redis
brew services start redis
```
**Expected Output**:
```text
[WARNING] Broker unavailable when enqueuing email task (welcome); executing inline fallback: Connection refused.
[BeanBox Mock Email] -> To: arjun@beanbox.in | Subject: Welcome to BeanBox
```
The email is delivered inline; the customer request completes successfully.

---

### Exercise 4: Force a Task to Fail & Watch Dead Letters
**Goal**: Watch exponential retries exhaust and write to the `failed_jobs` table.
```bash
# Trigger an invalid task that will raise ValueError 5 times
python -c "from app.worker.tasks_email import send_email_task; send_email_task.apply_async(kwargs={'kind':'invalid_kind','payload_ids':{}}, queue='emails')"
```
**Expected Result**:
1. Worker retries 5 times with increasing backoff.
2. `TrackedTask.on_failure` executes.
3. Row created in `failed_jobs` table.
4. Open `http://localhost:3000/admin/jobs` — the failed task appears in the **Failed Jobs (Dead Letters)** table with stack trace and "Retry Task" button.

---

### Exercise 5: Place an Order & Watch Automatic Expiry
**Goal**: Verify `expire_unpaid_orders` cancels unpaid orders and returns reserved stock.
```bash
# 1. Create a dummy pending order from 35 minutes ago
python -c "from tests.conftest import create_test_app; from tests.test_celery_jobs import _make_dummy_order; app = create_test_app(); _make_dummy_order(app, '22222222-2222-4222-8222-222222222222', minutes_ago=35)"

# 2. Run expiry job
python -c "from app.worker.tasks_orders import expire_unpaid_orders; print(expire_unpaid_orders())"
```
**Expected Output**:
```text
{'status': 'success', 'scanned': 1, 'expired': 1, 'skipped': 0}
```
Order status transitions to `cancelled`, `cancel_reason='payment_timeout'`, and stock is returned to inventory.

---

### Exercise 6: Start Two Beat Instances & Verify Distributed Lock
**Goal**: Confirm that overlapping periodic tasks are blocked by Redis lock.
```bash
# Terminal 1:
celery -A app.worker.celery_app beat -l info

# Terminal 2:
celery -A app.worker.celery_app beat -l info
```
**Expected Result**:
Both instances push ticks, but only the worker that first acquires `beanbox:locks:expire_unpaid_orders` executes the job. The other logs:
```text
[WARNING] Another instance of expire_unpaid_orders is currently running; skipping.
```

---

### Exercise 7: Enqueue 100 Emails & Watch Concurrency
**Goal**: Observe 2 worker processes drain a high-concurrency batch.
```bash
python -c "
from app.worker.celery_app import celery_app
for i in range(100):
    celery_app.send_task('app.worker.tasks_email.send_email_task', kwargs={'kind':'welcome','payload_ids':{'user_id':'22222222-2222-4222-8222-222222222222'}}, queue='emails')
"
```
**Expected Result**:
Worker processes tasks concurrently without socket leaks or packet corruption.

---

### Exercise 8: Inspect Queue Telemetry via Redis CLI
**Goal**: Directly inspect the broker data structures on DB 1.
```bash
# Check length of emails queue
redis-cli -n 1 LLEN emails

# Peek at the raw JSON Kombu message payload
redis-cli -n 1 LRANGE emails 0 0

# Check active Redis locks on DB 0
redis-cli -n 0 KEYS "beanbox:locks:*"
```
**Expected Output**:
Valid JSON string containing Celery message metadata: `task`, `id`, `argsrepr`, `retries`.

---

## 11. What Scaled Production Systems Add Beyond This

While our Celery + Redis architecture is production-ready for thousands of orders per day, enterprise platforms add several architectural extensions:

1. **Transactional Outbox Pattern**:
   Instead of calling `enqueue_email()` in the same request as `db.commit()`, the API writes the job payload to an `outbox` table in the *same PostgreSQL database transaction*. A separate CDC (Change Data Capture) process or Debezium tailer pushes from PostgreSQL WAL to Redis/Kafka, guaranteeing 100% zero dual-write inconsistency even if Redis crashes mid-request.

2. **Temporal / Cadence (Orchestration & Sagas)**:
   For long-running, multi-step business workflows (e.g. order -> payment -> roaster assignment -> shipping label -> 7-day delivery check), tools like Temporal represent workflows as durable async code where local variables survive process restarts.

3. **Apache Kafka / AWS SQS for High-Throughput Streams**:
   For event ingestion (e.g. user clickstreams, analytics, IoT sensor streams), Kafka provides persistent partition-ordered logs consumed by consumer groups.

4. **Priority Queues**:
   Splitting workers into dedicated pools:
   - High-priority (`checkout_confirmations`, `password_resets`)
   - Normal (`welcome_emails`, `inventory_sync`)
   - Low-priority / Batch (`marketing_newsletters`, `data_exports`)

5. **Rate-Limited Tasks**:
   Enforcing per-destination limits (e.g. Gmail rate limits of 10 emails/sec) using Celery's `rate_limit='10/s'` or token bucket algorithms in Redis.

6. **Celery Canvas Workflows**:
   - Chains: `(step1.s() | step2.s() | step3.s())()` (sequential pipeline)
   - Groups: `group(send_email.s(u) for u in users)()` (parallel map)
   - Chords: `chord(group(tasks))(combine_results.s())` (parallel map with barrier callback)
