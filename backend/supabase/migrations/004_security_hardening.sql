-- BeanBox Security Hardening Migration (004)
-- Applies variant soft-inactivation support, distributed 2FA challenge JTI replay
-- protection, and bounded refresh-grace consumption.

ALTER TABLE product_variants
  ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS grace_uses_remaining INTEGER NOT NULL DEFAULT 3 CHECK (grace_uses_remaining >= 0);

CREATE TABLE IF NOT EXISTS consumed_challenges (
  jti TEXT PRIMARY KEY,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_consumed_challenges_expires
  ON consumed_challenges (expires_at);

ALTER TABLE consumed_challenges ENABLE ROW LEVEL SECURITY;
