'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { adminApi } from '@/lib/api/endpoints';
import { formatDateIN, formatINR } from '@/lib/format';
import { Coupon } from '@/types/api';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

export default function AdminCouponsPage() {
  const { showToast } = useToast();
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Coupon | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [code, setCode] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState<'percent' | 'flat'>('percent');
  const [value, setValue] = useState('15');
  const [minOrderInr, setMinOrderInr] = useState('500');
  const [usageLimit, setUsageLimit] = useState('100');
  const [daysValid, setDaysValid] = useState('30');
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminApi.listCoupons();
      setCoupons(res.items);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const expiresAt = new Date(
        Date.now() + Number(daysValid) * 86400000
      ).toISOString();
      await adminApi.createCoupon({
        code,
        description,
        type,
        value:
          type === 'percent'
            ? Number(value)
            : Math.round(Number(value) * 100),
        minOrderPaise: Math.round(Number(minOrderInr) * 100),
        expiresAt,
        usageLimit: Number(usageLimit),
        isActive: true
      });
      showToast(`Coupon ${code.toUpperCase()} created`, 'success');
      setShowForm(false);
      setCode('');
      setDescription('');
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Failed to create coupon',
        'error'
      );
    } finally {
      setCreating(false);
    }
  };

  const toggleActive = async (coupon: Coupon) => {
    try {
      await adminApi.updateCoupon(coupon.id, { isActive: !coupon.isActive });
      showToast(`Updated ${coupon.code}`, 'info');
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Failed to update coupon',
        'error'
      );
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await adminApi.deleteCoupon(deleteTarget.id);
      showToast(`Deleted ${deleteTarget.code}`, 'info');
      setDeleteTarget(null);
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Failed to delete coupon',
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
          Promo Coupons ({coupons.length})
        </h2>
        <button
          type="button"
          onClick={() => setShowForm((s) => !s)}
          className="inline-flex min-h-[42px] items-center gap-1.5 rounded-xl bg-espresso-900 px-4 text-xs font-semibold text-white hover:bg-caramel"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {showForm ? 'Close Form' : 'New Coupon'}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="grid grid-cols-1 gap-4 rounded-2xl border border-espresso-200 bg-white p-6 sm:grid-cols-2"
        >
          <div>
            <label htmlFor="c-code" className="block text-xs font-semibold">
              Coupon Code *
            </label>
            <input
              id="c-code"
              type="text"
              required
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="ROAST15"
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm font-mono uppercase"
            />
          </div>
          <div>
            <label htmlFor="c-type" className="block text-xs font-semibold">
              Discount Type
            </label>
            <select
              id="c-type"
              value={type}
              onChange={(e) => setType(e.target.value as 'percent' | 'flat')}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 bg-white px-3 text-sm"
            >
              <option value="percent">Percentage (%)</option>
              <option value="flat">Flat INR (₹)</option>
            </select>
          </div>
          <div>
            <label htmlFor="c-val" className="block text-xs font-semibold">
              {type === 'percent' ? 'Discount % *' : 'Flat Amount (₹) *'}
            </label>
            <input
              id="c-val"
              type="text"
              inputMode="numeric"
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor="c-min" className="block text-xs font-semibold">
              Min Order (₹) *
            </label>
            <input
              id="c-min"
              type="text"
              inputMode="numeric"
              required
              value={minOrderInr}
              onChange={(e) => setMinOrderInr(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor="c-limit" className="block text-xs font-semibold">
              Usage Limit *
            </label>
            <input
              id="c-limit"
              type="text"
              inputMode="numeric"
              required
              value={usageLimit}
              onChange={(e) => setUsageLimit(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor="c-days" className="block text-xs font-semibold">
              Valid For (Days) *
            </label>
            <input
              id="c-days"
              type="text"
              inputMode="numeric"
              required
              value={daysValid}
              onChange={(e) => setDaysValid(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="c-desc" className="block text-xs font-semibold">
              Description *
            </label>
            <input
              id="c-desc"
              type="text"
              required
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="15% off freshly roasted single estates"
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div className="sm:col-span-2 flex justify-end">
            <button
              type="submit"
              disabled={creating}
              className="min-h-[44px] rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white"
            >
              {creating ? 'Creating…' : 'Create Coupon'}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="h-48 animate-pulse rounded-2xl bg-white border border-espresso-200" />
      ) : (
        <div
          tabIndex={0}
          role="region"
          aria-label="Coupons management table"
          className="table-scroll-region rounded-2xl border border-espresso-200 bg-white"
        >
          <table className="text-left text-sm">
            <thead className="bg-espresso-50 text-xs uppercase text-espresso-600">
              <tr>
                <th className="px-4 py-3">Code</th>
                <th className="px-4 py-3">Discount</th>
                <th className="px-4 py-3">Min Order</th>
                <th className="px-4 py-3">Usage</th>
                <th className="px-4 py-3">Expires</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Delete</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-espresso-100">
              {coupons.map((c) => (
                <tr key={c.id}>
                  <th scope="row" className="px-4 py-3 font-mono font-bold">
                    <div>{c.code}</div>
                    <div className="font-sans text-xs font-normal text-espresso-500">
                      {c.description}
                    </div>
                  </th>
                  <td className="px-4 py-3 font-semibold">
                    {c.type === 'percent' ? `${c.value}%` : formatINR(c.value)}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {formatINR(c.minOrderPaise)}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {c.usedCount} / {c.usageLimit}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {formatDateIN(c.expiresAt)}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => toggleActive(c)}
                      className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        c.isActive
                          ? 'bg-sage-light text-sage'
                          : 'bg-stone-200 text-stone-700'
                      }`}
                    >
                      {c.isActive ? 'Active' : 'Paused'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      aria-label={`Delete coupon ${c.code}`}
                      onClick={() => setDeleteTarget(c)}
                      className="p-1.5 text-rose-700 hover:bg-rose-50 rounded-lg"
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={`Delete coupon ${deleteTarget?.code}?`}
        description="Customers will no longer be able to apply this code."
        confirmLabel="Delete Coupon"
        isBusy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
