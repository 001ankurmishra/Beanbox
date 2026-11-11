'use client';

import React from 'react';
import Link from 'next/link';

export default function ErrorBoundaryPage({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-xl px-4 py-20 text-center">
      <div className="rounded-3xl border border-rose-200 bg-white p-8">
        <h1 className="font-serif text-2xl font-bold text-espresso-900">
          Something spilled in the roastery
        </h1>
        <p className="mt-2 text-sm text-espresso-600">
          {error.message || 'An unexpected client error occurred.'}
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="min-h-[44px] rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white"
          >
            Try Again
          </button>
          <Link
            href="/"
            className="inline-flex min-h-[44px] items-center rounded-xl border border-espresso-300 bg-white px-5 text-sm font-semibold text-espresso-900"
          >
            Return Home
          </Link>
        </div>
      </div>
    </div>
  );
}
