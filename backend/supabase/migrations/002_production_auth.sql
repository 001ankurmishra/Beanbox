-- BeanBox Production-Grade Auth Migration (002)
-- Run this in Supabase SQL Editor. Idempotent and safe on existing BeanBox tables.
-- Implements: sessions, email_verification_tokens, oauth_accounts, totp_secrets,
-- recovery_codes, login_attempts, audit_logs + FK indexes + strict RLS.

-- 1. Extend users table
ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT false;

-- Pre-mark seeded demo accounts as email-verified so existing store flows work immediately
UPDATE users
SET email_verified = true,
    email_verified_at = COALESCE(email_verified_at, now())
WHERE email IN ('admin@beanbox.in', 'arjun@beanbox.in')
  AND email_verified = false;

-- 2. Sessions (Rotating Refresh Tokens + Family Reuse Detection)
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_hash TEXT NOT NULL UNIQUE,
  previous_refresh_hashes TEXT[] NOT NULL DEFAULT '{}',
  family_id TEXT NOT NULL,
  user_agent TEXT NOT NULL,
  ip TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_family_id ON sessions (family_id);
CREATE INDEX IF NOT EXISTS idx_sessions_active_user ON sessions (user_id, last_used_at DESC)
  WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_sessions_prev_hashes ON sessions USING GIN (previous_refresh_hashes);

-- 3. Email Verification Tokens (Single-use hashed tokens, 24h TTL)
CREATE TABLE IF NOT EXISTS email_verification_tokens (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_user_created
  ON email_verification_tokens (user_id, created_at DESC);

-- 4. OAuth Accounts (Google OAuth 2.0 + PKCE)
CREATE TABLE IF NOT EXISTS oauth_accounts (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK (provider IN ('google')),
  provider_user_id TEXT NOT NULL,
  provider_email TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_user_id)
);
CREATE INDEX IF NOT EXISTS idx_oauth_accounts_user_id ON oauth_accounts (user_id);

-- 5. TOTP Secrets (AES-256-GCM encrypted secret at rest)
CREATE TABLE IF NOT EXISTS totp_secrets (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  encrypted_secret TEXT NOT NULL,
  is_enabled BOOLEAN NOT NULL DEFAULT false,
  last_used_timestep BIGINT,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 6. Recovery Codes (HMAC-SHA256 hashed single-use 2FA backup codes)
CREATE TABLE IF NOT EXISTS recovery_codes (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash TEXT NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, code_hash)
);
CREATE INDEX IF NOT EXISTS idx_recovery_codes_user_unused
  ON recovery_codes (user_id) WHERE used_at IS NULL;

-- 7. Login Attempts (Per-account, per-IP, per-2FA brute-force lockout counters)
CREATE TABLE IF NOT EXISTS login_attempts (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  key TEXT NOT NULL UNIQUE,
  key_type TEXT NOT NULL CHECK (key_type IN ('account', 'ip', '2fa')),
  failed_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
  lockout_level INTEGER NOT NULL DEFAULT 0 CHECK (lockout_level >= 0),
  first_failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  locked_until TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_locked
  ON login_attempts (locked_until) WHERE locked_until IS NOT NULL;

-- 8. Security Audit Logs (Append-only event log; never stores tokens/passwords/secrets)
CREATE TABLE IF NOT EXISTS audit_logs (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure', 'warning')),
  target_id TEXT,
  ip TEXT NOT NULL,
  user_agent TEXT NOT NULL,
  request_id TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_created ON audit_logs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_event_created ON audit_logs (event_type, created_at DESC);

-- 9. Strict Row-Level Security (RLS): deny all direct anon/authenticated Data API access.
-- All mutations and reads execute exclusively through FastAPI's direct server connection.
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_verification_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE totp_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE recovery_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE login_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
