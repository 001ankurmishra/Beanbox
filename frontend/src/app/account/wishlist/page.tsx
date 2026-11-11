'use client';

import React from 'react';
import { Heart } from 'lucide-react';
import { useWishlist } from '@/context/WishlistContext';
import { ProductCard } from '@/components/products/ProductCard';
import { EmptyState } from '@/components/ui/EmptyState';

export default function AccountWishlistPage() {
  const { items, isLoading } = useWishlist();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <div className="h-80 animate-pulse rounded-2xl bg-white border border-espresso-200" />
        <div className="h-80 animate-pulse rounded-2xl bg-white border border-espresso-200" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        icon={<Heart className="h-7 w-7" aria-hidden="true" />}
        title="Your wishlist is empty"
        description="Tap the heart icon on any roast or pour-over kit to save it for later."
        actionLabel="Explore Coffees"
        actionHref="/shop"
      />
    );
  }

  return (
    <div>
      <h2 className="mb-5 font-serif text-xl font-bold text-espresso-900">
        Saved Favourites ({items.length})
      </h2>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </div>
  );
}
