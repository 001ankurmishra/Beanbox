'use client';

import React, { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { authApi } from '@/lib/api/endpoints';
import { ApiClientError } from '@/lib/api/client';
import { useToast } from '@/context/ToastContext';

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { showToast } = useToast();

  const [token, setToken] = useState(searchParams.get('token') || '');
  const [newPassword, setNewPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    setSubmitting(true);
    try {
      await authApi.resetPassword({ token, newPassword });
      showToast('Password updated! Please sign in.', 'success');
      router.push('/login');
    } catch (err) {
      setErrorMsg(
        err instanceof ApiClientError ? err.message : 'Reset failed'
      );
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-md px-4 py-14">
      <div className="rounded-3xl border border-espresso-200 bg-white p-7 shadow-warm">
        <h1 className="font-serif text-2xl font-bold text-espresso-900">
          Set New Password
        </h1>

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
              htmlFor="reset-token"
              className="block text-xs font-semibold text-espresso-800"
            >
              Reset Token *
            </label>
            <input
              id="reset-token"
              type="text"
              required
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="mt-1 h-12 w-full rounded-xl border border-espresso-200 px-3.5 text-sm font-mono"
            />
          </div>

          <div>
            <label
              htmlFor="reset-pw"
              className="block text-xs font-semibold text-espresso-800"
            >
              New Password (min 8 chars) *
            </label>
            <input
              id="reset-pw"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="mt-1 h-12 w-full rounded-xl border border-espresso-200 px-3.5 text-base"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="min-h-[48px] w-full rounded-xl bg-espresso-900 px-4 text-sm font-semibold text-white hover:bg-caramel transition disabled:opacity-50"
          >
            {submitting ? 'Updating…' : 'Update Password'}
          </button>
        </form>

        <p className="mt-5 text-center text-xs text-espresso-600">
          <Link href="/login" className="font-semibold text-caramel-dark hover:underline">
            Back to Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="py-14 text-center">Loading…</div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}
