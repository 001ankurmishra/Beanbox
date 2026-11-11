'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Check, MapPin, Plus, Trash2 } from 'lucide-react';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { addressesApi } from '@/lib/api/endpoints';
import { Address } from '@/types/api';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState } from '@/components/ui/EmptyState';

export default function AccountAddressesPage() {
  const { showToast } = useToast();
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [label, setLabel] = useState<'Home' | 'Work' | 'Other'>('Home');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [line1, setLine1] = useState('');
  const [line2, setLine2] = useState('');
  const [city, setCity] = useState('');
  const [stateName, setStateName] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [isDefault, setIsDefault] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await addressesApi.list();
      setAddresses(res.items);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await addressesApi.create({
        label,
        fullName,
        phone,
        line1,
        line2: line2 || undefined,
        city,
        state: stateName,
        postalCode,
        isDefault
      });
      showToast('Address added', 'success');
      setShowForm(false);
      setFullName('');
      setPhone('');
      setLine1('');
      setLine2('');
      setCity('');
      setStateName('');
      setPostalCode('');
      setIsDefault(false);
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Failed to save address',
        'error'
      );
    } finally {
      setSaving(false);
    }
  };

  const handleSetDefault = async (id: string) => {
    try {
      await addressesApi.setDefault(id);
      showToast('Default delivery address updated', 'success');
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Update failed',
        'error'
      );
    }
  };

  const confirmDelete = async () => {
    if (!deleteId) return;
    setDeleting(true);
    try {
      await addressesApi.remove(deleteId);
      showToast('Address deleted', 'info');
      setDeleteId(null);
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Delete failed',
        'error'
      );
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-xl font-bold text-espresso-900">
          Saved Addresses
        </h2>
        <button
          type="button"
          onClick={() => setShowForm((s) => !s)}
          className="inline-flex min-h-[42px] items-center gap-1.5 rounded-xl bg-espresso-900 px-4 text-xs font-semibold text-white hover:bg-caramel"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {showForm ? 'Cancel' : 'Add Address'}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="grid grid-cols-1 gap-4 rounded-2xl border border-espresso-200 bg-white p-6 sm:grid-cols-2"
        >
          <div>
            <label htmlFor="a-label" className="block text-xs font-semibold">
              Label
            </label>
            <select
              id="a-label"
              value={label}
              onChange={(e) => setLabel(e.target.value as 'Home' | 'Work' | 'Other')}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 bg-white px-3 text-sm"
            >
              <option value="Home">Home</option>
              <option value="Work">Work</option>
              <option value="Other">Other</option>
            </select>
          </div>
          <div>
            <label htmlFor="a-name" className="block text-xs font-semibold">
              Full Name *
            </label>
            <input
              id="a-name"
              type="text"
              required
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor="a-phone" className="block text-xs font-semibold">
              Mobile Number *
            </label>
            <input
              id="a-phone"
              type="tel"
              inputMode="numeric"
              required
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="9820456789"
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor="a-pin" className="block text-xs font-semibold">
              6-Digit PIN Code *
            </label>
            <input
              id="a-pin"
              type="text"
              inputMode="numeric"
              pattern="[1-9][0-9]{5}"
              required
              value={postalCode}
              onChange={(e) => setPostalCode(e.target.value)}
              placeholder="560038"
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="a-l1" className="block text-xs font-semibold">
              Street Address *
            </label>
            <input
              id="a-l1"
              type="text"
              required
              value={line1}
              onChange={(e) => setLine1(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="a-l2" className="block text-xs font-semibold">
              Landmark (Optional)
            </label>
            <input
              id="a-l2"
              type="text"
              value={line2}
              onChange={(e) => setLine2(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor="a-city" className="block text-xs font-semibold">
              City *
            </label>
            <input
              id="a-city"
              type="text"
              required
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor="a-state" className="block text-xs font-semibold">
              State *
            </label>
            <input
              id="a-state"
              type="text"
              required
              value={stateName}
              onChange={(e) => setStateName(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div className="sm:col-span-2 flex items-center justify-between pt-2">
            <label className="inline-flex items-center gap-2 text-xs font-medium">
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                className="h-4 w-4 accent-espresso-900"
              />
              Set as default shipping address
            </label>
            <button
              type="submit"
              disabled={saving}
              className="min-h-[44px] rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white"
            >
              {saving ? 'Saving…' : 'Save Address'}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="h-40 animate-pulse rounded-2xl bg-white border border-espresso-200" />
      ) : addresses.length === 0 ? (
        <EmptyState
          icon={<MapPin className="h-7 w-7" aria-hidden="true" />}
          title="No saved addresses"
          description="Add a home or office delivery address for one-click checkout."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {addresses.map((addr) => (
            <div
              key={addr.id}
              className="flex flex-col justify-between rounded-2xl border border-espresso-200 bg-white p-5"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="rounded-lg bg-espresso-100 px-2.5 py-0.5 text-xs font-semibold text-espresso-800">
                    {addr.label}
                  </span>
                  {addr.isDefault && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-sage-light px-2.5 py-0.5 text-xs font-semibold text-sage">
                      <Check className="h-3 w-3" aria-hidden="true" />
                      Default
                    </span>
                  )}
                </div>
                <div className="mt-3 font-semibold text-sm text-espresso-900">
                  {addr.fullName}
                </div>
                <p className="mt-1 text-xs text-espresso-600 leading-relaxed">
                  {addr.line1}
                  {addr.line2 ? `, ${addr.line2}` : ''}
                  <br />
                  {addr.city}, {addr.state} — {addr.postalCode}
                  <br />
                  Mobile: {addr.phone}
                </p>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-espresso-100 pt-3">
                {!addr.isDefault ? (
                  <button
                    type="button"
                    onClick={() => handleSetDefault(addr.id)}
                    className="text-xs font-semibold text-caramel-dark hover:underline"
                  >
                    Set as Default
                  </button>
                ) : (
                  <span className="text-xs text-espresso-400">Primary address</span>
                )}
                <button
                  type="button"
                  onClick={() => setDeleteId(addr.id)}
                  aria-label="Delete address"
                  className="inline-flex items-center gap-1 text-xs font-medium text-rose-700 hover:underline"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deleteId)}
        title="Delete this address?"
        description="This shipping address will be permanently removed from your account."
        confirmLabel="Delete Address"
        isBusy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  );
}
