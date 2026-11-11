import React from 'react';
import Link from 'next/link';
import { Coffee } from 'lucide-react';

interface EmptyStateProps {
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  icon?: React.ReactNode;
}

export function EmptyState({
  title,
  description,
  actionLabel,
  actionHref,
  onAction,
  icon
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-espresso-300 bg-white/70 px-6 py-12 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-espresso-100 text-espresso-700">
        {icon ?? <Coffee className="h-7 w-7" aria-hidden="true" />}
      </div>
      <h2 className="font-serif text-xl font-semibold text-espresso-900">{title}</h2>
      <p className="mt-2 max-w-md text-sm text-espresso-600">{description}</p>
      {actionLabel && actionHref && (
        <Link
          href={actionHref}
          className="mt-6 inline-flex min-h-[44px] items-center rounded-xl bg-espresso-900 px-5 py-2.5 text-sm font-semibold text-espresso-50 hover:bg-espresso-800 transition"
        >
          {actionLabel}
        </Link>
      )}
      {actionLabel && onAction && !actionHref && (
        <button
          type="button"
          onClick={onAction}
          className="mt-6 inline-flex min-h-[44px] items-center rounded-xl bg-espresso-900 px-5 py-2.5 text-sm font-semibold text-espresso-50 hover:bg-espresso-800 transition"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
