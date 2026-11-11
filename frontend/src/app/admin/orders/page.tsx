'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { adminApi } from '@/lib/api/endpoints';
import { formatDateIN, formatINR, ORDER_STATUS_STYLES } from '@/lib/format';
import { Order, OrderStatus } from '@/types/api';
import { Badge } from '@/components/ui/Badge';

const ALLOWED_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  pending: ['paid', 'cancelled'],
  paid: ['processing', 'cancelled', 'refunded'],
  processing: ['shipped', 'cancelled', 'refunded'],
  shipped: ['delivered'],
  delivered: ['refunded'],
  cancelled: [],
  refunded: []
};

export default function AdminOrdersPage() {
  const { showToast } = useToast();
  const [orders, setOrders] = useState<Order[]>([]);
  const [filterStatus, setFilterStatus] = useState<OrderStatus | ''>('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminApi.listOrders({
        status: filterStatus || undefined,
        limit: 50
      });
      setOrders(res.items);
    } finally {
      setLoading(false);
    }
  }, [filterStatus]);

  useEffect(() => {
    load();
  }, [load]);

  const handleTransition = async (orderId: string, nextStatus: OrderStatus) => {
    try {
      await adminApi.updateOrderStatus(orderId, nextStatus);
      showToast(`Order transitioned to '${nextStatus}'`, 'success');
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Transition failed',
        'error'
      );
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="font-serif text-xl font-bold text-espresso-900">
          Order Fulfillment ({orders.length})
        </h2>
        <div className="flex items-center gap-2">
          <label htmlFor="ord-filter" className="text-xs font-semibold">
            Filter:
          </label>
          <select
            id="ord-filter"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as OrderStatus | '')}
            className="h-10 rounded-xl border border-espresso-200 bg-white px-3 text-xs font-semibold"
          >
            <option value="">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="paid">Paid</option>
            <option value="processing">Processing</option>
            <option value="shipped">Shipped</option>
            <option value="delivered">Delivered</option>
            <option value="cancelled">Cancelled</option>
            <option value="refunded">Refunded</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="h-64 animate-pulse rounded-2xl bg-white border border-espresso-200" />
      ) : (
        <div
          tabIndex={0}
          role="region"
          aria-label="Admin orders management table"
          className="table-scroll-region rounded-2xl border border-espresso-200 bg-white"
        >
          <table className="text-left text-sm">
            <thead className="bg-espresso-50 text-xs uppercase text-espresso-600">
              <tr>
                <th className="px-4 py-3">Order</th>
                <th className="px-4 py-3">Buyer</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Total</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Advance Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-espresso-100">
              {orders.map((ord) => {
                const badge = ORDER_STATUS_STYLES[ord.status];
                const nextOptions = ALLOWED_TRANSITIONS[ord.status] || [];
                return (
                  <tr key={ord.id}>
                    <th scope="row" className="px-4 py-3 font-mono font-semibold">
                      {ord.orderNumber}
                    </th>
                    <td className="px-4 py-3 text-xs">
                      <div className="font-semibold text-espresso-900">
                        {ord.shippingAddress.fullName}
                      </div>
                      <div className="text-espresso-500">
                        {ord.shippingAddress.city}, {ord.shippingAddress.state}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-espresso-600">
                      {formatDateIN(ord.createdAt)}
                    </td>
                    <td className="px-4 py-3 font-bold">
                      {formatINR(ord.pricing.totalPaise)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge className={badge.badgeClass}>{badge.label}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      {nextOptions.length === 0 ? (
                        <span className="text-xs text-espresso-400">Terminal</span>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {nextOptions.map((next) => (
                            <button
                              key={next}
                              type="button"
                              onClick={() => handleTransition(ord.id, next)}
                              className="rounded-lg border border-espresso-300 bg-espresso-50 px-2.5 py-1 text-xs font-semibold capitalize hover:bg-espresso-900 hover:text-white transition"
                            >
                              → {next}
                            </button>
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
