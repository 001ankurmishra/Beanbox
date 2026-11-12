'use client';

import React, { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Coffee, Eye, EyeOff, KeyRound, ShieldCheck } from 'lucide-react';
import { GoogleSignInButton } from '@/components/auth/GoogleSignInButton';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { User } from '@/types/api';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = searchParams.get('next') || '/';
  const oauthError = searchParams.get('error');
  const { login, verify2faLogin } = useAuth();
  const { showToast } = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Step 2: Two-factor authentication state
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [twoFaCode, setTwoFaCode] = useState('');
  const [useRecoveryMode, setUseRecoveryMode] = useState(false);

  useEffect(() => {
    if (oauthError === 'oauth_denied') {
      setErrorMsg('Google sign-in was cancelled.');
    }
    if (typeof window !== 'undefined' && window.location.hash.startsWith('#challenge=')) {
      const tok = window.location.hash.slice('#challenge='.length).trim();
      if (tok) {
        setChallengeToken(tok);
        window.history.replaceState(
          null,
          '',
          `${window.location.pathname}${window.location.search}`
        );
      }
    }
  }, [oauthError]);

  const navigateAfterLogin = (loggedInUser: User) => {
    if (loggedInUser.role === 'admin' && !loggedInUser.totpEnabled) {
      showToast(
        'Administrator accounts require 2FA setup before accessing the console.',
        'info'
      );
      router.push('/account/security?enforce2fa=1');
      return;
    }
    showToast(`Welcome back, ${loggedInUser.name.split(' ')[0]}!`, 'success');
    router.push(nextPath);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    setSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.requiresTwoFactor) {
        setChallengeToken(result.challengeToken);
        setTwoFaCode('');
        setSubmitting(false);
        return;
      }
      navigateAfterLogin(result.user);
    } catch (err) {
      const msg =
        err instanceof ApiClientError ? err.message : 'Could not sign in';
      setErrorMsg(msg);
      setSubmitting(false);
    }
  };

  const handleVerify2fa = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!challengeToken) return;
    setErrorMsg('');
    setSubmitting(true);
    try {
      const user = await verify2faLogin(challengeToken, twoFaCode.trim());
      navigateAfterLogin(user);
    } catch (err) {
      const msg =
        err instanceof ApiClientError ? err.message : 'Invalid verification code';
      setErrorMsg(msg);
      setSubmitting(false);
    }
  };

  if (challengeToken) {
    return (
      <div className="mx-auto max-w-md px-4 py-14">
        <div className="rounded-3xl border border-espresso-200 bg-white p-7 shadow-warm">
          <div className="flex items-center gap-2.5 text-espresso-900">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-espresso-900 text-caramel-light">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h1 className="font-serif text-2xl font-bold">
                Two-Factor Verification
              </h1>
              <p className="text-xs text-espresso-600">
                Step 2 of 2 — verify your identity to finish signing in.
              </p>
            </div>
          </div>

          {errorMsg && (
            <div
              role="alert"
              className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs font-medium text-rose-800"
            >
              {errorMsg}
            </div>
          )}

          <form onSubmit={handleVerify2fa} className="mt-6 space-y-4">
            <div>
              <label
                htmlFor="twofa-code"
                className="block text-xs font-semibold text-espresso-800"
              >
                {useRecoveryMode
                  ? 'Backup Recovery Code *'
                  : '6-Digit Authenticator Code *'}
              </label>
              <p id="twofa-hint" className="mt-0.5 text-xs text-espresso-500">
                {useRecoveryMode
                  ? 'Enter one of your single-use 8-character recovery codes (e.g. A1B2-C3D4).'
                  : 'Open your authenticator app and enter the current 6-digit code.'}
              </p>
              <input
                id="twofa-code"
                name="otp"
                type="text"
                inputMode={useRecoveryMode ? 'text' : 'numeric'}
                autoComplete={useRecoveryMode ? 'off' : 'one-time-code'}
                pattern={useRecoveryMode ? undefined : '\\d{6}'}
                maxLength={useRecoveryMode ? 16 : 6}
                aria-describedby="twofa-hint"
                autoFocus
                required
                placeholder={useRecoveryMode ? 'XXXX-XXXX' : '123456'}
                value={twoFaCode}
                onChange={(e) => setTwoFaCode(e.target.value)}
                className="auth-field mt-1.5 h-12 w-full rounded-xl border border-espresso-200 px-3.5 font-mono text-lg tracking-[0.25em] text-espresso-900"
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="min-h-[48px] w-full rounded-xl bg-espresso-900 px-4 text-sm font-semibold text-white hover:bg-caramel transition disabled:opacity-50"
            >
              {submitting ? 'Verifying…' : 'Verify & Sign In'}
            </button>
          </form>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-2 text-xs">
            <button
              type="button"
              onClick={() => {
                setUseRecoveryMode((m) => !m);
                setTwoFaCode('');
                setErrorMsg('');
              }}
              className="inline-flex items-center gap-1 font-semibold text-caramel-dark hover:underline"
            >
              <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
              {useRecoveryMode
                ? 'Use authenticator code instead'
                : 'Use a backup recovery code'}
            </button>

            <button
              type="button"
              onClick={() => {
                setChallengeToken(null);
                setTwoFaCode('');
                setErrorMsg('');
              }}
              className="font-medium text-espresso-600 hover:underline"
            >
              Back to password
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md px-4 py-14">
      <div className="rounded-3xl border border-espresso-200 bg-white p-7 shadow-warm">
        <div className="flex items-center gap-2.5 text-espresso-900">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-espresso-900 text-caramel-light">
            <Coffee className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h1 className="font-serif text-2xl font-bold">Sign in to BeanBox</h1>
            <p className="text-xs text-espresso-600">
              Your guest cart merges automatically on login.
            </p>
          </div>
        </div>

        <GoogleSignInButton nextPath={nextPath} />

        <div className="my-5 flex items-center gap-3 text-[11px] uppercase tracking-wider text-espresso-400">
          <span className="h-px flex-1 bg-espresso-200" />
          <span>or with email</span>
          <span className="h-px flex-1 bg-espresso-200" />
        </div>

        {errorMsg && (
          <div
            role="alert"
            className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs font-medium text-rose-800"
          >
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="login-email"
              className="block text-xs font-semibold text-espresso-800"
            >
              Email Address <span aria-hidden="true">*</span>
            </label>
            <input
              id="login-email"
              name="email"
              type="email"
              required
              autoComplete="username"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck={false}
              enterKeyHint="next"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="auth-field mt-1 h-12 w-full rounded-xl border border-espresso-200 px-3.5 text-base"
            />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label
                htmlFor="login-password"
                className="block text-xs font-semibold text-espresso-800"
              >
                Password <span aria-hidden="true">*</span>
              </label>
              <Link
                href="/forgot-password"
                className="text-xs font-medium text-caramel-dark hover:underline"
              >
                Forgot password?
              </Link>
            </div>
            <div className="relative mt-1">
              <input
                id="login-password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                required
                autoComplete="current-password"
                enterKeyHint="done"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="auth-field h-12 w-full rounded-xl border border-espresso-200 pl-3.5 pr-11 text-base"
              />
              <button
                type="button"
                aria-pressed={showPassword}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                onClick={() => setShowPassword((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-espresso-500 hover:text-espresso-900"
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Eye className="h-4 w-4" aria-hidden="true" />
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="min-h-[48px] w-full rounded-xl bg-espresso-900 px-4 text-sm font-semibold text-white hover:bg-caramel transition disabled:opacity-50"
          >
            {submitting ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        {/* Demo Quick Fill */}
        <div className="mt-6 rounded-2xl border border-espresso-200 bg-espresso-50 p-4">
          <div className="text-xs font-semibold text-espresso-800">
            Quick Demo Accounts
          </div>
          <div className="mt-2.5 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => {
                setEmail('arjun@beanbox.in');
                setPassword('Coffee@1234');
              }}
              className="rounded-xl border border-espresso-200 bg-white px-3 py-2 text-xs font-medium text-espresso-800 hover:border-caramel"
            >
              Customer (Arjun)
            </button>
            <button
              type="button"
              onClick={() => {
                setEmail('admin@beanbox.in');
                setPassword('Admin@1234');
              }}
              className="rounded-xl border border-espresso-200 bg-white px-3 py-2 text-xs font-medium text-espresso-800 hover:border-caramel"
            >
              Roaster Admin
            </button>
          </div>
        </div>

        <p className="mt-5 text-center text-xs text-espresso-600">
          New to BeanBox?{' '}
          <Link href="/signup" className="font-semibold text-caramel-dark hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="py-14 text-center">Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
