'use client';

import React, { useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  Boxes,
  Coffee,
  FileSearch,
  LayoutDashboard,
  PackageCheck,
  ShieldAlert,
  Ticket
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

const ADMIN_LINKS = [
  { href: '/admin', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/admin/products', label: 'Products', icon: Coffee },
  { href: '/admin/orders', label: 'Orders', icon: PackageCheck },
  { href: '/admin/inventory', label: 'Inventory', icon: Boxes },
  { href: '/admin/coupons', label: 'Coupons', icon: Ticket },
  { href: '/admin/audit-logs', label: 'Audit Logs', icon: FileSearch }
];

export default function AdminLayout({
  children
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/login?next=/admin');
      return;
    }
    if (!isLoading && user && user.role === 'admin' && !user.totpEnabled) {
      router.replace('/account/security?enforce2fa=1');
    }
  }, [isLoading, user, router]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12">
        <div className="h-64 animate-pulse rounded-3xl bg-white border border-espresso-200" />
      </div>
    );
  }

  if (!user) return null;

  if (user.role !== 'admin') {
    return (
      <div className="mx-auto max-w-xl px-4 py-16 text-center">
        <div className="rounded-3xl border border-rose-200 bg-white p-8">
          <ShieldAlert className="mx-auto h-10 w-10 text-rose-700" aria-hidden="true" />
          <h1 className="mt-4 font-serif text-2xl font-bold text-espresso-900">
            Admin Access Required
          </h1>
          <p className="mt-2 text-sm text-espresso-600">
            Signed in as <strong>{user.email}</strong> ({user.role}). Sign in with
            an admin account (e.g. <code>admin@beanbox.in</code>) to manage the
            roastery.
          </p>
          <Link
            href="/"
            className="mt-6 inline-flex min-h-[44px] items-center rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white"
          >
            Back to Storefront
          </Link>
        </div>
      </div>
    );
  }

  if (!user.totpEnabled) {
    return (
      <div className="mx-auto max-w-xl px-4 py-16 text-center">
        <div className="rounded-3xl border border-amber-200 bg-white p-8">
          <ShieldAlert className="mx-auto h-10 w-10 text-amber-700" aria-hidden="true" />
          <h1 className="mt-4 font-serif text-2xl font-bold text-espresso-900">
            2FA Setup Required
          </h1>
          <p className="mt-2 text-sm text-espresso-600">
            Redirecting you to Security Settings to enable Two-Factor Authentication…
          </p>
          <Link
            href="/account/security?enforce2fa=1"
            className="mt-6 inline-flex min-h-[44px] items-center rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white"
          >
            Set Up 2FA
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-espresso-200 pb-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-caramel-dark">
            BeanBox Operations
          </p>
          <h1 className="font-serif text-3xl font-bold text-espresso-900">
            Roastery Admin Console
          </h1>
        </div>

        <nav aria-label="Admin sections" className="flex flex-wrap gap-2">
          {ADMIN_LINKS.map((item) => {
            const active =
              item.href === '/admin'
                ? pathname === '/admin'
                : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className={`inline-flex min-h-[40px] items-center gap-2 rounded-xl px-3.5 text-xs font-semibold transition ${
                  active
                    ? 'bg-espresso-900 text-white'
                    : 'border border-espresso-200 bg-white text-espresso-800 hover:bg-espresso-100'
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="mt-8">{children}</div>
    </div>
  );
}
