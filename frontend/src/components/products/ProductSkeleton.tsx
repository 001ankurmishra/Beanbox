import React from 'react';

export function ProductSkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div
      className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3"
      aria-busy="true"
      aria-label="Loading products"
    >
      {Array.from({ length: count }).map((_, idx) => (
        <div
          key={idx}
          className="animate-pulse overflow-hidden rounded-2xl border border-espresso-200 bg-white"
        >
          <div className="aspect-square bg-espresso-100" />
          <div className="space-y-3 p-4">
            <div className="h-3 w-24 rounded bg-espresso-100" />
            <div className="h-5 w-3/4 rounded bg-espresso-200/70" />
            <div className="h-3 w-full rounded bg-espresso-100" />
            <div className="flex justify-between pt-2">
              <div className="h-6 w-16 rounded bg-espresso-200/70" />
              <div className="h-9 w-24 rounded-xl bg-espresso-200/70" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
