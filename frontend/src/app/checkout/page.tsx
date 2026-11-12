'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  CheckCircle2,
  Lock,
  MapPin,
  Plus,
  Tag,
  X
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useCart } from '@/context/CartContext';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { addressesApi, authApi, ordersApi, paymentsApi } from '@/lib/api/endpoints';
import { formatINR } from '@/lib/format';
import { Address, CheckoutPreview } from '@/types/api';
import { EmptyState } from '@/components/ui/EmptyState';

export default function CheckoutPage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const { cart, refreshCart } = useCart();
  const { showToast } = useToast();

  const [addresses, setAddresses] = useState<Address[]>([]);
  const [selectedAddressId, setSelectedAddressId] = useState<string>('');
  const [showNewAddress, setShowNewAddress] = useState(false);

  const [couponInput, setCouponInput] = useState('');
  const [appliedCoupon, setAppliedCoupon] = useState<string | undefined>(undefined);
  const [preview, setPreview] = useState<CheckoutPreview | null>(null);
  const [loadingPage, setLoadingPage] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [resendingVerify, setResendingVerify] = useState(false);

  // New address form state
  const [addrLabel, setAddrLabel] = useState<'Home' | 'Work' | 'Other'>('Home');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [line1, setLine1] = useState('');
  const [line2, setLine2] = useState('');
  const [city, setCity] = useState('');
  const [stateName, setStateName] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [savingAddr, setSavingAddr] = useState(false);

  // Reuse one UUID idempotency key per checkout attempt across retries
  const orderIdempotencyKeyRef = useRef<string | null>(null);
  const paymentIdempotencyKeyRef = useRef<string | null>(null);

  useEffect(() => {
    orderIdempotencyKeyRef.current = null;
    paymentIdempotencyKeyRef.current = null;
  }, [selectedAddressId, appliedCoupon, cart.items]);

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace('/login?next=/checkout');
    }
  }, [authLoading, user, router]);

  const loadPreview = useCallback(
    async (coupon?: string, addressId?: string) => {
      const res = await ordersApi.previewCheckout({
        couponCode: coupon,
        addressId
      });
      setPreview(res.preview);
    },
    []
  );

  useEffect(() => {
    if (!user) return;
    let active = true;
    setLoadingPage(true);

    Promise.all([
      addressesApi.list(),
      cart.items.length > 0 ? ordersApi.previewCheckout({}) : Promise.resolve(null)
    ])
      .then(([addrRes, prevRes]) => {
        if (!active) return;
        setAddresses(addrRes.items);
        const def =
          addrRes.items.find((a) => a.isDefault) ?? addrRes.items[0];
        if (def) setSelectedAddressId(def.id);
        else setShowNewAddress(true);
        if (prevRes) setPreview(prevRes.preview);
      })
      .catch(() => {
        // Handled cleanly via empty state
      })
      .finally(() => {
        if (active) setLoadingPage(false);
      });

    return () => {
      active = false;
    };
  }, [user, cart.items.length]);

  const handleApplyCoupon = async (codeToApply?: string) => {
    const code = (codeToApply ?? couponInput).trim().toUpperCase();
    if (!code) return;
    try {
      await loadPreview(code, selectedAddressId || undefined);
      setAppliedCoupon(code);
      setCouponInput(code);
      showToast(`Coupon ${code} applied`, 'success');
    } catch (err) {
      const msg =
        err instanceof ApiClientError ? err.message : 'Invalid coupon code';
      showToast(msg, 'error');
    }
  };

  const handleRemoveCoupon = async () => {
    setAppliedCoupon(undefined);
    setCouponInput('');
    await loadPreview(undefined, selectedAddressId || undefined);
  };

  const handleSaveAddress = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingAddr(true);
    try {
      const res = await addressesApi.create({
        label: addrLabel,
        fullName,
        phone,
        line1,
        line2: line2 || undefined,
        city,
        state: stateName,
        postalCode,
        isDefault: addresses.length === 0
      });
      setAddresses((prev) => [res.address, ...prev]);
      setSelectedAddressId(res.address.id);
      setShowNewAddress(false);
      setFullName('');
      setPhone('');
      setLine1('');
      setLine2('');
      setCity('');
      setStateName('');
      setPostalCode('');
      showToast('Shipping address saved', 'success');
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Invalid address fields',
        'error'
      );
    } finally {
      setSavingAddr(false);
    }
  };

  const handlePlaceOrder = async () => {
    if (!selectedAddressId) {
      showToast('Please select or add a delivery address', 'error');
      return;
    }
    setSubmitting(true);
    if (!orderIdempotencyKeyRef.current) {
      orderIdempotencyKeyRef.current = crypto.randomUUID();
    }
    if (!paymentIdempotencyKeyRef.current) {
      paymentIdempotencyKeyRef.current = crypto.randomUUID();
    }
    try {
      const { order } = await ordersApi.create(
        {
          addressId: selectedAddressId,
          couponCode: appliedCoupon
        },
        orderIdempotencyKeyRef.current
      );
      const { session } = await paymentsApi.createSession(
        order.id,
        paymentIdempotencyKeyRef.current
      );
      await refreshCart();

      if (session.provider === 'mock') {
        const parsed = new URL(session.checkoutUrl);
        router.push(`${parsed.pathname}${parsed.search}`);
      } else {
        window.location.href = session.checkoutUrl;
      }
    } catch (err) {
      const msg =
        err instanceof ApiClientError
          ? err.message
          : 'Could not create order. Please review your bag.';
      showToast(msg, 'error');
      setSubmitting(false);
    }
  };

  if (authLoading || loadingPage) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="h-96 animate-pulse rounded-3xl bg-white border border-espresso-200" />
      </div>
    );
  }

  if (!user) return null;

  if (cart.items.length === 0 || !preview) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <EmptyState
          title="Nothing to check out yet"
          description="Your cart is empty. Add your favourite roasts before proceeding to checkout."
          actionLabel="Shop Coffees"
          actionHref="/shop"
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="border-b border-espresso-200 pb-6">
        <h1 className="font-serif text-3xl font-bold text-espresso-900">
          Secure Checkout
        </h1>
        <p className="mt-1 text-sm text-espresso-600">
          Pricing, coupon discounts, 5% GST, and shipping are verified live on our
          server.
        </p>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-12">
        {/* Left: Shipping Address & Coupon */}
        <div className="lg:col-span-7 space-y-8">
          {/* Address Section */}
          <section className="rounded-2xl border border-espresso-200 bg-white p-6">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-serif text-xl font-bold text-espresso-900">
                <MapPin className="h-5 w-5 text-caramel" aria-hidden="true" />
                1. Delivery Address
              </h2>
              <button
                type="button"
                onClick={() => setShowNewAddress((s) => !s)}
                className="inline-flex items-center gap-1 text-xs font-semibold text-caramel-dark hover:underline"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                {showNewAddress ? 'Close Form' : 'Add New Address'}
              </button>
            </div>

            {addresses.length > 0 && (
              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {addresses.map((addr) => {
                  const selected = addr.id === selectedAddressId;
                  return (
                    <button
                      key={addr.id}
                      type="button"
                      onClick={() => setSelectedAddressId(addr.id)}
                      className={`rounded-xl border p-4 text-left transition ${
                        selected
                          ? 'border-espresso-900 bg-espresso-50 ring-2 ring-espresso-900/15'
                          : 'border-espresso-200 hover:border-caramel'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="rounded-md bg-espresso-200/70 px-2 py-0.5 text-[11px] font-semibold text-espresso-800">
                          {addr.label}
                        </span>
                        {selected && (
                          <CheckCircle2
                            className="h-4 w-4 text-espresso-900"
                            aria-hidden="true"
                          />
                        )}
                      </div>
                      <div className="mt-2 font-semibold text-sm text-espresso-900">
                        {addr.fullName}
                      </div>
                      <div className="mt-1 text-xs text-espresso-600 leading-relaxed">
                        {addr.line1}
                        {addr.line2 ? `, ${addr.line2}` : ''}
                        <br />
                        {addr.city}, {addr.state} — {addr.postalCode}
                        <br />
                        Phone: {addr.phone}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {showNewAddress && (
              <form
                onSubmit={handleSaveAddress}
                className="mt-5 grid grid-cols-1 gap-4 border-t border-espresso-100 pt-5 sm:grid-cols-2"
              >
                <div>
                  <label
                    htmlFor="addr-label"
                    className="block text-xs font-semibold text-espresso-800"
                  >
                    Address Label
                  </label>
                  <select
                    id="addr-label"
                    value={addrLabel}
                    onChange={(e) =>
                      setAddrLabel(e.target.value as 'Home' | 'Work' | 'Other')
                    }
                    className="mt-1 h-11 w-full rounded-xl border border-espresso-200 bg-white px-3 text-sm"
                  >
                    <option value="Home">Home</option>
                    <option value="Work">Work</option>
                    <option value="Other">Other</option>
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="addr-name"
                    className="block text-xs font-semibold text-espresso-800"
                  >
                    Full Name *
                  </label>
                  <input
                    id="addr-name"
                    name="fullName"
                    type="text"
                    required
                    autoComplete="shipping name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
                  />
                </div>

                <div>
                  <label
                    htmlFor="addr-phone"
                    className="block text-xs font-semibold text-espresso-800"
                  >
                    10-Digit Mobile *
                  </label>
                  <input
                    id="addr-phone"
                    name="phone"
                    type="tel"
                    inputMode="numeric"
                    required
                    autoComplete="shipping tel"
                    placeholder="9820456789"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
                  />
                </div>

                <div>
                  <label
                    htmlFor="addr-pin"
                    className="block text-xs font-semibold text-espresso-800"
                  >
                    6-Digit PIN Code *
                  </label>
                  <input
                    id="addr-pin"
                    name="postalCode"
                    type="text"
                    inputMode="numeric"
                    pattern="[1-9][0-9]{5}"
                    required
                    autoComplete="shipping postal-code"
                    placeholder="560038"
                    value={postalCode}
                    onChange={(e) => setPostalCode(e.target.value)}
                    className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
                  />
                </div>

                <div className="sm:col-span-2">
                  <label
                    htmlFor="addr-line1"
                    className="block text-xs font-semibold text-espresso-800"
                  >
                    Flat / House / Street *
                  </label>
                  <input
                    id="addr-line1"
                    name="line1"
                    type="text"
                    required
                    autoComplete="shipping address-line1"
                    value={line1}
                    onChange={(e) => setLine1(e.target.value)}
                    className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
                  />
                </div>

                <div className="sm:col-span-2">
                  <label
                    htmlFor="addr-line2"
                    className="block text-xs font-semibold text-espresso-800"
                  >
                    Landmark / Locality (Optional)
                  </label>
                  <input
                    id="addr-line2"
                    name="line2"
                    type="text"
                    autoComplete="shipping address-line2"
                    value={line2}
                    onChange={(e) => setLine2(e.target.value)}
                    className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
                  />
                </div>

                <div>
                  <label
                    htmlFor="addr-city"
                    className="block text-xs font-semibold text-espresso-800"
                  >
                    City *
                  </label>
                  <input
                    id="addr-city"
                    name="city"
                    type="text"
                    required
                    autoComplete="shipping address-level2"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
                  />
                </div>

                <div>
                  <label
                    htmlFor="addr-state"
                    className="block text-xs font-semibold text-espresso-800"
                  >
                    State *
                  </label>
                  <input
                    id="addr-state"
                    name="state"
                    type="text"
                    required
                    autoComplete="shipping address-level1"
                    value={stateName}
                    onChange={(e) => setStateName(e.target.value)}
                    className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
                  />
                </div>

                <div className="sm:col-span-2 flex justify-end">
                  <button
                    type="submit"
                    disabled={savingAddr}
                    className="min-h-[44px] rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white hover:bg-espresso-800 disabled:opacity-50"
                  >
                    {savingAddr ? 'Saving…' : 'Save & Use Address'}
                  </button>
                </div>
              </form>
            )}
          </section>

          {/* Coupon Section */}
          <section className="rounded-2xl border border-espresso-200 bg-white p-6">
            <h2 className="flex items-center gap-2 font-serif text-xl font-bold text-espresso-900">
              <Tag className="h-5 w-5 text-caramel" aria-hidden="true" />
              2. Promo Coupon
            </h2>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleApplyCoupon();
              }}
              className="mt-4 flex gap-2.5"
            >
              <label htmlFor="coupon-code" className="sr-only">
                Coupon code
              </label>
              <input
                id="coupon-code"
                type="text"
                value={couponInput}
                onChange={(e) => setCouponInput(e.target.value.toUpperCase())}
                placeholder="Enter promo code (e.g. WELCOME10)"
                autoCorrect="off"
                autoCapitalize="characters"
                spellCheck={false}
                className="h-11 flex-1 rounded-xl border border-espresso-200 px-3.5 text-sm font-mono uppercase"
              />
              <button
                type="submit"
                className="min-h-[44px] rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white hover:bg-espresso-800"
              >
                Apply
              </button>
            </form>

            {preview.coupon && (
              <div className="mt-3 flex items-center justify-between rounded-xl bg-sage-light border border-sage/30 px-3.5 py-2.5 text-xs text-sage">
                <span>
                  Applied <strong>{preview.coupon.code}</strong> —{' '}
                  {preview.coupon.description}
                </span>
                <button
                  type="button"
                  onClick={handleRemoveCoupon}
                  aria-label="Remove coupon"
                  className="p-1 hover:text-espresso-900"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            )}

            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className="text-espresso-500 py-1">Try:</span>
              {['WELCOME10', 'FLAT150', 'BREW20'].map((code) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => handleApplyCoupon(code)}
                  className="rounded-lg border border-espresso-200 bg-espresso-50 px-2.5 py-1 font-mono font-semibold text-espresso-800 hover:border-caramel"
                >
                  {code}
                </button>
              ))}
            </div>
          </section>
        </div>

        {/* Right: Authoritative Backend Order Summary */}
        <aside className="lg:col-span-5">
          <div className="sticky top-28 rounded-2xl border border-espresso-200 bg-white p-6 space-y-5">
            <h2 className="font-serif text-xl font-bold text-espresso-900">
              Order Summary
            </h2>

            <ul className="divide-y divide-espresso-100 max-h-64 overflow-y-auto pr-1">
              {preview.items.map((item) => (
                <li
                  key={item.variantId}
                  className="flex items-center justify-between gap-3 py-3 text-sm"
                >
                  <div className="min-w-0">
                    <div className="font-semibold text-espresso-900 truncate">
                      {item.productName}
                    </div>
                    <div className="text-xs text-espresso-500">
                      {item.variantLabel} × {item.quantity}
                    </div>
                  </div>
                  <span className="font-semibold text-espresso-900 shrink-0">
                    {formatINR(item.lineTotalPaise)}
                  </span>
                </li>
              ))}
            </ul>

            <div className="space-y-2 border-t border-espresso-200 pt-4 text-sm">
              <div className="flex justify-between text-espresso-700">
                <span>Items Subtotal</span>
                <span>{formatINR(preview.pricing.itemsSubtotalPaise)}</span>
              </div>
              {preview.pricing.discountPaise > 0 && (
                <div className="flex justify-between text-sage font-medium">
                  <span>Coupon Discount ({preview.coupon?.code})</span>
                  <span>−{formatINR(preview.pricing.discountPaise)}</span>
                </div>
              )}
              <div className="flex justify-between text-espresso-700">
                <span>Taxable Value</span>
                <span>{formatINR(preview.pricing.taxableAmountPaise)}</span>
              </div>
              <div className="flex justify-between text-espresso-600 text-xs">
                <span>GST (5%: CGST 2.5% + SGST 2.5%)</span>
                <span>{formatINR(preview.pricing.gstPaise)}</span>
              </div>
              <div className="flex justify-between text-espresso-600 text-xs">
                <span>Shipping (Free above ₹999)</span>
                <span>
                  {preview.pricing.shippingPaise === 0
                    ? 'FREE'
                    : formatINR(preview.pricing.shippingPaise)}
                </span>
              </div>
              <div className="flex justify-between border-t border-espresso-200 pt-3 text-lg font-bold text-espresso-900">
                <span>Grand Total (INR)</span>
                <span>{formatINR(preview.pricing.totalPaise)}</span>
              </div>
            </div>

            {!user.emailVerified && (
              <div
                role="alert"
                className="rounded-xl border border-amber-300 bg-amber-50 p-3.5 text-xs text-amber-950 space-y-2"
              >
                <p className="font-semibold">
                  Verify your email address before placing an order.
                </p>
                <p>
                  We sent a verification link to <strong>{user.email}</strong>.
                </p>
                <div className="flex flex-wrap gap-2 pt-1">
                  <button
                    type="button"
                    disabled={resendingVerify}
                    onClick={async () => {
                      setResendingVerify(true);
                      try {
                        const r = await authApi.resendVerification();
                        showToast(r.message, 'success');
                      } catch (err) {
                        showToast(
                          err instanceof ApiClientError
                            ? err.message
                            : 'Please wait before resending',
                          'error'
                        );
                      } finally {
                        setResendingVerify(false);
                      }
                    }}
                    className="rounded-lg border border-amber-400 bg-white px-3 py-1.5 font-semibold text-amber-950 hover:bg-amber-100 disabled:opacity-50"
                  >
                    {resendingVerify ? 'Sending…' : 'Resend Email'}
                  </button>
                  <Link
                    href="/verify-email"
                    className="rounded-lg bg-amber-900 px-3 py-1.5 font-semibold text-white hover:bg-amber-800"
                  >
                    Verify Token
                  </Link>
                </div>
              </div>
            )}

            <button
              type="button"
              disabled={submitting || !selectedAddressId || !user.emailVerified}
              onClick={handlePlaceOrder}
              className="flex min-h-[50px] w-full items-center justify-center gap-2 rounded-xl bg-espresso-900 px-6 text-sm font-semibold text-white hover:bg-caramel transition disabled:opacity-50"
            >
              <Lock className="h-4 w-4" aria-hidden="true" />
              {submitting
                ? 'Creating Order & Payment Session…'
                : !user.emailVerified
                  ? 'Verify Email to Place Order'
                  : `Pay ${formatINR(preview.pricing.totalPaise)}`}
            </button>

            <p className="text-center text-xs text-espresso-500">
              Need to adjust items?{' '}
              <Link href="/cart" className="text-caramel-dark hover:underline">
                Return to bag
              </Link>
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
