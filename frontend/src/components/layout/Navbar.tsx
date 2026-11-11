'use client';

import React, { useEffect, useId, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  Coffee,
  Heart,
  Menu,
  Search,
  ShieldCheck,
  ShoppingBag,
  User,
  X
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useCart } from '@/context/CartContext';
import { useWishlist } from '@/context/WishlistContext';

const NAV_LINKS = [
  { href: '/', label: 'Home' },
  { href: '/shop', label: 'Shop Coffee' },
  { href: '/shop?category=beans', label: 'Whole Beans' },
  { href: '/shop?category=ground', label: 'Filter Kaapi' },
  { href: '/shop?category=equipment', label: 'Brew Gear' }
];

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { cart, openDrawer } = useCart();
  const { items: wishlistItems } = useWishlist();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const mobileDialogRef = useRef<HTMLDialogElement>(null);
  const mobileMenuTitleId = useId();

  useEffect(() => {
    const dialog = mobileDialogRef.current;
    if (!dialog) return;
    if (mobileOpen && !dialog.open) {
      dialog.showModal();
    } else if (!mobileOpen && dialog.open) {
      dialog.close();
    }
  }, [mobileOpen]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchTerm.trim();
    router.push(q ? `/shop?search=${encodeURIComponent(q)}` : '/shop');
  };

  return (
    <header className="sticky top-0 z-40 border-b border-espresso-200/80 bg-espresso-50/95 backdrop-blur-md">
      {/* Announcement bar */}
      <div className="bg-espresso-900 px-4 py-1.5 text-center text-xs font-medium text-espresso-100">
        Freshly roasted weekly in Bengaluru · Free shipping on orders ₹999+ · Code{' '}
        <span className="font-bold text-caramel-light">WELCOME10</span> for 10% off
      </div>

      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={mobileOpen}
            className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-espresso-200 text-espresso-800 hover:bg-espresso-100 lg:hidden"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>

          <Link
            href="/"
            className="flex items-center gap-2.5 text-espresso-900 hover:opacity-90"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-espresso-900 text-caramel-light shadow-sm">
              <Coffee className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="leading-none">
              <span className="font-serif text-xl font-bold tracking-tight">
                BeanBox
              </span>
              <span className="block text-[10px] uppercase tracking-[0.2em] text-espresso-600">
                Indian Roasters
              </span>
            </div>
          </Link>
        </div>

        {/* Desktop Nav */}
        <nav aria-label="Primary" className="hidden lg:flex items-center gap-1">
          {NAV_LINKS.map((link) => {
            const isActive =
              link.href === '/'
                ? pathname === '/'
                : pathname === '/shop' && link.href === '/shop';
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive ? 'page' : undefined}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? 'bg-espresso-200/70 text-espresso-950 underline decoration-caramel decoration-2 underline-offset-4'
                    : 'text-espresso-700 hover:bg-espresso-100 hover:text-espresso-950'
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        {/* Search + Actions */}
        <div className="flex items-center gap-2 sm:gap-3">
          <search className="hidden md:block">
            <form onSubmit={handleSearchSubmit} className="relative">
              <label htmlFor="navbar-search" className="sr-only">
                Search coffees and gear
              </label>
              <input
                id="navbar-search"
                type="search"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search Chikmagalur, Kaapi…"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
                className="h-10 w-48 lg:w-56 rounded-xl border border-espresso-200 bg-white pl-3 pr-9 text-sm text-espresso-900 placeholder:text-espresso-400 focus:border-caramel focus:outline-none"
              />
              <button
                type="submit"
                aria-label="Search store"
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-espresso-600 hover:text-espresso-900"
              >
                <Search className="h-4 w-4" aria-hidden="true" />
              </button>
            </form>
          </search>

          {user?.role === 'admin' && (
            <Link
              href="/admin"
              className="hidden sm:inline-flex min-h-[40px] items-center gap-1.5 rounded-xl border border-caramel/40 bg-caramel/10 px-3 py-1.5 text-xs font-semibold text-caramel-dark hover:bg-caramel/20"
            >
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              Admin
            </Link>
          )}

          <Link
            href="/account/wishlist"
            aria-label={`Wishlist (${wishlistItems.length} saved)`}
            className="relative inline-flex h-11 w-11 items-center justify-center rounded-xl border border-espresso-200 bg-white text-espresso-800 hover:bg-espresso-100"
          >
            <Heart className="h-5 w-5" aria-hidden="true" />
            {wishlistItems.length > 0 && (
              <span className="absolute -right-1 -top-1 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-caramel px-1 text-[11px] font-bold text-white">
                {wishlistItems.length}
              </span>
            )}
          </Link>

          <button
            type="button"
            onClick={openDrawer}
            aria-label={`Open cart (${cart.itemCount} items)`}
            className="relative inline-flex h-11 items-center gap-2 rounded-xl bg-espresso-900 px-3.5 text-sm font-semibold text-espresso-50 hover:bg-espresso-800 transition"
          >
            <ShoppingBag className="h-4 w-4" aria-hidden="true" />
            <span className="hidden sm:inline">Cart</span>
            <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-caramel px-1.5 text-xs font-bold text-white">
              {cart.itemCount}
            </span>
          </button>

          {user ? (
            <Link
              href="/account"
              aria-label="My Account"
              className="inline-flex h-11 items-center gap-2 rounded-xl border border-espresso-200 bg-white px-3 text-sm font-medium text-espresso-800 hover:bg-espresso-100"
            >
              <User className="h-4 w-4" aria-hidden="true" />
              <span className="hidden sm:inline max-w-[96px] truncate">
                {user.name.split(' ')[0]}
              </span>
            </Link>
          ) : (
            <Link
              href="/login"
              className="inline-flex h-11 items-center rounded-xl border border-espresso-300 bg-white px-3.5 text-sm font-semibold text-espresso-900 hover:bg-espresso-100"
            >
              Sign in
            </Link>
          )}
        </div>
      </div>

      {/* Mobile Navigation Drawer (<dialog>) */}
      <dialog
        ref={mobileDialogRef}
        aria-labelledby={mobileMenuTitleId}
        {...({ closedby: 'any' } as Record<string, string>)}
        onCancel={() => setMobileOpen(false)}
        onClose={() => setMobileOpen(false)}
        className="m-0 h-dvh max-h-none w-[min(85vw,20rem)] max-w-none border-r border-espresso-200 bg-espresso-50 p-5 text-espresso-900 shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-espresso-200 pb-4">
          <h2 id={mobileMenuTitleId} className="font-serif text-lg font-bold">
            BeanBox Menu
          </h2>
          <button
            type="button"
            autoFocus
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation menu"
            className="flex h-10 w-10 items-center justify-center rounded-lg hover:bg-espresso-100"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <form onSubmit={handleSearchSubmit} className="mt-4">
          <label htmlFor="mobile-search" className="sr-only">
            Search coffees
          </label>
          <input
            id="mobile-search"
            type="search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search coffees…"
            className="h-11 w-full rounded-xl border border-espresso-200 bg-white px-3 text-sm"
          />
        </form>

        <nav aria-label="Mobile" className="mt-5 flex flex-col gap-1">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileOpen(false)}
              className="rounded-xl px-3 py-3 text-base font-medium text-espresso-800 hover:bg-espresso-100"
            >
              {link.label}
            </Link>
          ))}
          <hr className="my-2 border-espresso-200" />
          {user ? (
            <>
              <Link
                href="/account"
                className="rounded-xl px-3 py-3 text-base font-medium text-espresso-800 hover:bg-espresso-100"
              >
                My Account & Orders
              </Link>
              {user.role === 'admin' && (
                <Link
                  href="/admin"
                  className="rounded-xl px-3 py-3 text-base font-semibold text-caramel-dark hover:bg-espresso-100"
                >
                  Admin Console
                </Link>
              )}
              <button
                type="button"
                onClick={async () => {
                  await logout();
                  setMobileOpen(false);
                }}
                className="mt-2 rounded-xl border border-espresso-300 px-3 py-2.5 text-left text-sm font-medium text-rose-800 hover:bg-rose-50"
              >
                Sign out
              </button>
            </>
          ) : (
            <Link
              href="/login"
              className="rounded-xl bg-espresso-900 px-4 py-3 text-center text-sm font-semibold text-white"
            >
              Sign in / Create Account
            </Link>
          )}
        </nav>
      </dialog>
    </header>
  );
}
