import React from 'react';
import { Star } from 'lucide-react';

interface StarRatingProps {
  rating: number;
  count?: number;
  size?: 'sm' | 'md';
}

export function StarRating({ rating, count, size = 'sm' }: StarRatingProps) {
  const iconClass = size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4';
  const rounded = Math.round(rating);

  return (
    <div
      className="inline-flex items-center gap-1"
      aria-label={
        count !== undefined
          ? `${rating.toFixed(1)} out of 5 stars from ${count} review${count === 1 ? '' : 's'}`
          : `${rating.toFixed(1)} out of 5 stars`
      }
    >
      <div className="flex items-center gap-0.5" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((star) => (
          <Star
            key={star}
            className={`${iconClass} ${
              star <= rounded
                ? 'fill-caramel text-caramel'
                : 'fill-espresso-100 text-espresso-300'
            }`}
          />
        ))}
      </div>
      {count !== undefined && (
        <span className="text-xs text-espresso-600 ml-0.5">
          {rating > 0 ? `${rating.toFixed(1)} (${count})` : 'New'}
        </span>
      )}
    </div>
  );
}
