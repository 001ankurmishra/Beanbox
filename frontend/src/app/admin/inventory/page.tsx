'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { adminApi } from '@/lib/api/endpoints';
import { formatINR } from '@/lib/format';
import { Product } from '@/types/api';

export default function AdminInventoryPage() {
  const { showToast } = useToast();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [drafts, setDrafts] = useState<
    Record<string, { stock: string; priceInr: string }>
  >({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminApi.listProducts({ limit: 50 });
      setProducts(res.items);
      const nextDrafts: Record<string, { stock: string; priceInr: string }> = {};
      for (const p of res.items) {
        for (const v of p.variants) {
          nextDrafts[v.id] = {
            stock: String(v.stock),
            priceInr: String(Math.round(v.pricePaise / 100))
          };
        }
      }
      setDrafts(nextDrafts);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async (productId: string, variantId: string) => {
    const draft = drafts[variantId];
    if (!draft) return;
    try {
      await adminApi.updateInventory(productId, variantId, {
        stock: Number(draft.stock),
        pricePaise: Math.round(Number(draft.priceInr) * 100)
      });
      showToast('Inventory updated', 'success');
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Update failed',
        'error'
      );
    }
  };

  if (loading) {
    return (
      <div className="h-64 animate-pulse rounded-2xl bg-white border border-espresso-200" />
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="font-serif text-xl font-bold text-espresso-900">
        Variant Stock & INR Pricing
      </h2>

      <div
        tabIndex={0}
        role="region"
        aria-label="Inventory management table"
        className="table-scroll-region rounded-2xl border border-espresso-200 bg-white"
      >
        <table className="text-left text-sm">
          <thead className="bg-espresso-50 text-xs uppercase text-espresso-600">
            <tr>
              <th className="px-4 py-3">Product & Variant</th>
              <th className="px-4 py-3">SKU</th>
              <th className="px-4 py-3">Current Price</th>
              <th className="px-4 py-3">New Price (₹)</th>
              <th className="px-4 py-3">Stock</th>
              <th className="px-4 py-3 text-right">Save</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-espresso-100">
            {products.flatMap((prod) =>
              prod.variants.map((v) => {
                const draft = drafts[v.id] || {
                  stock: String(v.stock),
                  priceInr: String(v.pricePaise / 100)
                };
                return (
                  <tr key={v.id}>
                    <th scope="row" className="px-4 py-3">
                      <div className="font-semibold text-espresso-900">
                        {prod.name}
                      </div>
                      <div className="text-xs font-normal text-espresso-500">
                        {v.label}
                      </div>
                    </th>
                    <td className="px-4 py-3 font-mono text-xs">{v.sku}</td>
                    <td className="px-4 py-3 text-xs font-medium">
                      {formatINR(v.pricePaise)}
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        inputMode="numeric"
                        aria-label={`Price in INR for ${v.sku}`}
                        value={draft.priceInr}
                        onChange={(e) =>
                          setDrafts((d) => ({
                            ...d,
                            [v.id]: { ...draft, priceInr: e.target.value }
                          }))
                        }
                        className="h-9 w-24 rounded-lg border border-espresso-200 px-2.5 text-xs"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        inputMode="numeric"
                        aria-label={`Stock for ${v.sku}`}
                        value={draft.stock}
                        onChange={(e) =>
                          setDrafts((d) => ({
                            ...d,
                            [v.id]: { ...draft, stock: e.target.value }
                          }))
                        }
                        className={`h-9 w-20 rounded-lg border px-2.5 text-xs font-semibold ${
                          v.stock <= 5
                            ? 'border-amber-400 bg-amber-50 text-amber-900'
                            : 'border-espresso-200'
                        }`}
                      />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => handleSave(prod.id, v.id)}
                        className="inline-flex h-9 items-center gap-1 rounded-lg bg-espresso-900 px-3 text-xs font-semibold text-white hover:bg-caramel"
                      >
                        <Save className="h-3.5 w-3.5" aria-hidden="true" />
                        Save
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
