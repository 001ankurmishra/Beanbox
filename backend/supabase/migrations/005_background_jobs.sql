-- BeanBox Background Jobs & Order Expiry Migration (005)
-- 1. Adds orders.cancel_reason (text, nullable).
-- 2. Adds partial index on orders(created_at) WHERE status = 'pending' for O(log N) expiry scans.
-- 3. Adds failed_jobs table for Celery dead-letter storage with IDs-only telemetry.

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS cancel_reason TEXT;

-- Partial index for order TTL expiry:
-- Pending orders represent < 1% of the total orders table in a healthy roastery.
-- A partial index indexes ONLY active pending orders, keeping the index small enough
-- to fit entirely within PostgreSQL buffer cache (RAM). The query:
--   SELECT * FROM orders WHERE status = 'pending' AND created_at < cutoff ORDER BY created_at ASC LIMIT 100
-- uses this index directly without scanning historical paid/shipped/cancelled rows.
CREATE INDEX IF NOT EXISTS idx_orders_pending_created
  ON orders (created_at ASC)
  WHERE status = 'pending';

-- Dead letter storage for exhausted task retries:
-- Stores task name, args (IDs only, never PII/tokens), error message, and truncated traceback (<=4KB).
CREATE TABLE IF NOT EXISTS failed_jobs (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  task_name TEXT NOT NULL,
  args_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  error_message TEXT NOT NULL,
  traceback TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 1,
  queue TEXT NOT NULL DEFAULT 'default',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_failed_jobs_created_at
  ON failed_jobs (created_at DESC);

ALTER TABLE failed_jobs ENABLE ROW LEVEL SECURITY;
