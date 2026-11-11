import Link from 'next/link';
import { Coffee } from 'lucide-react';

export default function NotFoundPage() {
  return (
    <div className="mx-auto max-w-xl px-4 py-20 text-center">
      <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-espresso-100 text-espresso-700">
        <Coffee className="h-8 w-8" aria-hidden="true" />
      </div>
      <p className="mt-4 text-xs font-bold uppercase tracking-widest text-caramel-dark">
        404 — Page Not Found
      </p>
      <h1 className="mt-2 font-serif text-3xl font-bold text-espresso-900">
        This cup ran dry
      </h1>
      <p className="mt-2 text-sm text-espresso-600">
        We couldn&apos;t find the page you were looking for. Let&apos;s get you back
        to fresh roasts.
      </p>
      <div className="mt-6 flex justify-center gap-3">
        <Link
          href="/"
          className="inline-flex min-h-[44px] items-center rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white hover:bg-caramel"
        >
          Go Home
        </Link>
        <Link
          href="/shop"
          className="inline-flex min-h-[44px] items-center rounded-xl border border-espresso-300 bg-white px-5 text-sm font-semibold text-espresso-900"
        >
          Browse Shop
        </Link>
      </div>
    </div>
  );
}
