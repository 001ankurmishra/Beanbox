'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { authApi } from '@/lib/api/endpoints';
import { ApiClientError } from '@/lib/api/client';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    setSubmitting(true);
    try {
      const res = await authApi.forgotPassword(email);
      setMessage(res.message);
    } catch (err) {
      setErrorMsg(
        err instanceof ApiClientError ? err.message : 'Request failed'
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-md px-4 py-14">
      <div className="rounded-3xl border border-espresso-200 bg-white p-7 shadow-warm">
        <h1 className="font-serif text-2xl font-bold text-espresso-900">
          Reset Password
        </h1>
        <p className="mt-1 text-xs text-espresso-600">
          Enter your email and we&apos;ll send a reset token (check the backend
          console in dev mode).
        </p>

        {message && (
          <div
            role="status"
            className="mt-4 rounded-xl border border-sage/30 bg-sage-light px-3.5 py-3 text-xs text-sage"
          >
            {message}{' '}
            <Link href="/reset-password" className="font-bold underline">
              Enter token here →
            </Link>
          </div>
        )}

        {errorMsg && (
          <div
            role="alert"
            className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-800"
          >
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div>
            <label
              htmlFor="forgot-email"
              className="block text-xs font-semibold text-espresso-800"
            >
              Email Address *
            </label>
            <input
              id="forgot-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 h-12 w-full rounded-xl border border-espresso-200 px-3.5 text-base"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="min-h-[48px] w-full rounded-xl bg-espresso-900 px-4 text-sm font-semibold text-white hover:bg-caramel transition disabled:opacity-50"
          >
            {submitting ? 'Sending…' : 'Send Reset Link'}
          </button>
        </form>

        <p className="mt-5 text-center text-xs text-espresso-600">
          Remembered your password?{' '}
          <Link href="/login" className="font-semibold text-caramel-dark hover:underline">
            Back to Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
