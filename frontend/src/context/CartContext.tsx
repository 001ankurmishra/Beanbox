'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState
} from 'react';
import { ApiClientError } from '@/lib/api/client';
import { cartApi } from '@/lib/api/endpoints';
import { HydratedCart, HydratedCartItem, Product, ProductVariant } from '@/types/api';
import { useAuth } from './AuthContext';
import { useToast } from './ToastContext';

const FREE_SHIPPING_THRESHOLD_PAISE = 99900;
const STANDARD_SHIPPING_PAISE = 7900;

const EMPTY_CART: HydratedCart = {
  items: [],
  itemCount: 0,
  itemsSubtotalPaise: 0,
  estimatedGstPaise: 0,
  estimatedShippingPaise: 0,
  estimatedTotalPaise: 0,
  freeShippingThresholdPaise: FREE_SHIPPING_THRESHOLD_PAISE,
  amountToFreeShippingPaise: FREE_SHIPPING_THRESHOLD_PAISE
};

function recomputeOptimisticCart(items: HydratedCartItem[]): HydratedCart {
  let itemCount = 0;
  let itemsSubtotalPaise = 0;
  for (const item of items) {
    itemCount += item.quantity;
    itemsSubtotalPaise += item.lineTotalPaise;
  }
  const estimatedGstPaise = Math.round(itemsSubtotalPaise * 0.05);
  const estimatedShippingPaise =
    itemsSubtotalPaise === 0 || itemsSubtotalPaise >= FREE_SHIPPING_THRESHOLD_PAISE
      ? 0
      : STANDARD_SHIPPING_PAISE;
  return {
    items,
    itemCount,
    itemsSubtotalPaise,
    estimatedGstPaise,
    estimatedShippingPaise,
    estimatedTotalPaise:
      itemsSubtotalPaise + estimatedGstPaise + estimatedShippingPaise,
    freeShippingThresholdPaise: FREE_SHIPPING_THRESHOLD_PAISE,
    amountToFreeShippingPaise: Math.max(
      0,
      FREE_SHIPPING_THRESHOLD_PAISE - itemsSubtotalPaise
    )
  };
}

interface CartContextValue {
  cart: HydratedCart;
  isLoading: boolean;
  isDrawerOpen: boolean;
  openDrawer: () => void;
  closeDrawer: () => void;
  refreshCart: () => Promise<void>;
  addItem: (
    product: Product,
    variant: ProductVariant,
    quantity?: number,
    options?: { openCartDrawer?: boolean }
  ) => Promise<boolean>;
  updateQuantity: (variantId: string, quantity: number) => Promise<void>;
  removeItem: (variantId: string) => Promise<void>;
  clearCart: () => Promise<void>;
}

const CartContext = createContext<CartContextValue | undefined>(undefined);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const { showToast } = useToast();
  const [cart, setCart] = useState<HydratedCart>(EMPTY_CART);
  const [isLoading, setIsLoading] = useState(true);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const refreshCart = useCallback(async () => {
    try {
      const res = await cartApi.get();
      setCart(res.cart);
    } catch {
      // Keep current state on transient failure
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Re-fetch cart whenever auth status changes (e.g. guest cart merged on login/signup)
  useEffect(() => {
    refreshCart();
  }, [user?.id, refreshCart]);

  const addItem = useCallback(
    async (
      product: Product,
      variant: ProductVariant,
      quantity = 1,
      options?: { openCartDrawer?: boolean }
    ) => {
      const prevCart = cart;
      const existing = prevCart.items.find((i) => i.variantId === variant.id);
      const nextQty = (existing?.quantity ?? 0) + quantity;

      const optimisticItems = existing
        ? prevCart.items.map((i) =>
            i.variantId === variant.id
              ? {
                  ...i,
                  quantity: nextQty,
                  lineTotalPaise: variant.pricePaise * nextQty
                }
              : i
          )
        : [
            ...prevCart.items,
            {
              productId: product.id,
              variantId: variant.id,
              productName: product.name,
              productSlug: product.slug,
              variantLabel: variant.label,
              sku: variant.sku,
              image: product.images[0] || '/images/products/beans-medium.svg',
              unitPricePaise: variant.pricePaise,
              quantity,
              lineTotalPaise: variant.pricePaise * quantity,
              availableStock: variant.stock,
              inStock: variant.stock >= nextQty
            }
          ];

      setCart(recomputeOptimisticCart(optimisticItems));
      if (options?.openCartDrawer !== false) {
        setIsDrawerOpen(true);
      }

      try {
        const res = await cartApi.addItem({
          productId: product.id,
          variantId: variant.id,
          quantity
        });
        setCart(res.cart);
        showToast(`Added ${product.name} to cart`, 'success');
        return true;
      } catch (err) {
        setCart(prevCart);
        const msg =
          err instanceof ApiClientError ? err.message : 'Could not add item to cart';
        showToast(msg, 'error');
        return false;
      }
    },
    [cart, showToast]
  );

  const updateQuantity = useCallback(
    async (variantId: string, quantity: number) => {
      const prevCart = cart;
      const optimisticItems =
        quantity <= 0
          ? prevCart.items.filter((i) => i.variantId !== variantId)
          : prevCart.items.map((i) =>
              i.variantId === variantId
                ? {
                    ...i,
                    quantity,
                    lineTotalPaise: i.unitPricePaise * quantity
                  }
                : i
            );
      setCart(recomputeOptimisticCart(optimisticItems));

      try {
        const res = await cartApi.updateItem(variantId, quantity);
        setCart(res.cart);
      } catch (err) {
        setCart(prevCart);
        const msg =
          err instanceof ApiClientError ? err.message : 'Failed to update quantity';
        showToast(msg, 'error');
      }
    },
    [cart, showToast]
  );

  const removeItem = useCallback(
    async (variantId: string) => {
      const prevCart = cart;
      const optimisticItems = prevCart.items.filter(
        (i) => i.variantId !== variantId
      );
      setCart(recomputeOptimisticCart(optimisticItems));

      try {
        const res = await cartApi.removeItem(variantId);
        setCart(res.cart);
        showToast('Removed item from cart', 'info');
      } catch (err) {
        setCart(prevCart);
        const msg =
          err instanceof ApiClientError ? err.message : 'Failed to remove item';
        showToast(msg, 'error');
      }
    },
    [cart, showToast]
  );

  const clearCart = useCallback(async () => {
    const prevCart = cart;
    setCart(EMPTY_CART);
    try {
      const res = await cartApi.clear();
      setCart(res.cart);
    } catch {
      setCart(prevCart);
    }
  }, [cart]);

  return (
    <CartContext.Provider
      value={{
        cart,
        isLoading,
        isDrawerOpen,
        openDrawer: () => setIsDrawerOpen(true),
        closeDrawer: () => setIsDrawerOpen(false),
        refreshCart,
        addItem,
        updateQuantity,
        removeItem,
        clearCart
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error('useCart must be used within CartProvider');
  return ctx;
}
