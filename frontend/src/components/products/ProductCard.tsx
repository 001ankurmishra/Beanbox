'use client';

import React from 'react';
import Link from 'next/link';
import { Heart, ShoppingBag } from 'lucide-react';
import { useCart } from '@/context/CartContext';
import { useWishlist } from '@/context/WishlistContext';
import { CATEGORY_LABELS, formatINR, ROAST_LABELS } from '@/lib/format';
import { Product } from '@/types/api';
import { StarRating } from '@/components/ui/StarRating';

export function ProductCard({ product }: { product: Product }) {
  const { addItem } = useCart();
  const { isInWishlist, toggleWishlist } = useWishlist();

  const defaultVariant =
    product.variants.find((v) => v.stock > 0) ?? product.variants[0];
  const minPricePaise = Math.min(...product.variants.map((v) => v.pricePaise));
  const totalStock = product.variants.reduce((acc, v) => acc + v.stock, 0);
  const wishlisted = isInWishlist(product.id);

  return (
    <article className="group flex flex-col overflow-hidden rounded-2xl border border-espresso-200/80 bg-white transition hover:-translate-y-0.5 hover:shadow-warm">
      <div className="relative aspect-square overflow-hidden bg-espresso-100">
        <Link href={`/products/${product.slug}`} className="block h-full w-full">
          <img
            src={product.images[0] || '/images/products/beans-medium.svg'}
            alt={product.name}
            className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
          />
        </Link>

        <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
          <span className="rounded-full bg-espresso-900/85 px-2.5 py-1 text-[11px] font-medium text-espresso-50 backdrop-blur-sm">
            {CATEGORY_LABELS[product.category]}
          </span>
          {product.roastLevel !== 'na' && (
            <span className="rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-medium text-espresso-800">
              {ROAST_LABELS[product.roastLevel]}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => toggleWishlist(product)}
          aria-label={
            wishlisted
              ? `Remove ${product.name} from wishlist`
              : `Save ${product.name} to wishlist`
          }
          aria-pressed={wishlisted}
          className={`absolute right-3 top-3 flex h-10 w-10 items-center justify-center rounded-full border transition ${
            wishlisted
              ? 'border-rose-200 bg-rose-50 text-rose-600'
              : 'border-espresso-200 bg-white/90 text-espresso-700 hover:text-rose-600'
          }`}
        >
          <Heart
            className={`h-4 w-4 ${wishlisted ? 'fill-current' : ''}`}
            aria-hidden="true"
          />
        </button>

        {totalStock <= 5 && totalStock > 0 && (
          <span className="absolute bottom-3 left-3 rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-semibold text-amber-900 border border-amber-300">
            Low stock · {totalStock} left
          </span>
        )}
        {totalStock === 0 && (
          <span className="absolute bottom-3 left-3 rounded-full bg-stone-800/90 px-2.5 py-0.5 text-[11px] font-semibold text-white">
            Sold Out
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-caramel-dark">
            {product.origin}
          </span>
          <StarRating
            rating={product.ratingAverage}
            count={product.ratingCount}
          />
        </div>

        <Link
          href={`/products/${product.slug}`}
          className="mt-1.5 font-serif text-lg font-semibold text-espresso-900 hover:text-caramel line-clamp-2"
        >
          {product.name}
        </Link>

        <p className="mt-1 text-xs text-espresso-600 line-clamp-2">
          {product.shortDescription}
        </p>

        <div className="mt-3 flex flex-wrap gap-1">
          {product.tastingNotes.slice(0, 3).map((note) => (
            <span
              key={note}
              className="rounded-md bg-espresso-100/80 px-2 py-0.5 text-[11px] text-espresso-700"
            >
              {note}
            </span>
          ))}
        </div>

        <div className="mt-auto flex items-center justify-between gap-3 border-t border-espresso-100 pt-3.5 mt-4">
          <div>
            <span className="block text-[11px] text-espresso-500">From</span>
            <span className="text-base font-bold text-espresso-900">
              {formatINR(minPricePaise)}
            </span>
          </div>

          {defaultVariant && (
            <button
              type="button"
              disabled={defaultVariant.stock === 0}
              onClick={() => addItem(product, defaultVariant, 1)}
              className="inline-flex min-h-[40px] items-center gap-1.5 rounded-xl bg-espresso-900 px-3.5 py-2 text-xs font-semibold text-white hover:bg-caramel transition disabled:cursor-not-allowed disabled:bg-stone-300"
            >
              <ShoppingBag className="h-3.5 w-3.5" aria-hidden="true" />
              {defaultVariant.stock === 0 ? 'Sold Out' : 'Quick Add'}
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
