'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, IndianRupee, Package, ShoppingBag, Users } from 'lucide-react';
import { adminApi } from '@/lib/api/endpoints';
import { formatDateIN, formatINR, ORDER_STATUS_STYLES } from '@/lib/format';
import { AdminDashboardStats } from '@/types/api';
import { Badge } from '@/components/ui/Badge';

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminDashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    adminApi
      .stats()
      .then((res) => setStats(res.stats))
      .finally(() => setLoading(false));
  }, []);

  if (loading || !stats) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((n) => (
          <div
            key={n}
            className="h-28 animate-pulse rounded-2xl bg-white border border-espresso-200"
          />
        ))}
      </div>
    );
  }

  const kpis = [
    {
      label: 'Total Revenue',
      value: formatINR(stats.totalRevenuePaise),
      sub: `${stats.paidOrdersCount} paid orders`,
      icon: IndianRupee
    },
    {
      label: 'Total Orders',
      value: String(stats.totalOrders),
      sub: `${stats.pendingOrdersCount} awaiting payment`,
      icon: ShoppingBag
    },
    {
      label: 'Low Stock Variants',
      value: String(stats.lowStockVariants.length),
      sub: 'Stock <= 5 units',
      icon: AlertTriangle
    },
    {
      label: 'Registered Users',
      value: String(stats.totalCustomers),
      sub: 'Customers & admins',
      icon: Users
    }
  ];

  return (
    <div className="space-y-8">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div
              key={kpi.label}
              className="rounded-2xl border border-espresso-200 bg-white p-5"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-espresso-500">
                  {kpi.label}
                </span>
                <Icon className="h-4 w-4 text-caramel" aria-hidden="true" />
              </div>
              <div className="mt-2 font-serif text-2xl font-bold text-espresso-900">
                {kpi.value}
              </div>
              <div className="mt-1 text-xs text-espresso-600">{kpi.sub}</div>
            </div>
          );
        })}
      </div>

      {/* Top Products & Low Stock */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <section className="lg:col-span-6 rounded-2xl border border-espresso-200 bg-white p-6">
          <h2 className="font-serif text-lg font-bold text-espresso-900">
            Top Performing Products
          </h2>
          {stats.topProducts.length === 0 ? (
            <p className="mt-4 text-sm text-espresso-600">No paid sales yet.</p>
          ) : (
            <ul className="mt-4 divide-y divide-espresso-100">
              {stats.topProducts.map((tp) => (
                <li
                  key={tp.productId}
                  className="flex items-center justify-between py-3 text-sm"
                >
                  <div>
                    <div className="font-semibold text-espresso-900">
                      {tp.productName}
                    </div>
                    <div className="text-xs text-espresso-500">
                      {tp.unitsSold} unit(s) sold
                    </div>
                  </div>
                  <span className="font-bold text-espresso-900">
                    {formatINR(tp.revenuePaise)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="lg:col-span-6 rounded-2xl border border-espresso-200 bg-white p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-serif text-lg font-bold text-espresso-900">
              Low Stock Alerts (≤ 5)
            </h2>
            <Link
              href="/admin/inventory"
              className="text-xs font-semibold text-caramel-dark hover:underline"
            >
              Restock →
            </Link>
          </div>
          {stats.lowStockVariants.length === 0 ? (
            <p className="mt-4 text-sm text-sage">All variants are well stocked.</p>
          ) : (
            <ul className="mt-4 divide-y divide-espresso-100">
              {stats.lowStockVariants.map((entry) => (
                <li
                  key={entry.variant.id}
                  className="flex items-center justify-between py-3 text-sm"
                >
                  <div>
                    <div className="font-semibold text-espresso-900">
                      {entry.productName}
                    </div>
                    <div className="text-xs text-espresso-500">
                      {entry.variant.label} ({entry.variant.sku})
                    </div>
                  </div>
                  <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-bold text-amber-900">
                    {entry.variant.stock} left
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* Recent Orders */}
      <section className="rounded-2xl border border-espresso-200 bg-white p-6">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-serif text-lg font-bold text-espresso-900">
            <Package className="h-5 w-5 text-caramel" aria-hidden="true" />
            Recent Orders
          </h2>
          <Link
            href="/admin/orders"
            className="text-xs font-semibold text-caramel-dark hover:underline"
          >
            Manage all orders →
          </Link>
        </div>

        <div
          tabIndex={0}
          role="region"
          aria-label="Recent orders table"
          className="table-scroll-region mt-4"
        >
          <table className="text-left text-sm">
            <thead className="bg-espresso-50 text-xs uppercase text-espresso-600">
              <tr>
                <th className="px-3 py-2.5">Order #</th>
                <th className="px-3 py-2.5">Customer</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5 text-right">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-espresso-100">
              {stats.recentOrders.map((ord) => {
                const badge = ORDER_STATUS_STYLES[ord.status];
                return (
                  <tr key={ord.id}>
                    <th scope="row" className="px-3 py-3 font-mono font-semibold">
                      {ord.orderNumber}
                    </th>
                    <td className="px-3 py-3 text-espresso-700">
                      {ord.shippingAddress.fullName}
                    </td>
                    <td className="px-3 py-3 text-espresso-500">
                      {formatDateIN(ord.createdAt)}
                    </td>
                    <td className="px-3 py-3">
                      <Badge className={badge.badgeClass}>{badge.label}</Badge>
                    </td>
                    <td className="px-3 py-3 text-right font-bold">
                      {formatINR(ord.pricing.totalPaise)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
