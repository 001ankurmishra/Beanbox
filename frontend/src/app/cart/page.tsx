'use client';

import React from 'react';
import Link from 'next/link';
import { ArrowRight, Minus, Plus, Trash2, Truck } from 'lucide-react';
import { useCart } from '@/context/CartContext';
import { formatINR } from '@/lib/format';
import { EmptyState } from '@/components/ui/EmptyState';

export default function CartPage() {
  const { cart, isLoading, updateQuantity, removeItem, clearCart } = useCart();

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="h-8 w-48 animate-pulse rounded bg-espresso-200/70" />
        <div className="mt-6 h-64 animate-pulse rounded-2xl bg-white border border-espresso-200" />
      </div>
    );
  }

  if (cart.items.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <EmptyState
          title="Your BeanBox bag is empty"
          description="Add freshly roasted beans, filter kaapi, cold brew concentrates, or gear to begin checkout."
          actionLabel="Explore Coffees"
          actionHref="/shop"
        />
      </div>
    );
  }

  const progress = Math.min(
    100,
    Math.round(
      (cart.itemsSubtotalPaise / (cart.freeShippingThresholdPaise || 99900)) * 100
    )
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-espresso-200 pb-6">
        <div>
          <h1 className="font-serif text-3xl font-bold text-espresso-900">
            Shopping Bag ({cart.itemCount})
          </h1>
          <p className="mt-1 text-sm text-espresso-600">
            All prices include freshly packed nitrogen-sealed freshness.
          </p>
        </div>
        <button
          type="button"
          onClick={clearCart}
          className="text-xs font-semibold text-rose-700 hover:underline"
        >
          Clear Bag
        </button>
      </div>

      {/* Free shipping progress */}
      <div className="mt-6 rounded-2xl border border-espresso-200 bg-white p-4">
        <div className="flex items-center gap-2 text-sm font-medium text-espresso-800">
          <Truck className="h-4 w-4 text-caramel" aria-hidden="true" />
          {cart.amountToFreeShippingPaise === 0 ? (
            <span className="text-sage font-semibold">
              Free express shipping unlocked across India!
            </span>
          ) : (
            <span>
              Add <strong>{formatINR(cart.amountToFreeShippingPaise)}</strong> more to
              unlock free shipping (orders ₹999+)
            </span>
          )}
        </div>
        <div className="mt-2.5 h-2 w-full overflow-hidden rounded-full bg-espresso-100">
          <div
            className="h-full rounded-full bg-caramel transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-12">
        {/* Line items */}
        <div className="lg:col-span-8 space-y-4">
          {cart.items.map((item) => (
            <div
              key={item.variantId}
              className="flex flex-col gap-4 rounded-2xl border border-espresso-200 bg-white p-4 sm:flex-row sm:items-center"
            >
              <img
                src={item.image}
                alt={item.productName}
                className="h-24 w-24 rounded-xl bg-espresso-100 object-cover shrink-0"
              />
              <div className="flex-1 min-w-0">
                <Link
                  href={`/products/${item.productSlug}`}
                  className="font-serif text-lg font-bold text-espresso-900 hover:text-caramel"
                >
                  {item.productName}
                </Link>
                <p className="text-sm text-espresso-600">{item.variantLabel}</p>
                <p className="mt-1 text-xs text-espresso-500">
                  {formatINR(item.unitPricePaise)} each · SKU {item.sku}
                </p>
              </div>

              <div className="flex items-center justify-between gap-4 sm:justify-end">
                <div className="inline-flex items-center rounded-xl border border-espresso-200 bg-espresso-50">
                  <button
                    type="button"
                    aria-label={`Decrease quantity of ${item.productName}`}
                    onClick={() =>
                      updateQuantity(item.variantId, item.quantity - 1)
                    }
                    className="flex h-10 w-10 items-center justify-center rounded-l-xl hover:bg-espresso-200/60"
                  >
                    <Minus className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <span className="w-9 text-center text-sm font-bold">
                    {item.quantity}
                  </span>
                  <button
                    type="button"
                    aria-label={`Increase quantity of ${item.productName}`}
                    disabled={item.quantity >= item.availableStock}
                    onClick={() =>
                      updateQuantity(item.variantId, item.quantity + 1)
                    }
                    className="flex h-10 w-10 items-center justify-center rounded-r-xl hover:bg-espresso-200/60 disabled:opacity-40"
                  >
                    <Plus className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>

                <div className="w-24 text-right text-base font-bold text-espresso-900">
                  {formatINR(item.lineTotalPaise)}
                </div>

                <button
                  type="button"
                  onClick={() => removeItem(item.variantId)}
                  aria-label={`Remove ${item.productName}`}
                  className="p-2 text-espresso-400 hover:text-rose-700"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Summary */}
        <aside className="lg:col-span-4">
          <div className="sticky top-28 rounded-2xl border border-espresso-200 bg-white p-6 space-y-4">
            <h2 className="font-serif text-xl font-bold text-espresso-900">
              Order Summary
            </h2>
            <div className="space-y-2.5 text-sm">
              <div className="flex justify-between text-espresso-700">
                <span>Items Subtotal</span>
                <span className="font-semibold">
                  {formatINR(cart.itemsSubtotalPaise)}
                </span>
              </div>
              <div className="flex justify-between text-espresso-600">
                <span>Estimated GST (5%)</span>
                <span>{formatINR(cart.estimatedGstPaise)}</span>
              </div>
              <div className="flex justify-between text-espresso-600">
                <span>Shipping</span>
                <span>
                  {cart.estimatedShippingPaise === 0
                    ? 'FREE'
                    : formatINR(cart.estimatedShippingPaise)}
                </span>
              </div>
              <div className="flex justify-between border-t border-espresso-200 pt-3 text-base font-bold text-espresso-900">
                <span>Estimated Total</span>
                <span>{formatINR(cart.estimatedTotalPaise)}</span>
              </div>
            </div>

            <p className="text-xs text-espresso-500">
              Promo codes (like <strong>WELCOME10</strong> or{' '}
              <strong>FLAT150</strong>) can be applied during checkout.
            </p>

            <Link
              href="/checkout"
              className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white hover:bg-caramel transition"
            >
              Proceed to Checkout
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </aside>
      </div>
    </div>
  );
}
