export type UserRole = 'customer' | 'admin';

export interface User {
  id: string;
  name: string;
  email: string;
  phone?: string | null;
  role: UserRole;
  createdAt: string;
  updatedAt: string;
}

export type ProductCategory = 'beans' | 'ground' | 'cold_brew' | 'equipment' | 'gift_sets';
export type RoastLevel = 'light' | 'medium_light' | 'medium' | 'medium_dark' | 'dark' | 'na';
export type VariantSize = '250g' | '500g' | '1kg' | 'standard';
export type VariantGrind = 'whole_bean' | 'espresso' | 'filter' | 'french_press' | 'na';

export interface ProductVariant {
  id: string;
  sku: string;
  size: VariantSize;
  grind: VariantGrind;
  label: string;
  pricePaise: number;
  compareAtPaise?: number | null;
  stock: number;
}

export interface Product {
  id: string;
  name: string;
  slug: string;
  shortDescription: string;
  description: string;
  category: ProductCategory;
  roastLevel: RoastLevel;
  origin: string;
  tastingNotes: string[];
  images: string[];
  variants: ProductVariant[];
  isFeatured: boolean;
  isActive: boolean;
  ratingAverage: number;
  ratingCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface PaginationMeta {
  page: number;
  limit: number;
  totalItems: number;
  totalPages: number;
  hasNext: boolean;
  hasPrev: boolean;
}

export interface ProductListResponse {
  items: Product[];
  pagination: PaginationMeta;
  facets: {
    origins: string[];
    categories: ProductCategory[];
    roastLevels: RoastLevel[];
  };
}

export interface HydratedCartItem {
  productId: string;
  variantId: string;
  productName: string;
  productSlug: string;
  variantLabel: string;
  sku: string;
  image: string;
  unitPricePaise: number;
  quantity: number;
  lineTotalPaise: number;
  availableStock: number;
  inStock: boolean;
}

export interface HydratedCart {
  items: HydratedCartItem[];
  itemCount: number;
  itemsSubtotalPaise: number;
  estimatedGstPaise: number;
  estimatedShippingPaise: number;
  estimatedTotalPaise: number;
  freeShippingThresholdPaise: number;
  amountToFreeShippingPaise: number;
}

export interface Address {
  id: string;
  userId: string;
  label: 'Home' | 'Work' | 'Other';
  fullName: string;
  phone: string;
  line1: string;
  line2?: string | null;
  city: string;
  state: string;
  postalCode: string;
  country: 'India';
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
}

export type OrderStatus =
  | 'pending'
  | 'paid'
  | 'processing'
  | 'shipped'
  | 'delivered'
  | 'cancelled'
  | 'refunded';

export type PaymentStatus = 'unpaid' | 'paid' | 'failed' | 'expired' | 'refunded';

export interface OrderItem {
  productId: string;
  variantId: string;
  sku: string;
  productName: string;
  productSlug: string;
  variantLabel: string;
  image: string;
  unitPricePaise: number;
  quantity: number;
  lineTotalPaise: number;
}

export interface OrderPricing {
  itemsSubtotalPaise: number;
  discountPaise: number;
  taxableAmountPaise: number;
  gstRate: number;
  gstPaise: number;
  cgstPaise: number;
  sgstPaise: number;
  shippingPaise: number;
  totalPaise: number;
  currency: 'INR';
}

export interface Order {
  id: string;
  orderNumber: string;
  userId: string;
  items: OrderItem[];
  shippingAddress: {
    label: 'Home' | 'Work' | 'Other';
    fullName: string;
    phone: string;
    line1: string;
    line2?: string | null;
    city: string;
    state: string;
    postalCode: string;
    country: 'India';
  };
  couponCode?: string | null;
  couponId?: string | null;
  pricing: OrderPricing;
  status: OrderStatus;
  paymentStatus: PaymentStatus;
  paymentProvider?: 'stripe' | 'mock' | null;
  paymentSessionId?: string | null;
  paymentIntentId?: string | null;
  stockReleased: boolean;
  cancelReason?: string | null;
  createdAt: string;
  updatedAt: string;
  paidAt?: string | null;
  shippedAt?: string | null;
  deliveredAt?: string | null;
  cancelledAt?: string | null;
}

export interface CheckoutPreview {
  items: OrderItem[];
  pricing: OrderPricing;
  coupon: {
    code: string;
    description: string;
    type: 'percent' | 'flat';
    value: number;
  } | null;
  shippingAddressId?: string | null;
}

export interface OrderInvoice {
  invoiceNumber: string;
  issuedAt: string;
  orderNumber: string;
  orderStatus: OrderStatus;
  paymentStatus: PaymentStatus;
  seller: {
    legalName: string;
    brandName: string;
    gstin: string;
    address: string;
    hsnSacCode: string;
  };
  buyer: Order['shippingAddress'];
  items: Array<
    OrderItem & {
      hsnCode: string;
      taxableValuePaise: number;
      gstRatePercent: number;
    }
  >;
  pricing: OrderPricing;
  couponCode?: string | null;
}

export interface Review {
  id: string;
  productId: string;
  userId: string;
  userName: string;
  rating: number;
  title: string;
  comment: string;
  verifiedPurchase: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface ReviewListResponse {
  items: Review[];
  stats: {
    average: number;
    count: number;
    distribution: Record<string, number>;
  };
  pagination: PaginationMeta;
}

export interface Coupon {
  id: string;
  code: string;
  description: string;
  type: 'percent' | 'flat';
  value: number;
  minOrderPaise: number;
  maxDiscountPaise?: number | null;
  expiresAt: string;
  usageLimit: number;
  usedCount: number;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AdminDashboardStats {
  totalRevenuePaise: number;
  totalOrders: number;
  paidOrdersCount: number;
  pendingOrdersCount: number;
  totalCustomers: number;
  statusBreakdown: Record<OrderStatus, number>;
  topProducts: Array<{
    productId: string;
    productName: string;
    productSlug: string;
    unitsSold: number;
    revenuePaise: number;
  }>;
  recentOrders: Order[];
  lowStockVariants: Array<{
    productId: string;
    productName: string;
    productSlug: string;
    category: ProductCategory;
    variant: ProductVariant;
  }>;
}
