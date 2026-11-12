'use client';

import React, { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  CheckCircle2,
  Copy,
  KeyRound,
  Laptop,
  Lock,
  LogOut,
  ShieldAlert,
  ShieldCheck,
  Smartphone
} from 'lucide-react';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { authApi } from '@/lib/api/endpoints';
import { formatDateIN } from '@/lib/format';
import {
  TwoFactorSetupResponse,
  TwoFactorStatusResponse,
  UserSession
} from '@/types/api';

function summarizeDevice(ua: string): { label: string; isMobile: boolean } {
  const lower = ua.toLowerCase();
  const isMobile = /iphone|android|mobile|ipad/.test(lower);
  let browser = 'Browser / Client';
  if (lower.includes('edg/')) browser = 'Microsoft Edge';
  else if (lower.includes('chrome/')) browser = 'Google Chrome';
  else if (lower.includes('firefox/')) browser = 'Mozilla Firefox';
  else if (lower.includes('safari/') && !lower.includes('chrome')) browser = 'Apple Safari';

  let os = '';
  if (lower.includes('mac os') || lower.includes('macintosh')) os = 'macOS';
  else if (lower.includes('windows')) os = 'Windows';
  else if (lower.includes('iphone')) os = 'iPhone';
  else if (lower.includes('android')) os = 'Android';
  else if (lower.includes('linux')) os = 'Linux';

  return {
    label: os ? `${browser} on ${os}` : browser,
    isMobile
  };
}

function SecuritySettingsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const enforce2fa = searchParams.get('enforce2fa') === '1';

  const { user, refreshUser, logoutAll } = useAuth();
  const { showToast } = useToast();

  // Sessions state
  const [sessions, setSessions] = useState<UserSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [confirmLogoutAllOpen, setConfirmLogoutAllOpen] = useState(false);
  const [loggingOutAll, setLoggingOutAll] = useState(false);

  // Change password state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [pwSaving, setPwSaving] = useState(false);
  const [pwError, setPwError] = useState('');

  // 2FA state
  const [twoFaStatus, setTwoFaStatus] = useState<TwoFactorStatusResponse | null>(
    null
  );
  const [setupData, setSetupData] = useState<TwoFactorSetupResponse | null>(null);
  const [totpVerifyCode, setTotpVerifyCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [disableCode, setDisableCode] = useState('');
  const [disablePassword, setDisablePassword] = useState('');
  const [regenCode, setRegenCode] = useState('');
  const [twoFaBusy, setTwoFaBusy] = useState(false);
  const [twoFaError, setTwoFaError] = useState('');

  const loadSecurityState = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const [sessRes, statusRes] = await Promise.all([
        authApi.sessions(),
        authApi.twoFactorStatus()
      ]);
      setSessions(sessRes.items);
      setTwoFaStatus(statusRes);
    } catch {
      // Handled gracefully
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    if (user) {
      loadSecurityState();
    }
  }, [user, loadSecurityState]);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwError('');
    setPwSaving(true);
    try {
      const res = await authApi.changePassword({ currentPassword, newPassword });
      setCurrentPassword('');
      setNewPassword('');
      showToast(res.message, 'success');
      await loadSecurityState();
    } catch (err) {
      setPwError(
        err instanceof ApiClientError
          ? err.message
          : 'Could not update password'
      );
    } finally {
      setPwSaving(false);
    }
  };

  const handleRevokeSession = async (sessionId: string) => {
    setRevokingId(sessionId);
    try {
      await authApi.revokeSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      showToast('Device session logged out', 'info');
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Failed to revoke session',
        'error'
      );
    } finally {
      setRevokingId(null);
    }
  };

  const handleConfirmLogoutAll = async () => {
    setLoggingOutAll(true);
    try {
      await logoutAll();
      showToast('Logged out of all devices', 'info');
      router.push('/login');
    } catch (err) {
      showToast(
        err instanceof ApiClientError
          ? err.message
          : 'Could not log out all devices',
        'error'
      );
      setLoggingOutAll(false);
      setConfirmLogoutAllOpen(false);
    }
  };

  const handleStart2faSetup = async () => {
    setTwoFaError('');
    setTwoFaBusy(true);
    try {
      const data = await authApi.setup2fa();
      setSetupData(data);
      setRecoveryCodes(null);
    } catch (err) {
      setTwoFaError(
        err instanceof ApiClientError ? err.message : 'Could not initiate 2FA'
      );
    } finally {
      setTwoFaBusy(false);
    }
  };

  const handleEnable2fa = async (e: React.FormEvent) => {
    e.preventDefault();
    setTwoFaError('');
    setTwoFaBusy(true);
    try {
      const res = await authApi.enable2fa(totpVerifyCode.trim());
      setRecoveryCodes(res.recoveryCodes);
      setSetupData(null);
      setTotpVerifyCode('');
      await refreshUser();
      await loadSecurityState();
      showToast('Two-factor authentication is now enabled!', 'success');
    } catch (err) {
      setTwoFaError(
        err instanceof ApiClientError ? err.message : 'Invalid verification code'
      );
    } finally {
      setTwoFaBusy(false);
    }
  };

  const handleDisable2fa = async (e: React.FormEvent) => {
    e.preventDefault();
    setTwoFaError('');
    setTwoFaBusy(true);
    try {
      await authApi.disable2fa({
        code: disableCode.trim(),
        password: disablePassword || undefined
      });
      setDisableCode('');
      setDisablePassword('');
      setRecoveryCodes(null);
      await refreshUser();
      await loadSecurityState();
      showToast('Two-factor authentication disabled', 'info');
    } catch (err) {
      setTwoFaError(
        err instanceof ApiClientError ? err.message : 'Failed to disable 2FA'
      );
    } finally {
      setTwoFaBusy(false);
    }
  };

  const handleRegenerateCodes = async (e: React.FormEvent) => {
    e.preventDefault();
    setTwoFaError('');
    setTwoFaBusy(true);
    try {
      const res = await authApi.regenerateRecoveryCodes(regenCode.trim());
      setRecoveryCodes(res.recoveryCodes);
      setRegenCode('');
      await loadSecurityState();
      showToast('Generated 10 fresh backup recovery codes', 'success');
    } catch (err) {
      setTwoFaError(
        err instanceof ApiClientError ? err.message : 'Invalid authenticator code'
      );
    } finally {
      setTwoFaBusy(false);
    }
  };

  const copyText = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showToast(`${label} copied to clipboard`, 'success');
    } catch {
      showToast('Copy failed — please select and copy manually', 'error');
    }
  };

  const adminNeedsSetup = user?.role === 'admin' && !user.totpEnabled;

  return (
    <div className="space-y-8">
      {(enforce2fa || adminNeedsSetup) && user?.role === 'admin' && (
        <div
          role="alert"
          className="rounded-2xl border border-rose-300 bg-rose-50 p-5 text-rose-950"
        >
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-rose-700" aria-hidden="true" />
            <div>
              <h2 className="font-serif text-lg font-bold">
                Administrator Two-Factor Authentication Required
              </h2>
              <p className="mt-1 text-sm text-rose-800">
                {user.totpEnabled
                  ? '2FA is now active on your administrator account.'
                  : 'For roastery security, admin accounts must enable TOTP two-factor authentication before accessing the Admin Console.'}
              </p>
              {user.totpEnabled && (
                <Link
                  href="/admin"
                  className="mt-3 inline-flex min-h-[40px] items-center rounded-xl bg-espresso-900 px-4 text-xs font-semibold text-white hover:bg-caramel"
                >
                  Continue to Admin Console →
                </Link>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        {/* Left column: Two-Factor Authentication */}
        <section
          aria-labelledby="twofa-heading"
          className="lg:col-span-6 rounded-2xl border border-espresso-200 bg-white p-6 space-y-5"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <ShieldCheck className="h-5 w-5 text-caramel" aria-hidden="true" />
              <h2
                id="twofa-heading"
                className="font-serif text-xl font-bold text-espresso-900"
              >
                Two-Factor Authentication (2FA)
              </h2>
            </div>
            <span
              className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                user?.totpEnabled
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                  : 'border-espresso-200 bg-espresso-50 text-espresso-700'
              }`}
            >
              {user?.totpEnabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>

          <p className="text-xs text-espresso-600 leading-relaxed">
            Protect your BeanBox account with time-based one-time passwords (TOTP)
            using Google Authenticator, 1Password, Authy, or Apple Passwords.
          </p>

          {twoFaError && (
            <div
              role="alert"
              className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs font-medium text-rose-800"
            >
              {twoFaError}
            </div>
          )}

          {recoveryCodes && (
            <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-bold text-amber-950">
                  Save Your 10 Backup Recovery Codes
                </h3>
                <button
                  type="button"
                  onClick={() => copyText(recoveryCodes.join('\n'), 'Recovery codes')}
                  className="inline-flex items-center gap-1 rounded-lg border border-amber-400 bg-white px-2.5 py-1 text-xs font-semibold text-amber-950 hover:bg-amber-100"
                >
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  Copy all
                </button>
              </div>
              <p className="text-xs text-amber-900">
                Store these single-use codes safely. For security, they cannot be viewed
                again once you leave this page.
              </p>
              <div className="grid grid-cols-2 gap-2 font-mono text-xs">
                {recoveryCodes.map((code) => (
                  <div
                    key={code}
                    className="rounded-lg border border-amber-200 bg-white px-2.5 py-1.5 text-center font-semibold text-espresso-900"
                  >
                    {code}
                  </div>
                ))}
              </div>
              {user?.role === 'admin' && (
                <Link
                  href="/admin"
                  className="inline-flex min-h-[40px] items-center rounded-xl bg-espresso-900 px-4 text-xs font-semibold text-white hover:bg-caramel"
                >
                  Open Roastery Admin Console →
                </Link>
              )}
            </div>
          )}

          {!user?.totpEnabled ? (
            !setupData ? (
              <button
                type="button"
                disabled={twoFaBusy}
                onClick={handleStart2faSetup}
                className="inline-flex min-h-[44px] items-center gap-2 rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white hover:bg-caramel transition disabled:opacity-50"
              >
                <KeyRound className="h-4 w-4" aria-hidden="true" />
                {twoFaBusy ? 'Preparing Setup…' : 'Set Up Authenticator 2FA'}
              </button>
            ) : (
              <div className="space-y-4 rounded-2xl border border-espresso-200 bg-espresso-50 p-4">
                <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
                  <div className="shrink-0 rounded-2xl border border-espresso-200 bg-white p-2.5">
                    {/* Generated local SVG data URI QR code */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={setupData.qrDataUrl}
                      alt="Scan this QR code with your authenticator app"
                      className="h-36 w-36"
                    />
                  </div>
                  <div className="min-w-0 flex-1 space-y-2">
                    <div className="text-xs font-semibold text-espresso-800">
                      1. Scan QR code or enter secret manually:
                    </div>
                    <div className="flex items-center gap-2">
                      <code className="block truncate rounded-lg border border-espresso-200 bg-white px-2.5 py-1.5 text-xs font-mono text-espresso-900">
                        {setupData.secret}
                      </code>
                      <button
                        type="button"
                        onClick={() => copyText(setupData.secret, 'Authenticator secret')}
                        aria-label="Copy manual secret key"
                        className="rounded-lg border border-espresso-300 bg-white p-2 text-espresso-700 hover:bg-espresso-100"
                      >
                        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    </div>
                    <p className="text-[11px] text-espresso-600">
                      Your secret is encrypted with AES-256-GCM before storage.
                    </p>
                  </div>
                </div>

                <form onSubmit={handleEnable2fa} className="space-y-3 border-t border-espresso-200 pt-4">
                  <div>
                    <label
                      htmlFor="enable-totp-code"
                      className="block text-xs font-semibold text-espresso-800"
                    >
                      2. Enter 6-Digit Code from Authenticator <span aria-hidden="true">*</span>
                    </label>
                    <input
                      id="enable-totp-code"
                      name="otp"
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      pattern="\d{6}"
                      maxLength={6}
                      required
                      placeholder="123456"
                      value={totpVerifyCode}
                      onChange={(e) => setTotpVerifyCode(e.target.value)}
                      className="auth-field mt-1 h-11 w-full rounded-xl border border-espresso-200 bg-white px-3.5 font-mono text-base tracking-[0.25em]"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="submit"
                      disabled={twoFaBusy}
                      className="min-h-[44px] rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white hover:bg-caramel disabled:opacity-50"
                    >
                      {twoFaBusy ? 'Verifying…' : 'Verify & Enable 2FA'}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setSetupData(null);
                        setTotpVerifyCode('');
                      }}
                      className="min-h-[44px] rounded-xl border border-espresso-300 bg-white px-4 text-sm font-medium text-espresso-700 hover:bg-espresso-100"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            )
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-xs text-emerald-950">
                <span className="flex items-center gap-2 font-medium">
                  <CheckCircle2 className="h-4 w-4 text-emerald-700" aria-hidden="true" />
                  Authenticator 2FA active
                </span>
                <span>
                  Backup codes remaining:{' '}
                  <strong>{twoFaStatus?.recoveryCodesRemaining ?? 0}</strong>
                </span>
              </div>

              {/* Regenerate recovery codes */}
              <form
                onSubmit={handleRegenerateCodes}
                className="rounded-xl border border-espresso-200 p-4 space-y-2.5"
              >
                <div className="text-xs font-semibold text-espresso-900">
                  Regenerate Backup Recovery Codes
                </div>
                <div className="flex flex-wrap gap-2">
                  <label htmlFor="regen-code" className="sr-only">
                    Current 6-digit authenticator code
                  </label>
                  <input
                    id="regen-code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="\d{6}"
                    maxLength={6}
                    required
                    placeholder="Current 6-digit code"
                    value={regenCode}
                    onChange={(e) => setRegenCode(e.target.value)}
                    className="auth-field h-10 flex-1 rounded-xl border border-espresso-200 px-3 font-mono text-sm"
                  />
                  <button
                    type="submit"
                    disabled={twoFaBusy}
                    className="min-h-[40px] rounded-xl border border-espresso-300 bg-white px-4 text-xs font-semibold text-espresso-900 hover:bg-espresso-100 disabled:opacity-50"
                  >
                    Regenerate 10 Codes
                  </button>
                </div>
              </form>

              {user.role === 'admin' ? (
                <p className="rounded-xl border border-espresso-200 bg-espresso-50 px-3.5 py-2.5 text-xs text-espresso-700">
                  Two-factor authentication is mandatory for <strong>admin</strong> accounts and cannot be disabled.
                </p>
              ) : (
                <form
                  onSubmit={handleDisable2fa}
                  className="rounded-xl border border-rose-200 bg-rose-50/40 p-4 space-y-3"
                >
                  <div className="text-xs font-semibold text-rose-900">
                    Disable Two-Factor Authentication
                  </div>
                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                    <div>
                      <label htmlFor="disable-pw" className="block text-[11px] font-medium text-espresso-700">
                        Account Password (if set)
                      </label>
                      <input
                        id="disable-pw"
                        type="password"
                        autoComplete="current-password"
                        value={disablePassword}
                        onChange={(e) => setDisablePassword(e.target.value)}
                        className="auth-field mt-1 h-10 w-full rounded-xl border border-espresso-200 bg-white px-3 text-sm"
                      />
                    </div>
                    <div>
                      <label htmlFor="disable-code" className="block text-[11px] font-medium text-espresso-700">
                        6-Digit or Recovery Code *
                      </label>
                      <input
                        id="disable-code"
                        type="text"
                        required
                        value={disableCode}
                        onChange={(e) => setDisableCode(e.target.value)}
                        placeholder="123456 or XXXX-XXXX"
                        className="auth-field mt-1 h-10 w-full rounded-xl border border-espresso-200 bg-white px-3 font-mono text-sm"
                      />
                    </div>
                  </div>
                  <button
                    type="submit"
                    disabled={twoFaBusy}
                    className="min-h-[40px] rounded-xl bg-rose-700 px-4 text-xs font-semibold text-white hover:bg-rose-800 disabled:opacity-50"
                  >
                    Disable 2FA
                  </button>
                </form>
              )}
            </div>
          )}
        </section>

        {/* Right column: Change Password */}
        <section
          aria-labelledby="change-pw-heading"
          className="lg:col-span-6 rounded-2xl border border-espresso-200 bg-white p-6 space-y-4"
        >
          <div className="flex items-center gap-2.5">
            <Lock className="h-5 w-5 text-caramel" aria-hidden="true" />
            <h2
              id="change-pw-heading"
              className="font-serif text-xl font-bold text-espresso-900"
            >
              Change Password
            </h2>
          </div>
          <p className="text-xs text-espresso-600">
            Updating your password rehashes with Argon2id and immediately signs out
            all other devices.
          </p>

          {pwError && (
            <div
              role="alert"
              className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs font-medium text-rose-800"
            >
              {pwError}
            </div>
          )}

          <form onSubmit={handleChangePassword} className="space-y-4">
            <div>
              <label
                htmlFor="curr-pw"
                className="block text-xs font-semibold text-espresso-800"
              >
                Current Password <span aria-hidden="true">*</span>
              </label>
              <input
                id="curr-pw"
                name="currentPassword"
                type="password"
                required
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="auth-field mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3.5 text-base"
              />
            </div>

            <div>
              <label
                htmlFor="next-pw"
                className="block text-xs font-semibold text-espresso-800"
              >
                New Password <span aria-hidden="true">*</span>
              </label>
              <p id="next-pw-hint" className="mt-0.5 text-xs text-espresso-500">
                Minimum 10 characters, avoid common passwords, and do not include your email.
              </p>
              <input
                id="next-pw"
                name="newPassword"
                type="password"
                required
                minLength={10}
                autoComplete="new-password"
                aria-describedby="next-pw-hint"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="auth-field mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3.5 text-base"
              />
            </div>

            <button
              type="submit"
              disabled={pwSaving}
              className="min-h-[44px] rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white hover:bg-caramel transition disabled:opacity-50"
            >
              {pwSaving ? 'Updating Password…' : 'Update Password'}
            </button>
          </form>
        </section>
      </div>

      {/* Active Sessions */}
      <section
        aria-labelledby="sessions-heading"
        className="rounded-2xl border border-espresso-200 bg-white p-6"
      >
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-espresso-100 pb-4">
          <div>
            <h2
              id="sessions-heading"
              className="font-serif text-xl font-bold text-espresso-900"
            >
              Active Sessions &amp; Devices
            </h2>
            <p className="text-xs text-espresso-600">
              Review signed-in devices and revoke any unfamiliar session immediately.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setConfirmLogoutAllOpen(true)}
            className="inline-flex min-h-[40px] items-center gap-2 rounded-xl border border-rose-300 bg-rose-50 px-4 text-xs font-semibold text-rose-800 hover:bg-rose-100"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Log Out All Devices
          </button>
        </div>

        {loadingSessions ? (
          <div className="mt-4 h-28 animate-pulse rounded-xl bg-espresso-50" />
        ) : sessions.length === 0 ? (
          <p className="mt-4 text-sm text-espresso-600">No active sessions found.</p>
        ) : (
          <ul className="mt-4 divide-y divide-espresso-100">
            {sessions.map((sess) => {
              const { label, isMobile } = summarizeDevice(sess.userAgent);
              const Icon = isMobile ? Smartphone : Laptop;
              return (
                <li
                  key={sess.id}
                  className="flex flex-wrap items-center justify-between gap-4 py-3.5"
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-espresso-100 text-espresso-700">
                      <Icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-sm text-espresso-900">
                          {label}
                        </span>
                        {sess.isCurrent && (
                          <span className="rounded-full bg-sage-light border border-sage/30 px-2 py-0.5 text-[11px] font-semibold text-sage">
                            This device
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 text-xs text-espresso-600">
                        IP: <span className="font-mono">{sess.ip}</span> · Last active:{' '}
                        {formatDateIN(sess.lastUsedAt)} · Expires:{' '}
                        {formatDateIN(sess.expiresAt)}
                      </div>
                    </div>
                  </div>

                  {!sess.isCurrent && (
                    <button
                      type="button"
                      disabled={revokingId === sess.id}
                      onClick={() => handleRevokeSession(sess.id)}
                      className="min-h-[38px] rounded-xl border border-espresso-300 bg-white px-3.5 text-xs font-semibold text-espresso-800 hover:bg-rose-50 hover:border-rose-300 hover:text-rose-800 disabled:opacity-50"
                    >
                      {revokingId === sess.id ? 'Revoking…' : 'Log out'}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <ConfirmDialog
        open={confirmLogoutAllOpen}
        title="Log out from all devices?"
        description="This immediately revokes every active session and refresh token across all browsers and phones, including this device."
        confirmLabel="Log Out All Devices"
        isBusy={loggingOutAll}
        onConfirm={handleConfirmLogoutAll}
        onCancel={() => setConfirmLogoutAllOpen(false)}
      />
    </div>
  );
}

export default function AccountSecurityPage() {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-3xl bg-white" />}>
      <SecuritySettingsContent />
    </Suspense>
  );
}
