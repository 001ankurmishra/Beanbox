-- BeanBox Refresh Token Grace Window Migration (003)
-- Adds a short grace window for the immediately previous refresh token so
-- concurrent tab refreshes do not falsely trigger reuse detection.

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS grace_refresh_hash TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS grace_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_sessions_grace_hash
  ON sessions (grace_refresh_hash)
  WHERE grace_refresh_hash IS NOT NULL;
