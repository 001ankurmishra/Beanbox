'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { MailWarning, ShieldAlert } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { authApi } from '@/lib/api/endpoints';

export function VerifyEmailBanner() {
  const { user } = useAuth();
  const { showToast } = useToast();
  const [sending, setSending] = useState(false);

  if (!user) return null;

  const needsAdmin2fa = user.role === 'admin' && !user.totpEnabled;
  const needsVerify = !user.emailVerified;

  if (!needsVerify && !needsAdmin2fa) return null;

  const handleResend = async () => {
    setSending(true);
    try {
      const res = await authApi.resendVerification();
      showToast(res.message, 'success');
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Please wait before resending',
        'error'
      );
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      role="region"
      aria-label="Account security notifications"
      className="border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-950"
    >
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 sm:px-2">
        {needsVerify ? (
          <div className="flex flex-wrap items-center gap-2">
            <MailWarning className="h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
            <span>
              Please verify <strong>{user.email}</strong> to place orders at checkout.
            </span>
            <button
              type="button"
              disabled={sending}
              onClick={handleResend}
              className="rounded-lg border border-amber-300 bg-white px-2.5 py-1 font-semibold text-amber-900 hover:bg-amber-100 disabled:opacity-50"
            >
              {sending ? 'Sending…' : 'Resend email'}
            </button>
            <Link
              href="/verify-email"
              className="font-semibold underline text-amber-900 hover:text-espresso-900"
            >
              Enter token
            </Link>
          </div>
        ) : (
          <span />
        )}

        {needsAdmin2fa && (
          <div className="flex items-center gap-2 font-semibold text-rose-900">
            <ShieldAlert className="h-4 w-4 shrink-0 text-rose-700" aria-hidden="true" />
            <span>Admin accounts require 2FA before using the console.</span>
            <Link
              href="/account/security?enforce2fa=1"
              className="rounded-lg bg-rose-700 px-2.5 py-1 text-white hover:bg-rose-800"
            >
              Set up 2FA now
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
