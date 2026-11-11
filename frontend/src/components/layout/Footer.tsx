import React from 'react';
import Link from 'next/link';
import { Coffee } from 'lucide-react';

export function Footer() {
  return (
    <footer className="mt-16 border-t border-espresso-200 bg-espresso-950 text-espresso-200">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-10 px-4 py-12 sm:grid-cols-2 lg:grid-cols-4 sm:px-6 lg:px-8">
        <div>
          <div className="flex items-center gap-2.5 text-espresso-50">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-caramel text-white">
              <Coffee className="h-5 w-5" aria-hidden="true" />
            </span>
            <span className="font-serif text-xl font-bold">BeanBox</span>
          </div>
          <p className="mt-4 text-sm leading-relaxed text-espresso-300">
            Small-batch specialty coffee roasted weekly in Indiranagar, Bengaluru.
            Direct-trade Indian estates from Chikmagalur, Coorg, Araku Valley &
            the Nilgiris.
          </p>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-caramel-light">
            Shop
          </h3>
          <ul className="mt-4 space-y-2.5 text-sm">
            <li>
              <Link href="/shop?category=beans" className="hover:text-white">
                Single Estate Whole Beans
              </Link>
            </li>
            <li>
              <Link href="/shop?category=ground" className="hover:text-white">
                South Indian Filter Kaapi
              </Link>
            </li>
            <li>
              <Link href="/shop?category=cold_brew" className="hover:text-white">
                Cold Brew Concentrates
              </Link>
            </li>
            <li>
              <Link href="/shop?category=equipment" className="hover:text-white">
                Brewing Equipment
              </Link>
            </li>
            <li>
              <Link href="/shop?category=gift_sets" className="hover:text-white">
                Curated Gift Sets
              </Link>
            </li>
          </ul>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-caramel-light">
            Account & Support
          </h3>
          <ul className="mt-4 space-y-2.5 text-sm">
            <li>
              <Link href="/account/orders" className="hover:text-white">
                Track Your Orders
              </Link>
            </li>
            <li>
              <Link href="/account/addresses" className="hover:text-white">
                Saved Addresses
              </Link>
            </li>
            <li>
              <Link href="/account/wishlist" className="hover:text-white">
                Wishlist
              </Link>
            </li>
            <li>
              <Link href="/cart" className="hover:text-white">
                Shopping Bag
              </Link>
            </li>
          </ul>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-caramel-light">
            India Pricing & Shipping
          </h3>
          <ul className="mt-4 space-y-2 text-sm text-espresso-300">
            <li>All prices in INR (₹) · 5% GST billed transparently</li>
            <li>Free express shipping above ₹999 (₹79 below ₹999)</li>
            <li>Roastery: 12th Main, Indiranagar, Bengaluru 560008</li>
            <li>Support: care@beanbox.in</li>
          </ul>
        </div>
      </div>

      <div className="border-t border-espresso-800 px-4 py-5 text-center text-xs text-espresso-400">
        © {new Date().getFullYear()} BeanBox Specialty Coffee Roasters Pvt. Ltd. ·
        GSTIN 29AABCB4821K1Z5
      </div>
    </footer>
  );
}
