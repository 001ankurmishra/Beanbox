'use client';

import React, { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertTriangle, CheckCircle2, Clock, ShieldCheck } from 'lucide-react';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { ordersApi, paymentsApi } from '@/lib/api/endpoints';
import { formatINR } from '@/lib/format';
import { Order } from '@/types/api';

function MockPayContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { showToast } = useToast();

  const orderId = searchParams.get('orderId') || '';
  const sessionId = searchParams.get('sessionId') || '';

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    if (!orderId) {
      setLoading(false);
      return;
    }
    ordersApi
      .detail(orderId)
      .then((res) => setOrder(res.order))
      .catch(() => setOrder(null))
      .finally(() => setLoading(false));
  }, [orderId]);

  const handleOutcome = async (outcome: 'success' | 'failed' | 'expired') => {
    if (!orderId) return;
    setProcessing(true);
    try {
      await paymentsApi.triggerMock(orderId, outcome);
      if (outcome === 'success') {
        showToast('Payment confirmed via signed webhook!', 'success');
        router.replace(`/orders/success?orderId=${encodeURIComponent(orderId)}`);
      } else {
        showToast(
          outcome === 'expired'
            ? 'Session expired — reserved stock released back to catalog'
            : 'Payment failed — reserved stock released back to catalog',
          'info'
        );
        router.replace(`/account/orders/${encodeURIComponent(orderId)}`);
      }
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Webhook simulation failed',
        'error'
      );
      setProcessing(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <div className="h-80 animate-pulse rounded-3xl bg-white border border-espresso-200" />
      </div>
    );
  }

  if (!order) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <h1 className="font-serif text-2xl font-bold text-espresso-900">
          Payment Session Not Found
        </h1>
        <p className="mt-2 text-sm text-espresso-600">
          Please sign in as the order owner or start checkout from your bag.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-12">
      <div className="rounded-3xl border border-espresso-200 bg-white p-7 shadow-warm">
        <div className="flex items-center justify-between border-b border-espresso-100 pb-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-espresso-900">
            <ShieldCheck className="h-5 w-5 text-caramel" aria-hidden="true" />
            BeanBox Test Checkout
          </div>
          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-bold text-amber-900">
            MOCK MODE
          </span>
        </div>

        <div className="mt-5 space-y-2 text-sm">
          <div className="flex justify-between text-espresso-600">
            <span>Order Number</span>
            <span className="font-mono font-semibold text-espresso-900">
              {order.orderNumber}
            </span>
          </div>
          <div className="flex justify-between text-espresso-600">
            <span>Session ID</span>
            <span className="font-mono text-xs text-espresso-700 truncate max-w-[200px]">
              {sessionId || order.paymentSessionId}
            </span>
          </div>
          <div className="flex justify-between border-t border-espresso-100 pt-3 text-lg font-bold text-espresso-900">
            <span>Amount Due</span>
            <span>{formatINR(order.pricing.totalPaise)}</span>
          </div>
        </div>

        <p className="mt-4 rounded-xl bg-espresso-50 p-3 text-xs text-espresso-700 leading-relaxed">
          No Stripe keys are configured, so BeanBox runs its HMAC-SHA256 signed
          mock webhook gateway. Choose an outcome below to test the real webhook
          and stock reservation pipeline:
        </p>

        <div className="mt-6 space-y-3">
          <button
            type="button"
            disabled={processing}
            onClick={() => handleOutcome('success')}
            className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-sage px-4 text-sm font-semibold text-white hover:opacity-95 disabled:opacity-50"
          >
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            Pay {formatINR(order.pricing.totalPaise)} (Simulate Success)
          </button>

          <button
            type="button"
            disabled={processing}
            onClick={() => handleOutcome('failed')}
            className="flex min-h-[46px] w-full items-center justify-center gap-2 rounded-xl border border-rose-300 bg-rose-50 px-4 text-sm font-semibold text-rose-800 hover:bg-rose-100 disabled:opacity-50"
          >
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            Simulate Card Failure (Release Stock)
          </button>

          <button
            type="button"
            disabled={processing}
            onClick={() => handleOutcome('expired')}
            className="flex min-h-[46px] w-full items-center justify-center gap-2 rounded-xl border border-espresso-300 bg-white px-4 text-sm font-semibold text-espresso-800 hover:bg-espresso-100 disabled:opacity-50"
          >
            <Clock className="h-4 w-4" aria-hidden="true" />
            Simulate Expired Session (Release Stock)
          </button>
        </div>
      </div>
    </div>
  );
}

export default function MockPayPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-lg px-4 py-16">
          <div className="h-80 animate-pulse rounded-3xl bg-white" />
        </div>
      }
    >
      <MockPayContent />
    </Suspense>
  );
}
