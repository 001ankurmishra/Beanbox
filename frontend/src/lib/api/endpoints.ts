import {
  Address,
  AdminDashboardStats,
  AuditLogEntry,
  AuthProvidersResponse,
  CacheStats,
  CheckoutPreview,
  Coupon,
  HydratedCart,
  LoginResult,
  Order,
  OrderInvoice,
  OrderStatus,
  PaginationMeta,
  Product,
  ProductCategory,
  ProductListResponse,
  ProductVariant,
  Review,
  ReviewListResponse,
  RoastLevel,
  TwoFactorSetupResponse,
  TwoFactorStatusResponse,
  User,
  UserRole,
  UserSession
} from '@/types/api';
import { sanitizeNextPath } from '@/lib/redirect';
import { API_BASE_URL, apiFetch } from './client';

export const authApi = {
  providers: () =>
    apiFetch<AuthProvidersResponse>('/auth/providers', { skipAuthRedirect: true }),
  csrf: () => apiFetch<{ csrfToken: string }>('/auth/csrf', { skipAuthRedirect: true }),
  me: () => apiFetch<{ user: User }>('/auth/me', { skipAuthRedirect: true }),
  updateMe: (body: { name?: string; phone?: string }) =>
    apiFetch<{ user: User }>('/auth/me', {
      method: 'PATCH',
      body: JSON.stringify(body)
    }),
  signup: (body: { name: string; email: string; password: string; phone?: string }) =>
    apiFetch<{ user: User; requiresEmailVerification?: boolean }>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  login: (body: { email: string; password: string }) =>
    apiFetch<LoginResult>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  verify2faLogin: (body: { challengeToken: string; code: string }) =>
    apiFetch<{ user: User; requiresTwoFactor?: false }>('/auth/2fa/verify-login', {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  refresh: () =>
    apiFetch<{ user: User }>('/auth/refresh', {
      method: 'POST',
      skipAuthRedirect: true
    }),
  logout: () =>
    apiFetch<{ message: string }>('/auth/logout', { method: 'POST' }),
  logoutAll: () =>
    apiFetch<{ message: string; revokedSessions: number }>('/auth/logout-all', {
      method: 'POST'
    }),
  changePassword: (body: { currentPassword: string; newPassword: string }) =>
    apiFetch<{ message: string; revokedOtherSessions: number }>(
      '/auth/change-password',
      {
        method: 'POST',
        body: JSON.stringify(body)
      }
    ),
  verifyEmail: (token: string) =>
    apiFetch<{ user: User; message: string }>('/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ token }),
      skipAuthRedirect: true
    }),
  resendVerification: () =>
    apiFetch<{ message: string }>('/auth/verify-email/resend', { method: 'POST' }),
  forgotPassword: (email: string) =>
    apiFetch<{ message: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email })
    }),
  resetPassword: (body: { token: string; newPassword: string }) =>
    apiFetch<{ message: string }>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  sessions: () => apiFetch<{ items: UserSession[] }>('/auth/sessions'),
  revokeSession: (sessionId: string) =>
    apiFetch<{ message: string }>(`/auth/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE'
    }),
  twoFactorStatus: () => apiFetch<TwoFactorStatusResponse>('/auth/2fa/status'),
  setup2fa: () =>
    apiFetch<TwoFactorSetupResponse>('/auth/2fa/setup', { method: 'POST' }),
  enable2fa: (code: string) =>
    apiFetch<{ user: User; totpEnabled: boolean; recoveryCodes: string[] }>(
      '/auth/2fa/enable',
      {
        method: 'POST',
        body: JSON.stringify({ code })
      }
    ),
  disable2fa: (body: { code: string; password?: string }) =>
    apiFetch<{ user: User; totpEnabled: boolean }>('/auth/2fa/disable', {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  regenerateRecoveryCodes: (code: string) =>
    apiFetch<{ recoveryCodes: string[] }>('/auth/2fa/recovery-codes/regenerate', {
      method: 'POST',
      body: JSON.stringify({ code })
    }),
  googleStartUrl: (nextPath = '/') =>
    `${API_BASE_URL}/auth/google/start?next=${encodeURIComponent(sanitizeNextPath(nextPath))}`
};

export interface ProductQueryParams {
  search?: string;
  category?: ProductCategory;
  roast?: RoastLevel;
  origin?: string;
  minPrice?: number;
  maxPrice?: number;
  inStock?: boolean;
  featured?: boolean;
  sort?: 'popular' | 'newest' | 'price_asc' | 'price_desc' | 'rating_desc';
  page?: number;
  limit?: number;
}

export const productsApi = {
  list: (params: ProductQueryParams = {}) =>
    apiFetch<ProductListResponse>('/products', {
      params: params as Record<string, string | number | boolean | undefined>
    }),
  detail: (slug: string) => apiFetch<{ product: Product }>(`/products/${slug}`),
  related: (slug: string, limit = 4) =>
    apiFetch<{ items: Product[] }>(`/products/${slug}/related`, {
      params: { limit }
    })
};

export const cartApi = {
  get: () => apiFetch<{ cart: HydratedCart }>('/cart'),
  addItem: (body: { productId: string; variantId: string; quantity: number }) =>
    apiFetch<{ cart: HydratedCart }>('/cart/items', {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  updateItem: (variantId: string, quantity: number) =>
    apiFetch<{ cart: HydratedCart }>(`/cart/items/${variantId}`, {
      method: 'PATCH',
      body: JSON.stringify({ quantity })
    }),
  removeItem: (variantId: string) =>
    apiFetch<{ cart: HydratedCart }>(`/cart/items/${variantId}`, {
      method: 'DELETE'
    }),
  clear: () => apiFetch<{ cart: HydratedCart }>('/cart', { method: 'DELETE' })
};

export const addressesApi = {
  list: () => apiFetch<{ items: Address[] }>('/addresses'),
  create: (body: {
    label: 'Home' | 'Work' | 'Other';
    fullName: string;
    phone: string;
    line1: string;
    line2?: string;
    city: string;
    state: string;
    postalCode: string;
    isDefault?: boolean;
  }) =>
    apiFetch<{ address: Address }>('/addresses', {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  update: (
    id: string,
    body: Partial<{
      label: 'Home' | 'Work' | 'Other';
      fullName: string;
      phone: string;
      line1: string;
      line2?: string;
      city: string;
      state: string;
      postalCode: string;
      isDefault?: boolean;
    }>
  ) =>
    apiFetch<{ address: Address }>(`/addresses/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body)
    }),
  remove: (id: string) =>
    apiFetch<{ message: string }>(`/addresses/${id}`, { method: 'DELETE' }),
  setDefault: (id: string) =>
    apiFetch<{ address: Address }>(`/addresses/${id}/default`, { method: 'PATCH' })
};

