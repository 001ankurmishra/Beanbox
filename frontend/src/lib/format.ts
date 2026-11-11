import {
  OrderStatus,
  ProductCategory,
  RoastLevel,
  VariantGrind
} from '@/types/api';

export function formatINR(paise: number): string {
  const rupees = paise / 100;
  const hasDecimals = paise % 100 !== 0;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: hasDecimals ? 2 : 0,
    maximumFractionDigits: hasDecimals ? 2 : 0
  }).format(rupees);
}

export const CATEGORY_LABELS: Record<ProductCategory, string> = {
  beans: 'Whole Beans',
  ground: 'Ground Coffee',
  cold_brew: 'Cold Brew',
  equipment: 'Brew Gear',
  gift_sets: 'Gift Sets'
};

export const ROAST_LABELS: Record<RoastLevel, string> = {
  light: 'Light Roast',
  medium_light: 'Medium-Light',
  medium: 'Medium Roast',
  medium_dark: 'Medium-Dark',
  dark: 'Dark Roast',
  na: 'Hardware / Set'
};

export const ROAST_LEVEL_DOTS: Record<RoastLevel, number> = {
  light: 1,
  medium_light: 2,
  medium: 3,
  medium_dark: 4,
  dark: 5,
  na: 0
};

export const GRIND_LABELS: Record<VariantGrind, string> = {
  whole_bean: 'Whole Bean',
  espresso: 'Espresso',
  filter: 'Filter / Drip',
  french_press: 'French Press',
  na: 'Standard'
};

export const ORDER_STATUS_STYLES: Record<
  OrderStatus,
  { label: string; badgeClass: string }
> = {
  pending: {
    label: 'Payment Pending',
    badgeClass: 'bg-amber-100 text-amber-900 border-amber-300'
  },
  paid: {
    label: 'Paid',
    badgeClass: 'bg-emerald-100 text-emerald-900 border-emerald-300'
  },
  processing: {
    label: 'Roasting & Packing',
    badgeClass: 'bg-sky-100 text-sky-900 border-sky-300'
  },
  shipped: {
    label: 'Shipped',
    badgeClass: 'bg-indigo-100 text-indigo-900 border-indigo-300'
  },
  delivered: {
    label: 'Delivered',
    badgeClass: 'bg-sage-light text-sage border-sage/30'
  },
  cancelled: {
    label: 'Cancelled',
    badgeClass: 'bg-rose-100 text-rose-900 border-rose-300'
  },
  refunded: {
    label: 'Refunded',
    badgeClass: 'bg-stone-200 text-stone-800 border-stone-300'
  }
};

export function formatDateIN(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  });
}
