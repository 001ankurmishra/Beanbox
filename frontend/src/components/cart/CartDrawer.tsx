'use client';

import React, { useEffect, useId, useRef } from 'react';
import Link from 'next/link';
import { Minus, Plus, ShoppingBag, Trash2, Truck, X } from 'lucide-react';
import { useCart } from '@/context/CartContext';
import { formatINR } from '@/lib/format';

export function CartDrawer() {
  const {
    cart,
    isDrawerOpen,
    closeDrawer,
    updateQuantity,
    removeItem
  } = useCart();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (isDrawerOpen && !dialog.open) {
      dialog.showModal();
    } else if (!isDrawerOpen && dialog.open) {
      dialog.close();
    }
  }, [isDrawerOpen]);

  // Fallback light dismiss on backdrop click
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || 'closedBy' in HTMLDialogElement.prototype) return;

    let pressedOutside = false;
    const outside = (e: PointerEvent) => {
      const r = dialog.getBoundingClientRect();
      return (
        e.clientX < r.left ||
        e.clientX > r.right ||
        e.clientY < r.top ||
        e.clientY > r.bottom
      );
    };
    const onDown = (e: PointerEvent) => {
      pressedOutside = outside(e);
    };
    const onUp = (e: PointerEvent) => {
      if (pressedOutside && outside(e)) closeDrawer();
    };
    dialog.addEventListener('pointerdown', onDown);
    dialog.addEventListener('pointerup', onUp);
    return () => {
      dialog.removeEventListener('pointerdown', onDown);
      dialog.removeEventListener('pointerup', onUp);
    };
  }, [closeDrawer]);

  const freeProgress = Math.min(
    100,
    Math.round(
      (cart.itemsSubtotalPaise / (cart.freeShippingThresholdPaise || 99900)) * 100
    )
  );

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      {...({ closedby: 'any' } as Record<string, string>)}
      onCancel={closeDrawer}
      onClose={() => {
        if (isDrawerOpen) closeDrawer();
      }}
      className="ml-auto mr-0 my-0 h-dvh max-h-none w-[min(94vw,27rem)] max-w-none flex-col border-l border-espresso-200 bg-espresso-50 p-0 text-espresso-900 shadow-2xl open:flex"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-espresso-200 bg-white px-5 py-4">
        <div className="flex items-center gap-2.5">
          <ShoppingBag className="h-5 w-5 text-caramel" aria-hidden="true" />
          <h2 id={titleId} className="font-serif text-lg font-bold">
            Your Brew Bag ({cart.itemCount})
          </h2>
        </div>
        <button
          type="button"
          autoFocus
          onClick={closeDrawer}
          aria-label="Close cart drawer"
          className="flex h-10 w-10 items-center justify-center rounded-xl text-espresso-700 hover:bg-espresso-100"
        >
          <X className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      {/* Free shipping progress */}
      <div className="border-b border-espresso-200 bg-espresso-100/70 px-5 py-3">
        <div className="flex items-center gap-2 text-xs font-medium text-espresso-800">
          <Truck className="h-4 w-4 text-caramel shrink-0" aria-hidden="true" />
          {cart.amountToFreeShippingPaise === 0 && cart.itemCount > 0 ? (
            <span className="text-sage font-semibold">
              You unlocked FREE express shipping!
            </span>
          ) : (
            <span>
              Add{' '}
              <strong>{formatINR(cart.amountToFreeShippingPaise)}</strong> more for
              FREE shipping (above ₹999)
            </span>
          )}
        </div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-espresso-200">
          <div
            className="h-full rounded-full bg-caramel transition-all duration-300"
            style={{ width: `${freeProgress}%` }}
          />
        </div>
      </div>

      {/* Items */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {cart.items.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center py-10">
            <ShoppingBag className="h-12 w-12 text-espresso-300" aria-hidden="true" />
            <p className="mt-3 font-serif text-lg font-semibold text-espresso-900">
              Your bag is empty
            </p>
            <p className="mt-1 text-sm text-espresso-600">
              Explore single-estate beans, filter kaapi, or pour-over kits.
            </p>
            <Link
              href="/shop"
              onClick={closeDrawer}
              className="mt-5 inline-flex min-h-[44px] items-center rounded-xl bg-espresso-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-espresso-800"
            >
              Browse Coffees
            </Link>
          </div>
        ) : (
          <ul className="space-y-4">
            {cart.items.map((item) => (
              <li
                key={item.variantId}
                className="flex gap-3.5 rounded-2xl border border-espresso-200 bg-white p-3"
              >
                <img
                  src={item.image}
                  alt={item.productName}
                  className="h-20 w-20 rounded-xl bg-espresso-100 object-cover shrink-0"
                />
                <div className="flex flex-1 flex-col justify-between min-w-0">
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <Link
                        href={`/products/${item.productSlug}`}
                        onClick={closeDrawer}
                        className="text-sm font-semibold text-espresso-900 hover:text-caramel line-clamp-1"
                      >
                        {item.productName}
                      </Link>
                      <button
                        type="button"
                        onClick={() => removeItem(item.variantId)}
                        aria-label={`Remove ${item.productName}`}
                        className="text-espresso-400 hover:text-rose-700 p-1"
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                    <p className="text-xs text-espresso-600 mt-0.5">
                      {item.variantLabel}
                    </p>
                  </div>

                  <div className="mt-2 flex items-center justify-between">
                    <div className="inline-flex items-center rounded-lg border border-espresso-200 bg-espresso-50">
                      <button
                        type="button"
                        aria-label={`Decrease quantity of ${item.productName}`}
                        onClick={() =>
                          updateQuantity(item.variantId, item.quantity - 1)
                        }
                        className="flex h-8 w-8 items-center justify-center text-espresso-800 hover:bg-espresso-200/60 rounded-l-lg"
                      >
                        <Minus className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                      <span className="w-8 text-center text-xs font-semibold">
                        {item.quantity}
                      </span>
                      <button
                        type="button"
                        aria-label={`Increase quantity of ${item.productName}`}
                        disabled={item.quantity >= item.availableStock}
                        onClick={() =>
                          updateQuantity(item.variantId, item.quantity + 1)
                        }
                        className="flex h-8 w-8 items-center justify-center text-espresso-800 hover:bg-espresso-200/60 rounded-r-lg disabled:opacity-40"
                      >
                        <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    </div>
                    <span className="text-sm font-bold text-espresso-900">
                      {formatINR(item.lineTotalPaise)}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Footer summary */}
      {cart.items.length > 0 && (
        <div className="border-t border-espresso-200 bg-white px-5 py-4 space-y-3">
          <div className="space-y-1 text-sm">
            <div className="flex justify-between text-espresso-700">
              <span>Subtotal</span>
              <span className="font-medium">
                {formatINR(cart.itemsSubtotalPaise)}
              </span>
            </div>
            <div className="flex justify-between text-espresso-600 text-xs">
              <span>Est. GST (5%)</span>
              <span>{formatINR(cart.estimatedGstPaise)}</span>
            </div>
            <div className="flex justify-between text-espresso-600 text-xs">
              <span>Est. Shipping</span>
              <span>
                {cart.estimatedShippingPaise === 0
                  ? 'FREE'
                  : formatINR(cart.estimatedShippingPaise)}
              </span>
            </div>
            <div className="flex justify-between border-t border-espresso-100 pt-2 text-base font-bold text-espresso-900">
              <span>Estimated Total</span>
              <span>{formatINR(cart.estimatedTotalPaise)}</span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <Link
              href="/cart"
              onClick={closeDrawer}
              className="flex min-h-[44px] items-center justify-center rounded-xl border border-espresso-300 bg-white px-4 text-sm font-semibold text-espresso-900 hover:bg-espresso-100"
            >
              View Bag
            </Link>
            <Link
              href="/checkout"
              onClick={closeDrawer}
              className="flex min-h-[44px] items-center justify-center rounded-xl bg-espresso-900 px-4 text-sm font-semibold text-white hover:bg-espresso-800"
            >
              Checkout
            </Link>
          </div>
        </div>
      )}
    </dialog>
  );
}