export const ordersApi = {
  previewCheckout: (body: { addressId?: string; couponCode?: string }) =>
    apiFetch<{ preview: CheckoutPreview }>('/checkout/preview', {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  create: (
    body: { addressId: string; couponCode?: string },
    idempotencyKey?: string
  ) =>
    apiFetch<{ order: Order }>('/orders', {
      method: 'POST',
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
      body: JSON.stringify(body)
    }),
  list: (page = 1, limit = 10) =>
    apiFetch<{ items: Order[]; pagination: PaginationMeta }>('/orders', {
      params: { page, limit }
    }),
  detail: (id: string) => apiFetch<{ order: Order }>(`/orders/${id}`),
  cancel: (id: string, reason?: string) =>
    apiFetch<{ order: Order }>(`/orders/${id}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    }),
  invoice: (id: string) =>
    apiFetch<{ invoice: OrderInvoice }>(`/orders/${id}/invoice`)
};

export const paymentsApi = {
  createSession: (orderId: string, idempotencyKey?: string) =>
    apiFetch<{
      session: {
        provider: 'stripe' | 'mock';
        sessionId: string;
        checkoutUrl: string;
      };
    }>('/payments/checkout-session', {
      method: 'POST',
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
      body: JSON.stringify({ orderId })
    }),
  triggerMock: (orderId: string, outcome: 'success' | 'failed' | 'expired') =>
    apiFetch<{
      webhookResult: { received: boolean; duplicate: boolean; status?: string };
      order: Order;
    }>('/payments/mock/trigger', {
      method: 'POST',
      body: JSON.stringify({ orderId, outcome })
    })
};

export const reviewsApi = {
  list: (slug: string, page = 1, limit = 10) =>
    apiFetch<ReviewListResponse>(`/products/${slug}/reviews`, {
      params: { page, limit }
    }),
  create: (slug: string, body: { rating: number; title: string; comment: string }) =>
    apiFetch<{ review: Review }>(`/products/${slug}/reviews`, {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  remove: (reviewId: string) =>
    apiFetch<{ message: string }>(`/reviews/${reviewId}`, { method: 'DELETE' })
};

export const wishlistApi = {
  list: () => apiFetch<{ items: Product[] }>('/wishlist'),
  add: (productId: string) =>
    apiFetch<{ items: Product[] }>(`/wishlist/${productId}`, { method: 'POST' }),
  remove: (productId: string) =>
    apiFetch<{ items: Product[] }>(`/wishlist/${productId}`, { method: 'DELETE' })
};

export const adminApi = {
  stats: () => apiFetch<{ stats: AdminDashboardStats }>('/admin/stats'),
  listProducts: (params: { search?: string; page?: number; limit?: number } = {}) =>
    apiFetch<{ items: Product[]; pagination: PaginationMeta }>('/admin/products', {
      params
    }),
  createProduct: (body: {
    name: string;
    slug: string;
    shortDescription: string;
    description: string;
    category: ProductCategory;
    roastLevel: RoastLevel;
    origin: string;
    tastingNotes: string[];
    images: string[];
    variants: Array<Omit<ProductVariant, 'id'> & { id?: string }>;
    isFeatured: boolean;
    isActive: boolean;
  }) =>
    apiFetch<{ product: Product }>('/admin/products', {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  updateProduct: (
    id: string,
    body: Partial<{
      name: string;
      slug: string;
      shortDescription: string;
      description: string;
      category: ProductCategory;
      roastLevel: RoastLevel;
      origin: string;
      tastingNotes: string[];
      images: string[];
      isFeatured: boolean;
      isActive: boolean;
    }>
  ) =>
    apiFetch<{ product: Product }>(`/admin/products/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body)
    }),
  deleteProduct: (id: string) =>
    apiFetch<{ message: string }>(`/admin/products/${id}`, { method: 'DELETE' }),
  updateInventory: (
    productId: string,
    variantId: string,
    body: { stock?: number; pricePaise?: number }
  ) =>
    apiFetch<{ variant: ProductVariant }>(
      `/admin/inventory/${productId}/${variantId}`,
      {
        method: 'PATCH',
        body: JSON.stringify(body)
      }
    ),
  listOrders: (params: { status?: OrderStatus; page?: number; limit?: number } = {}) =>
    apiFetch<{ items: Order[]; pagination: PaginationMeta }>('/admin/orders', {
      params
    }),
  updateOrderStatus: (id: string, status: OrderStatus, reason?: string) =>
    apiFetch<{ order: Order }>(`/admin/orders/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, reason })
    }),
  listCoupons: () => apiFetch<{ items: Coupon[] }>('/admin/coupons'),
  createCoupon: (body: {
    code: string;
    description: string;
    type: 'percent' | 'flat';
    value: number;
    minOrderPaise: number;
    maxDiscountPaise?: number;
    expiresAt: string;
    usageLimit: number;
    isActive: boolean;
  }) =>
    apiFetch<{ coupon: Coupon }>('/admin/coupons', {
      method: 'POST',
      body: JSON.stringify(body)
    }),
  updateCoupon: (
    id: string,
    body: Partial<{
      isActive: boolean;
      usageLimit: number;
      description: string;
    }>
  ) =>
    apiFetch<{ coupon: Coupon }>(`/admin/coupons/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body)
    }),
  deleteCoupon: (id: string) =>
    apiFetch<{ message: string }>(`/admin/coupons/${id}`, { method: 'DELETE' }),
  listUsers: (page = 1, limit = 20) =>
    apiFetch<{
      items: Array<User & { orderCount: number }>;
      pagination: PaginationMeta;
    }>('/admin/users', { params: { page, limit } }),
  updateUserRole: (userId: string, role: UserRole) =>
    apiFetch<{ user: User }>(`/admin/users/${encodeURIComponent(userId)}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ role })
    }),
  auditLogs: (
    params: { eventType?: string; userId?: string; page?: number; limit?: number } = {}
  ) =>
    apiFetch<{ items: AuditLogEntry[]; pagination: PaginationMeta }>(
      '/admin/audit-logs',
      { params }
    ),
  cacheStats: () => apiFetch<{ stats: CacheStats }>('/admin/cache-stats')
};
