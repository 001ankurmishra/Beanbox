'use client';

import React from 'react';

export default function GlobalError({
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="flex min-h-screen items-center justify-center bg-[#FBF7F2] p-6 text-[#26150E]">
        <div className="max-w-md rounded-2xl border border-[#E6D3C0] bg-white p-8 text-center">
          <h1 className="text-2xl font-bold">Application Error</h1>
          <p className="mt-2 text-sm text-[#5C341E]">
            Please refresh or try again.
          </p>
          <button
            type="button"
            onClick={reset}
            className="mt-5 rounded-xl bg-[#26150E] px-5 py-2.5 text-sm font-semibold text-white"
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
