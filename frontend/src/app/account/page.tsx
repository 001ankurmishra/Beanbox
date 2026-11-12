'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { authApi } from '@/lib/api/endpoints';

export default function AccountProfilePage() {
  const { user, refreshUser } = useAuth();
  const { showToast } = useToast();

  const [name, setName] = useState(user?.name || '');
  const [phone, setPhone] = useState(user?.phone || '');
  const [saving, setSaving] = useState(false);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await authApi.updateMe({
        name: name.trim(),
        phone: phone.trim() || undefined
      });
      await refreshUser();
      showToast('Profile updated', 'success');
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Failed to update profile',
        'error'
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
      <section className="lg:col-span-6 rounded-2xl border border-espresso-200 bg-white p-6">
        <h2 className="font-serif text-xl font-bold text-espresso-900">
          Profile Details
        </h2>
        <form onSubmit={handleSave} className="mt-5 space-y-4">
          <div>
            <label
              htmlFor="prof-name"
              className="block text-xs font-semibold text-espresso-800"
            >
              Full Name
            </label>
            <input
              id="prof-name"
              type="text"
              required
              minLength={2}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3.5 text-sm"
            />
          </div>

          <div>
            <label
              htmlFor="prof-email"
              className="block text-xs font-semibold text-espresso-800"
            >
              Email Address
            </label>
            <input
              id="prof-email"
              type="email"
              disabled
              value={user?.email || ''}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 bg-espresso-50 px-3.5 text-sm text-espresso-500"
            />
          </div>

          <div>
            <label
              htmlFor="prof-phone"
              className="block text-xs font-semibold text-espresso-800"
            >
              Mobile Number
            </label>
            <input
              id="prof-phone"
              type="tel"
              inputMode="numeric"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="9820456789"
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3.5 text-sm"
            />
          </div>

          <button
            type="submit"
            disabled={saving}
            className="min-h-[44px] rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white hover:bg-caramel transition disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </form>
      </section>

      <section className="lg:col-span-6 space-y-4">
        <div className="rounded-2xl border border-espresso-200 bg-white p-6">
          <h2 className="font-serif text-xl font-bold text-espresso-900">
            Quick Shortcuts
          </h2>
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Link
              href="/account/orders"
              className="rounded-xl border border-espresso-200 p-4 hover:border-caramel"
            >
              <div className="font-semibold text-sm text-espresso-900">
                Order History & Invoices
              </div>
              <p className="mt-1 text-xs text-espresso-600">
                Track shipments, download GST invoices, or cancel pending brews.
              </p>
            </Link>
            <Link
              href="/account/addresses"
              className="rounded-xl border border-espresso-200 p-4 hover:border-caramel"
            >
              <div className="font-semibold text-sm text-espresso-900">
                Delivery Addresses
              </div>
              <p className="mt-1 text-xs text-espresso-600">
                Manage Home/Work addresses and PIN codes across India.
              </p>
            </Link>
            <Link
              href="/account/security"
              className="rounded-xl border border-espresso-200 p-4 hover:border-caramel sm:col-span-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-sm text-espresso-900">
                  Security Settings &amp; 2FA
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                    user?.totpEnabled
                      ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                      : 'bg-amber-50 text-amber-800 border border-amber-200'
                  }`}
                >
                  {user?.totpEnabled ? '2FA Active' : '2FA Off'}
                </span>
              </div>
              <p className="mt-1 text-xs text-espresso-600">
                Change your password, manage active devices, configure authenticator 2FA, and save backup recovery codes.
              </p>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
