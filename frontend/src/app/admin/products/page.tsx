'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';
import { adminApi } from '@/lib/api/endpoints';
import { CATEGORY_LABELS, formatINR, ROAST_LABELS } from '@/lib/format';
import { Product, ProductCategory, RoastLevel } from '@/types/api';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

export default function AdminProductsPage() {
  const { showToast } = useToast();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Product | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Create form fields
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [shortDescription, setShortDescription] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<ProductCategory>('beans');
  const [roastLevel, setRoastLevel] = useState<RoastLevel>('medium');
  const [origin, setOrigin] = useState('');
  const [notes, setNotes] = useState('Milk Chocolate, Caramel');
  const [sku, setSku] = useState('');
  const [priceInr, setPriceInr] = useState('549');
  const [stock, setStock] = useState('25');
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminApi.listProducts({ limit: 50 });
      setProducts(res.items);
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
      const imgByCat: Record<ProductCategory, string> = {
        beans: '/images/products/beans-medium.svg',
        ground: '/images/products/ground-roast.svg',
        cold_brew: '/images/products/cold-brew.svg',
        equipment: '/images/products/equipment-pour.svg',
        gift_sets: '/images/products/gift-box.svg'
      };
      await adminApi.createProduct({
        name,
        slug,
        shortDescription,
        description,
        category,
        roastLevel,
        origin,
        tastingNotes: notes
          .split(',')
          .map((n) => n.trim())
          .filter(Boolean),
        images: [imgByCat[category]],
        variants: [
          {
            sku: sku.toUpperCase(),
            size: category === 'equipment' ? 'standard' : '250g',
            grind: category === 'beans' ? 'whole_bean' : category === 'ground' ? 'filter' : 'na',
            label: category === 'equipment' ? 'Standard Unit' : '250g · Signature Pack',
            pricePaise: Math.round(Number(priceInr) * 100),
            stock: Number(stock)
          }
        ],
        isFeatured: false,
        isActive: true
      });
      showToast('Product created', 'success');
      setShowCreate(false);
      setName('');
      setSlug('');
      setShortDescription('');
      setDescription('');
      setOrigin('');
      setSku('');
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Failed to create product',
        'error'
      );
    } finally {
      setCreating(false);
    }
  };

  const toggleActive = async (prod: Product) => {
    try {
      await adminApi.updateProduct(prod.id, { isActive: !prod.isActive });
      showToast(
        `${prod.name} marked ${!prod.isActive ? 'active' : 'hidden'}`,
        'info'
      );
      await load();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Update failed',
        'error'
      );
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await adminApi.deleteProduct(deleteTarget.id);
      showToast(`Deleted ${deleteTarget.name}`, 'info');
      setDeleteTarget(null);
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
          Product Catalog ({products.length})
        </h2>
        <button
          type="button"
          onClick={() => setShowCreate((s) => !s)}
          className="inline-flex min-h-[42px] items-center gap-1.5 rounded-xl bg-espresso-900 px-4 text-xs font-semibold text-white hover:bg-caramel"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {showCreate ? 'Close Form' : 'New Product'}
        </button>
      </div>

      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="grid grid-cols-1 gap-4 rounded-2xl border border-espresso-200 bg-white p-6 sm:grid-cols-2"
        >
          <div>
            <label htmlFor="p-name" className="block text-xs font-semibold">
              Product Name *
            </label>
            <input
              id="p-name"
              type="text"
              required
              minLength={3}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (!slug) {
                  setSlug(
                    e.target.value
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, '-')
                      .replace(/^-|-$/g, '')
                  );
                }
              }}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor="p-slug" className="block text-xs font-semibold">
              URL Slug *
            </label>
            <input
              id="p-slug"
              type="text"
              required
              pattern="[a-z0-9-]+"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm font-mono"
            />
          </div>
          <div>
            <label htmlFor="p-cat" className="block text-xs font-semibold">
              Category
            </label>
            <select
              id="p-cat"
              value={category}
              onChange={(e) => setCategory(e.target.value as ProductCategory)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 bg-white px-3 text-sm"
            >
              <option value="beans">Whole Beans</option>
              <option value="ground">Ground Coffee</option>
              <option value="cold_brew">Cold Brew</option>
              <option value="equipment">Brew Gear</option>
              <option value="gift_sets">Gift Sets</option>
            </select>
          </div>
          <div>
            <label htmlFor="p-roast" className="block text-xs font-semibold">
              Roast Level
            </label>
            <select
              id="p-roast"
              value={roastLevel}
              onChange={(e) => setRoastLevel(e.target.value as RoastLevel)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 bg-white px-3 text-sm"
            >
              <option value="light">Light Roast</option>
              <option value="medium_light">Medium-Light</option>
              <option value="medium">Medium Roast</option>
              <option value="medium_dark">Medium-Dark</option>
              <option value="dark">Dark Roast</option>
              <option value="na">Hardware / N/A</option>
            </select>
          </div>
          <div>
            <label htmlFor="p-origin" className="block text-xs font-semibold">
              Origin *
            </label>
            <input
              id="p-origin"
              type="text"
              required
              placeholder="Chikmagalur, Karnataka"
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor="p-notes" className="block text-xs font-semibold">
              Tasting Notes (comma-separated)
            </label>
            <input
              id="p-notes"
              type="text"
              required
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="p-short" className="block text-xs font-semibold">
              Short Summary *
            </label>
            <input
              id="p-short"
              type="text"
              required
              minLength={10}
              value={shortDescription}
              onChange={(e) => setShortDescription(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
            />
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="p-desc" className="block text-xs font-semibold">
              Full Description *
            </label>
            <textarea
              id="p-desc"
              required
              minLength={10}
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-1 w-full rounded-xl border border-espresso-200 p-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor="p-sku" className="block text-xs font-semibold">
              Initial Variant SKU *
            </label>
            <input
              id="p-sku"
              type="text"
              required
              placeholder="BEAN-250-WB"
              value={sku}
              onChange={(e) => setSku(e.target.value)}
              className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm font-mono uppercase"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="p-price" className="block text-xs font-semibold">
                Price (INR ₹) *
              </label>
              <input
                id="p-price"
                type="text"
                inputMode="numeric"
                required
                value={priceInr}
                onChange={(e) => setPriceInr(e.target.value)}
                className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
              />
            </div>
            <div>
              <label htmlFor="p-stock" className="block text-xs font-semibold">
                Initial Stock *
              </label>
              <input
                id="p-stock"
                type="text"
                inputMode="numeric"
                required
                value={stock}
                onChange={(e) => setStock(e.target.value)}
                className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
              />
            </div>
          </div>
          <div className="sm:col-span-2 flex justify-end">
            <button
              type="submit"
              disabled={creating}
              className="min-h-[44px] rounded-xl bg-espresso-900 px-5 text-sm font-semibold text-white"
            >
              {creating ? 'Creating…' : 'Create Product'}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="h-64 animate-pulse rounded-2xl bg-white border border-espresso-200" />
      ) : (
        <div
          tabIndex={0}
          role="region"
          aria-label="Products catalog table"
          className="table-scroll-region rounded-2xl border border-espresso-200 bg-white"
        >
          <table className="text-left text-sm">
            <thead className="bg-espresso-50 text-xs uppercase text-espresso-600">
              <tr>
                <th className="px-4 py-3">Product</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Roast</th>
                <th className="px-4 py-3">From Price</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-espresso-100">
              {products.map((prod) => {
                const minPrice = Math.min(
                  ...prod.variants.map((v) => v.pricePaise)
                );
                return (
                  <tr key={prod.id}>
                    <th scope="row" className="px-4 py-3 font-semibold">
                      <div>{prod.name}</div>
                      <div className="text-xs font-normal text-espresso-500">
                        {prod.origin} · {prod.variants.length} variant(s)
                      </div>
                    </th>
                    <td className="px-4 py-3 text-xs">
                      {CATEGORY_LABELS[prod.category]}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {ROAST_LABELS[prod.roastLevel]}
                    </td>
                    <td className="px-4 py-3 font-semibold">
                      {formatINR(minPrice)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => toggleActive(prod)}
                        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          prod.isActive
                            ? 'bg-sage-light text-sage'
                            : 'bg-stone-200 text-stone-700'
                        }`}
                      >
                        {prod.isActive ? 'Active' : 'Hidden'}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        aria-label={`Delete ${prod.name}`}
                        onClick={() => setDeleteTarget(prod)}
                        className="p-1.5 text-rose-700 hover:bg-rose-50 rounded-lg"
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={`Delete ${deleteTarget?.name}?`}
        description="This removes the product from the catalog immediately."
        confirmLabel="Delete Product"
        isBusy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
