'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Package } from 'lucide-react';
import { ordersApi } from '@/lib/api/endpoints';
import { formatDateIN, formatINR, ORDER_STATUS_STYLES } from '@/lib/format';
import { Order, PaginationMeta } from '@/types/api';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';

export default function AccountOrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    ordersApi
      .list(page, 10)
      .then((res) => {
        setOrders(res.items);
        setPagination(res.pagination);
      })
      .finally(() => setLoading(false));
  }, [page]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-28 animate-pulse rounded-2xl bg-white border border-espresso-200" />
        <div className="h-28 animate-pulse rounded-2xl bg-white border border-espresso-200" />
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <EmptyState
        icon={<Package className="h-7 w-7" aria-hidden="true" />}
        title="No orders yet"
        description="Once you place your first roast order, track deliveries and download GST invoices here."
        actionLabel="Shop Coffees"
        actionHref="/shop"
      />
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="font-serif text-xl font-bold text-espresso-900">
        Your Order History
      </h2>

      {orders.map((order) => {
        const badge = ORDER_STATUS_STYLES[order.status];
        return (
          <div
            key={order.id}
            className="flex flex-col gap-4 rounded-2xl border border-espresso-200 bg-white p-5 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-mono text-sm font-bold text-espresso-900">
                  {order.orderNumber}
                </span>
                <Badge className={badge.badgeClass}>{badge.label}</Badge>
              </div>
              <p className="mt-1 text-xs text-espresso-600">
                Placed on {formatDateIN(order.createdAt)} · {order.items.length}{' '}
                item(s) · {order.shippingAddress.city},{' '}
                {order.shippingAddress.state}
              </p>
            </div>

            <div className="flex items-center justify-between gap-4 sm:justify-end">
              <div className="text-right">
                <span className="block text-[11px] text-espresso-500">Total</span>
                <span className="text-base font-bold text-espresso-900">
                  {formatINR(order.pricing.totalPaise)}
                </span>
              </div>
              <Link
                href={`/account/orders/${order.id}`}
                className="inline-flex min-h-[40px] items-center rounded-xl border border-espresso-300 bg-espresso-50 px-4 text-xs font-semibold text-espresso-900 hover:bg-espresso-100"
              >
                View Details
              </Link>
            </div>
          </div>
        );
      })}

      {pagination && pagination.totalPages > 1 && (
        <div className="flex justify-center gap-2 pt-4">
          <button
            type="button"
            disabled={!pagination.hasPrev}
            onClick={() => setPage((p) => p - 1)}
            className="min-h-[40px] rounded-xl border border-espresso-200 bg-white px-4 text-xs font-semibold disabled:opacity-40"
          >
            Previous
          </button>
          <button
            type="button"
            disabled={!pagination.hasNext}
            onClick={() => setPage((p) => p + 1)}
            className="min-h-[40px] rounded-xl border border-espresso-200 bg-white px-4 text-xs font-semibold disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
