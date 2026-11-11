'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  ArrowLeft,
  CheckCircle2,
  Heart,
  Minus,
  Plus,
  ShoppingBag,
  Sparkles,
  Trash2
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useCart } from '@/context/CartContext';
import { useToast } from '@/context/ToastContext';
import { useWishlist } from '@/context/WishlistContext';
import { ApiClientError } from '@/lib/api/client';
import { productsApi, reviewsApi } from '@/lib/api/endpoints';
import {
  CATEGORY_LABELS,
  formatDateIN,
  formatINR,
  GRIND_LABELS,
  ROAST_LABELS,
  ROAST_LEVEL_DOTS
} from '@/lib/format';
import { Product, ProductVariant, ReviewListResponse } from '@/types/api';
import { ProductCard } from '@/components/products/ProductCard';
import { StarRating } from '@/components/ui/StarRating';
import { EmptyState } from '@/components/ui/EmptyState';

export default function ProductDetailPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const { user } = useAuth();
  const { addItem } = useCart();
  const { isInWishlist, toggleWishlist } = useWishlist();
  const { showToast } = useToast();

  const [product, setProduct] = useState<Product | null>(null);
  const [related, setRelated] = useState<Product[]>([]);
  const [reviewsData, setReviewsData] = useState<ReviewListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFoundErr, setNotFoundErr] = useState(false);

  const [selectedImageIdx, setSelectedImageIdx] = useState(0);
  const [selectedVariantId, setSelectedVariantId] = useState<string>('');
  const [quantity, setQuantity] = useState(1);

  // Review form state
  const [rating, setRating] = useState(5);
  const [title, setTitle] = useState('');
  const [comment, setComment] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setNotFoundErr(false);
    try {
      const [detailRes, relRes, revRes] = await Promise.all([
        productsApi.detail(slug),
        productsApi.related(slug, 4),
        reviewsApi.list(slug, 1, 10)
      ]);
      setProduct(detailRes.product);
      setRelated(relRes.items);
      setReviewsData(revRes);

      const firstAvailable =
        detailRes.product.variants.find((v) => v.stock > 0) ??
        detailRes.product.variants[0];
      setSelectedVariantId(firstAvailable?.id ?? '');
    } catch {
      setNotFoundErr(true);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const selectedVariant: ProductVariant | undefined = useMemo(
    () => product?.variants.find((v) => v.id === selectedVariantId),
    [product, selectedVariantId]
  );

  const handleReviewSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!product) return;
    setSubmittingReview(true);
    try {
      await reviewsApi.create(product.slug, { rating, title, comment });
      showToast('Thank you! Your verified buyer review is live.', 'success');
      setTitle('');
      setComment('');
      await loadData();
    } catch (err) {
      const msg =
        err instanceof ApiClientError ? err.message : 'Could not post review';
      showToast(msg, 'error');
    } finally {
      setSubmittingReview(false);
    }
  };

  const handleDeleteReview = async (reviewId: string) => {
    try {
      await reviewsApi.remove(reviewId);
      showToast('Review deleted', 'info');
      await loadData();
    } catch (err) {
      showToast(
        err instanceof ApiClientError ? err.message : 'Could not delete review',
        'error'
      );
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-10 lg:grid-cols-2 animate-pulse">
          <div className="aspect-square rounded-3xl bg-espresso-100" />
          <div className="space-y-4 py-4">
            <div className="h-4 w-32 rounded bg-espresso-100" />
            <div className="h-10 w-3/4 rounded bg-espresso-200/70" />
            <div className="h-24 w-full rounded bg-espresso-100" />
            <div className="h-12 w-48 rounded-xl bg-espresso-200/70" />
          </div>
        </div>
      </div>
    );
  }

  if (notFoundErr || !product) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <EmptyState
          title="Coffee not found"
          description="This roast may have rotated out of season or the URL might be mistyped."
          actionLabel="Back to Shop"
          actionHref="/shop"
        />
      </div>
    );
  }

  const roastDots = ROAST_LEVEL_DOTS[product.roastLevel];
  const wishlisted = isInWishlist(product.id);
  const activeStock = selectedVariant?.stock ?? 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <Link
        href="/shop"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-espresso-700 hover:text-caramel-dark"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to Shop
      </Link>

      {/* Main Product Section */}
      <div className="mt-6 grid grid-cols-1 gap-10 lg:grid-cols-12">
        {/* Gallery */}
        <div className="lg:col-span-6 space-y-4">
          <div className="overflow-hidden rounded-3xl border border-espresso-200 bg-white">
            <img
              src={
                product.images[selectedImageIdx] ||
                product.images[0] ||
                '/images/products/beans-medium.svg'
              }
              alt={product.name}
              className="aspect-square w-full object-cover"
            />
          </div>

          {product.images.length > 1 && (
            <div className="flex gap-3">
              {product.images.map((img, idx) => (
                <button
                  key={`${img}-${idx}`}
                  type="button"
                  onClick={() => setSelectedImageIdx(idx)}
                  aria-label={`View image ${idx + 1}`}
                  className={`overflow-hidden rounded-2xl border-2 p-1 transition ${
                    selectedImageIdx === idx
                      ? 'border-caramel bg-white'
                      : 'border-espresso-200 opacity-70 hover:opacity-100'
                  }`}
                >
                  <img
                    src={img}
                    alt={`${product.name} thumbnail ${idx + 1}`}
                    className="h-16 w-16 rounded-xl object-cover"
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Details & Variant Picker */}
        <div className="lg:col-span-6 flex flex-col">
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
            <span className="rounded-full bg-espresso-900 px-3 py-1 text-white">
              {CATEGORY_LABELS[product.category]}
            </span>
            <span className="rounded-full bg-espresso-100 px-3 py-1 text-espresso-800">
              {product.origin}
            </span>
            {roastDots > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white border border-espresso-200 px-3 py-1 text-espresso-800">
                {ROAST_LABELS[product.roastLevel]}
                <span className="inline-flex gap-0.5" aria-hidden="true">
                  {[1, 2, 3, 4, 5].map((dot) => (
                    <span
                      key={dot}
                      className={`h-2 w-2 rounded-full ${
                        dot <= roastDots ? 'bg-espresso-900' : 'bg-espresso-200'
                      }`}
                    />
                  ))}
                </span>
              </span>
            )}
          </div>

          <h1 className="mt-4 font-serif text-3xl font-bold text-espresso-900 sm:text-4xl">
            {product.name}
          </h1>

          <div className="mt-3 flex items-center gap-3">
            <StarRating
              rating={product.ratingAverage}
              count={product.ratingCount}
              size="md"
            />
            {selectedVariant && (
              <span className="text-xs text-espresso-500">
                SKU: {selectedVariant.sku}
              </span>
            )}
          </div>

          <p className="mt-4 text-sm leading-relaxed text-espresso-700 sm:text-base">
            {product.description}
          </p>

          {/* Tasting notes */}
          <div className="mt-5">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-espresso-500">
              Tasting Notes & Highlights
            </h2>
            <div className="mt-2 flex flex-wrap gap-2">
              {product.tastingNotes.map((note) => (
                <span
                  key={note}
                  className="inline-flex items-center gap-1 rounded-xl border border-espresso-200 bg-white px-3 py-1.5 text-xs font-medium text-espresso-800"
                >
                  <Sparkles className="h-3 w-3 text-caramel" aria-hidden="true" />
                  {note}
                </span>
              ))}
            </div>
          </div>

          {/* Price */}
          {selectedVariant && (
            <div className="mt-6 flex items-baseline gap-3 border-y border-espresso-200 py-4">
              <span className="text-3xl font-bold text-espresso-900">
                {formatINR(selectedVariant.pricePaise)}
              </span>
              {selectedVariant.compareAtPaise &&
                selectedVariant.compareAtPaise > selectedVariant.pricePaise && (
                  <span className="text-base text-espresso-400 line-through">
                    {formatINR(selectedVariant.compareAtPaise)}
                  </span>
                )}
              <span className="ml-auto text-xs font-semibold">
                {activeStock > 5 ? (
                  <span className="text-sage">In Stock ({activeStock} bags)</span>
                ) : activeStock > 0 ? (
                  <span className="text-amber-700">
                    Low Stock — Only {activeStock} left!
                  </span>
                ) : (
                  <span className="text-rose-700">Out of Stock</span>
                )}
              </span>
            </div>
          )}

          {/* Variant Selector */}
          <div className="mt-6">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-espresso-600">
              Choose Pack Size & Grind
            </h2>
            <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {product.variants.map((variant) => {
                const selected = variant.id === selectedVariantId;
                return (
                  <button
                    key={variant.id}
                    type="button"
                    onClick={() => {
                      setSelectedVariantId(variant.id);
                      setQuantity(1);
                    }}
                    className={`flex items-center justify-between rounded-xl border p-3 text-left transition ${
                      selected
                        ? 'border-espresso-900 bg-espresso-900 text-white shadow-sm'
                        : 'border-espresso-200 bg-white text-espresso-900 hover:border-caramel'
                    } ${variant.stock === 0 ? 'opacity-60' : ''}`}
                  >
                    <div>
                      <div className="text-sm font-semibold">{variant.label}</div>
                      <div
                        className={`text-xs ${
                          selected ? 'text-espresso-200' : 'text-espresso-500'
                        }`}
                      >
                        {GRIND_LABELS[variant.grind]}
                        {variant.stock === 0 ? ' · Sold out' : ''}
                      </div>
                    </div>
                    <span className="text-sm font-bold">
                      {formatINR(variant.pricePaise)}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Quantity + Add to Cart + Wishlist */}
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <div className="inline-flex items-center rounded-xl border border-espresso-300 bg-white">
              <button
                type="button"
                aria-label="Decrease quantity"
                onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                className="flex h-12 w-11 items-center justify-center rounded-l-xl hover:bg-espresso-100"
              >
                <Minus className="h-4 w-4" aria-hidden="true" />
              </button>
              <span className="w-10 text-center text-sm font-bold">{quantity}</span>
              <button
                type="button"
                aria-label="Increase quantity"
                disabled={!selectedVariant || quantity >= selectedVariant.stock}
                onClick={() =>
                  setQuantity((q) =>
                    Math.min(selectedVariant?.stock ?? 1, 20, q + 1)
                  )
                }
                className="flex h-12 w-11 items-center justify-center rounded-r-xl hover:bg-espresso-100 disabled:opacity-40"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>

            <button
              type="button"
              disabled={!selectedVariant || selectedVariant.stock === 0}
              onClick={() =>
                selectedVariant && addItem(product, selectedVariant, quantity)
              }
              className="flex-1 min-h-[48px] inline-flex items-center justify-center gap-2 rounded-xl bg-espresso-900 px-6 text-sm font-semibold text-white hover:bg-caramel transition disabled:cursor-not-allowed disabled:bg-stone-300"
            >
              <ShoppingBag className="h-4 w-4" aria-hidden="true" />
              {selectedVariant && selectedVariant.stock > 0
                ? `Add to Bag · ${formatINR(selectedVariant.pricePaise * quantity)}`
                : 'Out of Stock'}
            </button>

            <button
              type="button"
              onClick={() => toggleWishlist(product)}
              aria-label={wishlisted ? 'Remove from wishlist' : 'Save to wishlist'}
              aria-pressed={wishlisted}
              className={`flex h-12 w-12 items-center justify-center rounded-xl border transition ${
                wishlisted
                  ? 'border-rose-200 bg-rose-50 text-rose-600'
                  : 'border-espresso-300 bg-white text-espresso-800 hover:bg-espresso-100'
              }`}
            >
              <Heart
                className={`h-5 w-5 ${wishlisted ? 'fill-current' : ''}`}
                aria-hidden="true"
              />
            </button>
          </div>
          <p className="mt-3 text-xs text-espresso-600">
            5% GST calculated at checkout · Free express shipping on orders ₹999+
          </p>
        </div>
      </div>

      {/* Reviews Section */}
      <section className="mt-16 border-t border-espresso-200 pt-12">
        <div className="grid grid-cols-1 gap-10 lg:grid-cols-12">
          {/* Summary & Form */}
          <div className="lg:col-span-5 space-y-6">
            <div>
              <h2 className="font-serif text-2xl font-bold text-espresso-900">
                Verified Buyer Reviews
              </h2>
              <div className="mt-2 flex items-center gap-3">
                <StarRating
                  rating={reviewsData?.stats.average ?? product.ratingAverage}
                  count={reviewsData?.stats.count ?? product.ratingCount}
                  size="md"
                />
              </div>
            </div>

            {/* Rating breakdown */}
            {reviewsData && (
              <div className="space-y-2 rounded-2xl border border-espresso-200 bg-white p-4">
                {[5, 4, 3, 2, 1].map((star) => {
                  const count = reviewsData.stats.distribution[String(star)] || 0;
                  const pct =
                    reviewsData.stats.count > 0
                      ? Math.round((count / reviewsData.stats.count) * 100)
                      : 0;
                  return (
                    <div key={star} className="flex items-center gap-3 text-xs">
                      <span className="w-8 font-semibold text-espresso-800">
                        {star} ★
                      </span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-espresso-100">
                        <div
                          className="h-full rounded-full bg-caramel"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="w-8 text-right text-espresso-600">
                        {count}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Write a review */}
            <div className="rounded-2xl border border-espresso-200 bg-white p-5">
              <h3 className="font-serif text-lg font-bold text-espresso-900">
                Leave a Review
              </h3>
              <p className="mt-1 text-xs text-espresso-600">
                Reviews are restricted to verified BeanBox buyers (one per product).
              </p>

              {!user ? (
                <Link
                  href="/login"
                  className="mt-4 inline-flex min-h-[42px] items-center rounded-xl bg-espresso-900 px-4 text-xs font-semibold text-white"
                >
                  Sign in to Review
                </Link>
              ) : (
                <form onSubmit={handleReviewSubmit} className="mt-4 space-y-3">
                  <div>
                    <label
                      htmlFor="review-rating"
                      className="block text-xs font-semibold text-espresso-800"
                    >
                      Rating
                    </label>
                    <select
                      id="review-rating"
                      value={rating}
                      onChange={(e) => setRating(Number(e.target.value))}
                      className="mt-1 h-11 w-full rounded-xl border border-espresso-200 bg-espresso-50 px-3 text-sm"
                    >
                      <option value={5}>5 Stars — Exceptional</option>
                      <option value={4}>4 Stars — Very Good</option>
                      <option value={3}>3 Stars — Solid</option>
                      <option value={2}>2 Stars — Okay</option>
                      <option value={1}>1 Star — Needs Work</option>
                    </select>
                  </div>

                  <div>
                    <label
                      htmlFor="review-title"
                      className="block text-xs font-semibold text-espresso-800"
                    >
                      Headline
                    </label>
                    <input
                      id="review-title"
                      type="text"
                      required
                      minLength={3}
                      maxLength={100}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Summarize your brew experience"
                      className="mt-1 h-11 w-full rounded-xl border border-espresso-200 px-3 text-sm"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="review-comment"
                      className="block text-xs font-semibold text-espresso-800"
                    >
                      Review
                    </label>
                    <textarea
                      id="review-comment"
                      required
                      minLength={5}
                      maxLength={1000}
                      rows={3}
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      placeholder="How did you brew it? What notes stood out?"
                      className="mt-1 w-full rounded-xl border border-espresso-200 p-3 text-sm"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={submittingReview}
                    className="w-full min-h-[44px] rounded-xl bg-espresso-900 px-4 text-sm font-semibold text-white hover:bg-espresso-800 disabled:opacity-50"
                  >
                    {submittingReview ? 'Submitting…' : 'Publish Review'}
                  </button>
                </form>
              )}
            </div>
          </div>

          {/* Review list */}
          <div className="lg:col-span-7 space-y-4">
            {!reviewsData || reviewsData.items.length === 0 ? (
              <EmptyState
                title="No reviews yet"
                description="Be the first verified buyer to share tasting notes on this roast."
              />
            ) : (
              reviewsData.items.map((rev) => (
                <article
                  key={rev.id}
                  className="rounded-2xl border border-espresso-200 bg-white p-5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <StarRating rating={rev.rating} />
                      <h3 className="mt-1.5 font-serif text-base font-bold text-espresso-900">
                        {rev.title}
                      </h3>
                    </div>
                    {(user?.id === rev.userId || user?.role === 'admin') && (
                      <button
                        type="button"
                        onClick={() => handleDeleteReview(rev.id)}
                        aria-label="Delete review"
                        className="p-1.5 text-espresso-400 hover:text-rose-700"
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-espresso-700">
                    {rev.comment}
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-espresso-500">
                    <span className="font-semibold text-espresso-800">
                      {rev.userName}
                    </span>
                    {rev.verifiedPurchase && (
                      <span className="inline-flex items-center gap-1 text-sage font-medium">
                        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                        Verified Buyer
                      </span>
                    )}
                    <span>{formatDateIN(rev.createdAt)}</span>
                  </div>
                </article>
              ))
            )}
          </div>
        </div>
      </section>

      {/* Related Products */}
      {related.length > 0 && (
        <section className="mt-16 border-t border-espresso-200 pt-12">
          <h2 className="font-serif text-2xl font-bold text-espresso-900">
            You May Also Enjoy
          </h2>
          <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {related.map((item) => (
              <ProductCard key={item.id} product={item} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
