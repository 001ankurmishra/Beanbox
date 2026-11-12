'use client';

import React, { Suspense, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { CheckCircle2, MailCheck, Send } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { authApi } from '@/lib/api/endpoints';

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const queryToken = searchParams.get('token') || '';
  const { user, refreshUser } = useAuth();
  const { showToast } = useToast();

  const [token, setToken] = useState(queryToken);
  const [status, setStatus] = useState<'idle' | 'verifying' | 'verified' | 'error'>(
    queryToken ? 'verifying' : 'idle'
  );
  const [message, setMessage] = useState('');
  const [resending, setResending] = useState(false);

  const attemptedTokenRef = useRef<string | null>(null);

  useEffect(() => {
    if (!queryToken || attemptedTokenRef.current === queryToken) return;
    attemptedTokenRef.current = queryToken;
    setStatus('verifying');
    authApi
      .verifyEmail(queryToken)
      .then(async (res) => {
        setStatus('verified');
        setMessage(res.message);
        await refreshUser();
      })
      .catch((err) => {
        setStatus('error');
        setMessage(
          err instanceof ApiClientError
            ? err.message
            : 'Invalid or expired verification token'
        );
      });
  }, [queryToken, refreshUser]);

  const handleManualVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = token.trim();
    if (!cleaned) return;
    setStatus('verifying');
    setMessage('');
    try {
      const res = await authApi.verifyEmail(cleaned);
      setStatus('verified');
      setMessage(res.message);
      await refreshUser();
      showToast('Email verified!', 'success');
    } catch (err) {
      setStatus('error');
      setMessage(
        err instanceof ApiClientError
          ? err.message
          : 'Verification token is invalid or expired'
      );
    }
  };

  const handleResend = async () => {
    setResending(true);
    try {
      const res = await authApi.resendVerification();
      showToast(res.message, 'success');
    } catch (err) {
      showToast(
        err instanceof ApiClientError
          ? err.message
          : 'Unable to resend right now',
        'error'
      );
    } finally {
      setResending(false);
    }
  };

  const isAlreadyVerified = Boolean(user?.emailVerified) || status === 'verified';

  return (
    <div className="mx-auto max-w-md px-4 py-14">
      <div className="rounded-3xl border border-espresso-200 bg-white p-7 shadow-warm">
        <div className="flex items-center gap-2.5 text-espresso-900">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-espresso-900 text-caramel-light">
            {isAlreadyVerified ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-300" aria-hidden="true" />
            ) : (
              <MailCheck className="h-5 w-5" aria-hidden="true" />
            )}
          </span>
          <div>
            <h1 className="font-serif text-2xl font-bold">Verify Your Email</h1>
            <p className="text-xs text-espresso-600">
              Verified emails are required before placing orders.
            </p>
          </div>
        </div>

        {isAlreadyVerified ? (
          <div className="mt-6 space-y-4">
            <div
              role="status"
              className="rounded-2xl border border-sage/30 bg-sage-light p-4 text-sm text-sage"
            >
              <strong>Your email is verified.</strong>{' '}
              {message || 'You are ready to complete checkout anytime.'}
            </div>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/shop"
                className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-xl bg-espresso-900 px-4 text-sm font-semibold text-white hover:bg-caramel"
              >
                Shop Coffee
              </Link>
              <Link
                href="/checkout"
                className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-xl border border-espresso-300 bg-white px-4 text-sm font-semibold text-espresso-900 hover:bg-espresso-50"
              >
                Go to Checkout
              </Link>
            </div>
          </div>
        ) : (
          <>
            {status === 'verifying' && (
              <p role="status" className="mt-5 text-sm text-espresso-700">
                Verifying your token…
              </p>
            )}

            {status === 'error' && message && (
              <div
                role="alert"
                className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs font-medium text-rose-800"
              >
                {message}
              </div>
            )}

            <form onSubmit={handleManualVerify} className="mt-6 space-y-4">
              <div>
                <label
                  htmlFor="verify-token"
                  className="block text-xs font-semibold text-espresso-800"
                >
                  Verification Token <span aria-hidden="true">*</span>
                </label>
                <p id="verify-hint" className="mt-0.5 text-xs text-espresso-500">
                  Check your verification email (or backend console in dev mode) for
                  the single-use token.
                </p>
                <input
                  id="verify-token"
                  name="token"
                  type="text"
                  required
                  minLength={16}
                  autoCorrect="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  aria-describedby="verify-hint"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  className="auth-field mt-1.5 h-12 w-full rounded-xl border border-espresso-200 px-3.5 font-mono text-sm"
                />
              </div>

              <button
                type="submit"
                disabled={status === 'verifying'}
                className="min-h-[48px] w-full rounded-xl bg-espresso-900 px-4 text-sm font-semibold text-white hover:bg-caramel transition disabled:opacity-50"
              >
                {status === 'verifying' ? 'Verifying…' : 'Verify Email'}
              </button>
            </form>

            {user && (
              <div className="mt-6 rounded-2xl border border-espresso-200 bg-espresso-50 p-4">
                <p className="text-xs text-espresso-700">
                  Signed in as <strong>{user.email}</strong>. Didn&apos;t receive the
                  link?
                </p>
                <button
                  type="button"
                  disabled={resending}
                  onClick={handleResend}
                  className="mt-2.5 inline-flex min-h-[40px] items-center gap-2 rounded-xl border border-espresso-300 bg-white px-4 text-xs font-semibold text-espresso-900 hover:bg-espresso-100 disabled:opacity-50"
                >
                  <Send className="h-3.5 w-3.5" aria-hidden="true" />
                  {resending ? 'Sending…' : 'Resend Verification Email'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="py-14 text-center">Loading…</div>}>
      <VerifyEmailContent />
    </Suspense>
  );
}
