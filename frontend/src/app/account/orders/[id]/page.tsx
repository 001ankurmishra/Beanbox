'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, CreditCard, FileText, Printer, XCircle } from 'lucide-react';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { ordersApi, paymentsApi } from '@/lib/api/endpoints';
import { formatDateIN, formatINR, ORDER_STATUS_STYLES } from '@/lib/format';
import { Order, OrderInvoice } from '@/types/api';
import { Badge } from '@/components/ui/Badge';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { showToast } = useToast();

  const [order, setOrder] = useState<Order | null>(null);
  const [invoice, setInvoice] = useState<OrderInvoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ordRes, invRes] = await Promise.all([
        ordersApi.detail(params.id),
        ordersApi.invoice(params.id)
      ]);
      setOrder(ordRes.order);
      setInvoice(invRes.invoice);
    } catch {
      setOrder(null);
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  const handlePayNow = async () => {
    if (!order) return;
    try {
      const { session } = await paymentsApi.createSession(order.id);
      if (session.provider === 'mock') {
        const parsed = new URL(session.checkoutUrl);
        router.push(`${parsed.pathname}${parsed.search}`);
      } else {
        window.location.href = session.checkoutUrl;
      }
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Could not resume payment',
        'error'
      );
    }
  };

  const handleCancelOrder = async () => {
    if (!order) return;
    setCancelling(true);
    try {
      await ordersApi.cancel(order.id, 'Cancelled by customer');
      showToast('Order cancelled and reserved stock released', 'info');
      setShowCancelModal(false);
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Could not cancel order',
        'error'
      );
    } finally {
      setCancelling(false);
    }
  };

  if (loading) {
    return (
      <div className="h-80 animate-pulse rounded-2xl bg-white border border-espresso-200" />
    );
  }

  if (!order) {
    return (
      <div className="rounded-2xl border border-espresso-200 bg-white p-8 text-center">
        <p className="font-serif text-xl font-bold">Order not found</p>
        <Link
          href="/account/orders"
          className="mt-4 inline-block text-sm font-semibold text-caramel-dark hover:underline"
        >
          ← Back to Orders
        </Link>
      </div>
    );
  }

  const badge = ORDER_STATUS_STYLES[order.status];
  const canCancel = ['pending', 'paid', 'processing'].includes(order.status);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link
            href="/account/orders"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-espresso-600 hover:text-caramel-dark"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            All Orders
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h2 className="font-mono text-2xl font-bold text-espresso-900">
              {order.orderNumber}
            </h2>
            <Badge className={badge.badgeClass}>{badge.label}</Badge>
          </div>
          <p className="mt-1 text-xs text-espresso-600">
            Placed {formatDateIN(order.createdAt)} · Payment status:{' '}
            <strong className="capitalize">{order.paymentStatus}</strong>
          </p>
        </div>

        <div className="flex flex-wrap gap-2.5">
          {order.status === 'pending' && (
            <button
              type="button"
              onClick={handlePayNow}
              className="inline-flex min-h-[42px] items-center gap-2 rounded-xl bg-sage px-4 text-xs font-semibold text-white hover:opacity-95"
            >
              <CreditCard className="h-4 w-4" aria-hidden="true" />
              Complete Payment
            </button>
          )}
          {canCancel && (
            <button
              type="button"
              onClick={() => setShowCancelModal(true)}
              className="inline-flex min-h-[42px] items-center gap-2 rounded-xl border border-rose-300 bg-rose-50 px-4 text-xs font-semibold text-rose-800 hover:bg-rose-100"
            >
              <XCircle className="h-4 w-4" aria-hidden="true" />
              Cancel Order
            </button>
          )}
        </div>
      </div>

      {/* Items & Shipping */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-7 rounded-2xl border border-espresso-200 bg-white p-5">
          <h3 className="font-serif text-lg font-bold text-espresso-900">
            Items Ordered
          </h3>
          <ul className="mt-4 divide-y divide-espresso-100">
            {order.items.map((item) => (
              <li
                key={item.variantId}
                className="flex items-center justify-between gap-4 py-3 text-sm"
              >
                <div className="flex items-center gap-3">
                  <img
                    src={item.image}
                    alt={item.productName}
                    className="h-14 w-14 rounded-xl bg-espresso-100 object-cover"
                  />
                  <div>
                    <Link
                      href={`/products/${item.productSlug}`}
                      className="font-semibold text-espresso-900 hover:text-caramel"
                    >
                      {item.productName}
                    </Link>
                    <p className="text-xs text-espresso-500">
                      {item.variantLabel} · Qty {item.quantity} ×{' '}
                      {formatINR(item.unitPricePaise)}
                    </p>
                  </div>
                </div>
                <span className="font-bold text-espresso-900">
                  {formatINR(item.lineTotalPaise)}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="lg:col-span-5 space-y-4">
          <div className="rounded-2xl border border-espresso-200 bg-white p-5">
            <h3 className="font-serif text-lg font-bold text-espresso-900">
              Shipping Address
            </h3>
            <p className="mt-2 text-xs text-espresso-700 leading-relaxed">
              <strong>{order.shippingAddress.fullName}</strong> (
              {order.shippingAddress.label})
              <br />
              {order.shippingAddress.line1}
              {order.shippingAddress.line2
                ? `, ${order.shippingAddress.line2}`
                : ''}
              <br />
              {order.shippingAddress.city}, {order.shippingAddress.state} —{' '}
              {order.shippingAddress.postalCode}
              <br />
              Mobile: {order.shippingAddress.phone}
            </p>
          </div>

          <div className="rounded-2xl border border-espresso-200 bg-white p-5 space-y-2 text-sm">
            <h3 className="font-serif text-lg font-bold text-espresso-900">
              Payment Summary
            </h3>
            <div className="flex justify-between text-espresso-700">
              <span>Items Subtotal</span>
              <span>{formatINR(order.pricing.itemsSubtotalPaise)}</span>
            </div>
            {order.pricing.discountPaise > 0 && (
              <div className="flex justify-between text-sage">
                <span>Discount ({order.couponCode})</span>
                <span>−{formatINR(order.pricing.discountPaise)}</span>
              </div>
            )}
            <div className="flex justify-between text-espresso-600 text-xs">
              <span>GST (5%)</span>
              <span>{formatINR(order.pricing.gstPaise)}</span>
            </div>
            <div className="flex justify-between text-espresso-600 text-xs">
              <span>Shipping</span>
              <span>
                {order.pricing.shippingPaise === 0
                  ? 'FREE'
                  : formatINR(order.pricing.shippingPaise)}
              </span>
            </div>
            <div className="flex justify-between border-t border-espresso-100 pt-2 text-base font-bold text-espresso-900">
              <span>Total</span>
              <span>{formatINR(order.pricing.totalPaise)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Indian GST Tax Invoice */}
      {invoice && (
        <section className="rounded-2xl border border-espresso-200 bg-white p-6">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-espresso-200 pb-4">
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-caramel" aria-hidden="true" />
              <h3 className="font-serif text-lg font-bold text-espresso-900">
                Tax Invoice ({invoice.invoiceNumber})
              </h3>
            </div>
            <button
              type="button"
              onClick={() => window.print()}
              className="inline-flex min-h-[38px] items-center gap-1.5 rounded-xl border border-espresso-300 px-3 text-xs font-semibold text-espresso-800 hover:bg-espresso-100"
            >
              <Printer className="h-3.5 w-3.5" aria-hidden="true" />
              Print Invoice
            </button>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 text-xs text-espresso-700 sm:grid-cols-2">
            <div>
              <div className="font-bold text-espresso-900">
                {invoice.seller.legalName}
              </div>
              <div>GSTIN: {invoice.seller.gstin}</div>
              <div>HSN/SAC: {invoice.seller.hsnSacCode} (Coffee & Gear)</div>
              <div>{invoice.seller.address}</div>
            </div>
            <div className="sm:text-right">
              <div>Invoice Date: {formatDateIN(invoice.issuedAt)}</div>
              <div>CGST (2.5%): {formatINR(invoice.pricing.cgstPaise)}</div>
              <div>SGST (2.5%): {formatINR(invoice.pricing.sgstPaise)}</div>
              <div className="font-bold text-espresso-900">
                Invoice Total: {formatINR(invoice.pricing.totalPaise)}
              </div>
            </div>
          </div>
        </section>
      )}

      <ConfirmDialog
        open={showCancelModal}
        title="Cancel this order?"
        description="Your reserved coffee stock will be released immediately, and any captured payment will be refunded."
        confirmLabel="Yes, Cancel Order"
        isBusy={cancelling}
        onConfirm={handleCancelOrder}
        onCancel={() => setShowCancelModal(false)}
      />
    </div>
  );
}
