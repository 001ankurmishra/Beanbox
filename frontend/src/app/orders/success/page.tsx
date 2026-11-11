'use client';

import React, { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { CheckCircle2, FileText, Package } from 'lucide-react';
import { ordersApi } from '@/lib/api/endpoints';
import { formatINR } from '@/lib/format';
import { Order } from '@/types/api';

function OrderSuccessContent() {
  const searchParams = useSearchParams();
  const orderId = searchParams.get('orderId') || '';
  const [order, setOrder] = useState<Order | null>(null);

  useEffect(() => {
    if (!orderId) return;
    ordersApi
      .detail(orderId)
      .then((res) => setOrder(res.order))
      .catch(() => setOrder(null));
  }, [orderId]);

  return (
    <div className="mx-auto max-w-2xl px-4 py-16 text-center">
      <div className="rounded-3xl border border-espresso-200 bg-white p-8 shadow-warm">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-sage-light text-sage">
          <CheckCircle2 className="h-9 w-9" aria-hidden="true" />
        </div>
        <h1 className="mt-5 font-serif text-3xl font-bold text-espresso-900">
          Brew Order Confirmed!
        </h1>
        <p className="mt-2 text-sm text-espresso-600">
          Thank you for ordering from BeanBox. Your coffee is queued for fresh
          small-batch roasting.
        </p>

        {order && (
          <div className="mt-6 rounded-2xl border border-espresso-200 bg-espresso-50 p-5 text-left text-sm space-y-2">
            <div className="flex justify-between">
              <span className="text-espresso-600">Order Number</span>
              <span className="font-mono font-bold text-espresso-900">
                {order.orderNumber}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-espresso-600">Payment Status</span>
              <span className="font-semibold capitalize text-sage">
                {order.paymentStatus}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-espresso-600">Total Paid (incl. 5% GST)</span>
              <span className="font-bold text-espresso-900">
                {formatINR(order.pricing.totalPaise)}
              </span>
            </div>
          </div>
        )}

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          {orderId && (
            <Link
              href={`/account/orders/${encodeURIComponent(orderId)}`}
              className="inline-flex min-h-[46px] items-center gap-2 rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white hover:bg-caramel transition"
            >
              <FileText className="h-4 w-4" aria-hidden="true" />
              View Order & GST Invoice
            </Link>
          )}
          <Link
            href="/shop"
            className="inline-flex min-h-[46px] items-center gap-2 rounded-xl border border-espresso-300 bg-white px-5 text-sm font-semibold text-espresso-900 hover:bg-espresso-100"
          >
            <Package className="h-4 w-4" aria-hidden="true" />
            Continue Shopping
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function OrderSuccessPage() {
  return (
    <Suspense fallback={<div className="py-16 text-center">Loading order…</div>}>
      <OrderSuccessContent />
    </Suspense>
  );
}
