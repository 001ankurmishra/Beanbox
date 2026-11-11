'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState
} from 'react';
import { useRouter } from 'next/navigation';
import { ApiClientError } from '@/lib/api/client';
import { wishlistApi } from '@/lib/api/endpoints';
import { Product } from '@/types/api';
import { useAuth } from './AuthContext';
import { useToast } from './ToastContext';

interface WishlistContextValue {
  items: Product[];
  isLoading: boolean;
  isInWishlist: (productId: string) => boolean;
  toggleWishlist: (product: Product) => Promise<void>;
  refreshWishlist: () => Promise<void>;
}

const WishlistContext = createContext<WishlistContextValue | undefined>(undefined);

export function WishlistProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const { showToast } = useToast();
  const router = useRouter();
  const [items, setItems] = useState<Product[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const refreshWishlist = useCallback(async () => {
    if (!user) {
      setItems([]);
      return;
    }
    setIsLoading(true);
    try {
      const res = await wishlistApi.list();
      setItems(res.items);
    } catch {
      setItems([]);
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  useEffect(() => {
    refreshWishlist();
  }, [refreshWishlist]);

  const isInWishlist = useCallback(
    (productId: string) => items.some((p) => p.id === productId),
    [items]
  );

  const toggleWishlist = useCallback(
    async (product: Product) => {
      if (!user) {
        showToast('Please sign in to save favourites to your wishlist', 'info');
        router.push('/login');
        return;
      }

      const prev = items;
      const exists = prev.some((p) => p.id === product.id);
      const nextOptimistic = exists
        ? prev.filter((p) => p.id !== product.id)
        : [product, ...prev];

      setItems(nextOptimistic);

      try {
        const res = exists
          ? await wishlistApi.remove(product.id)
          : await wishlistApi.add(product.id);
        setItems(res.items);
        showToast(
          exists
            ? `Removed ${product.name} from wishlist`
            : `Saved ${product.name} to wishlist`,
          exists ? 'info' : 'success'
        );
      } catch (err) {
        setItems(prev);
        const msg =
          err instanceof ApiClientError ? err.message : 'Failed to update wishlist';
        showToast(msg, 'error');
      }
    },
    [user, items, showToast, router]
  );

  return (
    <WishlistContext.Provider
      value={{ items, isLoading, isInWishlist, toggleWishlist, refreshWishlist }}
    >
      {children}
    </WishlistContext.Provider>
  );
}

export function useWishlist() {
  const ctx = useContext(WishlistContext);
  if (!ctx) throw new Error('useWishlist must be used within WishlistProvider');
  return ctx;
}
