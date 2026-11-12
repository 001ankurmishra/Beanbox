'use client';

import React, { useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Heart, LogOut, MapPin, Package, ShieldCheck, User } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { sanitizeNextPath } from '@/lib/redirect';

const ACCOUNT_TABS = [
  { href: '/account', label: 'Profile', icon: User },
  { href: '/account/security', label: 'Security', icon: ShieldCheck },
  { href: '/account/orders', label: 'Orders', icon: Package },
  { href: '/account/addresses', label: 'Addresses', icon: MapPin },
  { href: '/account/wishlist', label: 'Wishlist', icon: Heart }
];

export default function AccountLayout({
  children
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading, logout } = useAuth();
  const { showToast } = useToast();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace(`/login?next=${encodeURIComponent(sanitizeNextPath(pathname || '/account'))}`);
    }
  }, [isLoading, user, router, pathname]);

  if (isLoading || !user) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="h-64 animate-pulse rounded-3xl bg-white border border-espresso-200" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-espresso-200 pb-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-caramel-dark">
            Member Account
          </p>
          <h1 className="mt-1 font-serif text-3xl font-bold text-espresso-900">
            Hello, {user.name}
          </h1>
          <p className="text-sm text-espresso-600">{user.email}</p>
        </div>
        <button
          type="button"
          onClick={async () => {
            await logout();
            showToast('Signed out', 'info');
            router.push('/');
          }}
          className="inline-flex min-h-[42px] items-center gap-2 rounded-xl border border-espresso-300 bg-white px-4 text-sm font-semibold text-espresso-800 hover:bg-espresso-100"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Sign out
        </button>
      </div>

      <nav aria-label="Account sections" className="mt-6 flex flex-wrap gap-2">
        {ACCOUNT_TABS.map((tab) => {
          const active =
            tab.href === '/account'
              ? pathname === '/account'
              : pathname.startsWith(tab.href);
          const Icon = tab.icon;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? 'page' : undefined}
              className={`inline-flex min-h-[42px] items-center gap-2 rounded-xl px-4 text-sm font-semibold transition ${
                active
                  ? 'bg-espresso-900 text-white'
                  : 'border border-espresso-200 bg-white text-espresso-800 hover:bg-espresso-100'
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {tab.label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-8">{children}</div>
    </div>
  );
}
