'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Award, Coffee, Flame, Leaf, Sparkles, Truck } from 'lucide-react';
import { productsApi } from '@/lib/api/endpoints';
import { Product } from '@/types/api';
import { ProductCard } from '@/components/products/ProductCard';
import { ProductSkeletonGrid } from '@/components/products/ProductSkeleton';

const CATEGORIES = [
  {
    slug: 'beans',
    title: 'Whole Beans',
    subtitle: 'Single-estate washed & honey micro-lots',
    image: '/images/products/beans-medium.svg'
  },
  {
    slug: 'ground',
    title: 'Filter Kaapi & Ground',
    subtitle: 'Brass filter 80:20 & French press grinds',
    image: '/images/products/ground-kaapi.svg'
  },
  {
    slug: 'cold_brew',
    title: 'Cold Brew',
    subtitle: '18-hour slow steep bottles & pouches',
    image: '/images/products/cold-brew.svg'
  },
  {
    slug: 'equipment',
    title: 'Brew Gear',
    subtitle: 'Ceramic V60, brass filters & presses',
    image: '/images/products/equipment-pour.svg'
  },
  {
    slug: 'gift_sets',
    title: 'Gift Sets',
    subtitle: 'Curated tasting boxes & ritual kits',
    image: '/images/products/gift-box.svg'
  }
];

const TESTIMONIALS = [
  {
    quote:
      'The Ratnagiri Red Honey smells like warm caramel the moment you grind it. Arrived two days after roasting in Bengaluru.',
    author: 'Ananya Kulkarni',
    city: 'Mumbai',
    brew: 'V60 Pour-Over'
  },
  {
    quote:
      'Finally found an 80:20 Filter Kaapi blend that gives thick hotel-style frothy decoction without overpowering bitterness.',
    author: 'Karthik Sundaram',
    city: 'Chennai',
    brew: 'Brass Degree Filter'
  },
  {
    quote:
      'The Cold Brew concentrate saves my summer afternoons—just pour over ice and tonic. Zero acidity and rich chocolate notes.',
    author: 'Riya Chatterjee',
    city: 'Bengaluru',
    brew: 'Iced Tonic'
  }
];

export default function HomePage() {
  const [featured, setFeatured] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    productsApi
      .list({ featured: true, limit: 8, sort: 'popular' })
      .then((res) => setFeatured(res.items))
      .catch(() => setFeatured([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden bg-espresso-900 text-espresso-50">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(194,112,53,0.28),transparent_55%)]" />
        <div className="relative mx-auto grid max-w-7xl grid-cols-1 items-center gap-10 px-4 py-16 sm:px-6 lg:grid-cols-12 lg:py-24 lg:px-8">
          <div className="lg:col-span-7">
            <span className="inline-flex items-center gap-2 rounded-full border border-caramel/40 bg-caramel/15 px-3.5 py-1 text-xs font-semibold uppercase tracking-wider text-caramel-light">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Harvest 2026 · Roasted Weekly in Bengaluru
            </span>
            <h1 className="mt-5 font-serif text-4xl font-bold leading-[1.1] tracking-tight sm:text-5xl lg:text-6xl">
              Single-Estate Indian Coffee, Brewed to Perfection.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-relaxed text-espresso-200 sm:text-lg">
              From misty Chikmagalur peaks and coastal Coorg Monsooned Malabar to
              vibrant Araku Valley micro-lots—roasted to order and delivered fresh
              across India.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                href="/shop"
                className="inline-flex min-h-[48px] items-center gap-2 rounded-xl bg-caramel px-6 py-3 text-sm font-semibold text-white shadow-lg hover:bg-caramel-dark transition"
              >
                Explore All Roasts
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                href="/shop?category=gift_sets"
                className="inline-flex min-h-[48px] items-center rounded-xl border border-espresso-400/50 bg-espresso-800/60 px-6 py-3 text-sm font-semibold text-espresso-100 hover:bg-espresso-800 transition"
              >
                Shop Tasting Boxes
              </Link>
            </div>

            <div className="mt-10 grid grid-cols-1 gap-4 border-t border-espresso-700/80 pt-6 sm:grid-cols-3 text-xs text-espresso-200">
              <div className="flex items-center gap-2.5">
                <Truck className="h-4 w-4 text-caramel-light shrink-0" aria-hidden="true" />
                <span>Free express shipping above ₹999</span>
              </div>
              <div className="flex items-center gap-2.5">
                <Flame className="h-4 w-4 text-caramel-light shrink-0" aria-hidden="true" />
                <span>Small-batch roast within 48 hrs</span>
              </div>
              <div className="flex items-center gap-2.5">
                <Award className="h-4 w-4 text-caramel-light shrink-0" aria-hidden="true" />
                <span>100% Specialty Grade · 5% GST transparent</span>
              </div>
            </div>
          </div>

          <div className="lg:col-span-5">
            <div className="mx-auto max-w-md rounded-3xl border border-espresso-700/70 bg-espresso-800/60 p-6 shadow-2xl backdrop-blur-sm">
              <div className="grid grid-cols-2 gap-4">
                <img
                  src="/images/products/beans-medium.svg"
                  alt="Chikmagalur Arabica bag"
                  className="rounded-2xl bg-espresso-100"
                />
                <img
                  src="/images/products/ground-kaapi.svg"
                  alt="Madras Filter Kaapi tin"
                  className="rounded-2xl bg-espresso-100"
                />
                <img
                  src="/images/products/equipment-pour.svg"
                  alt="Ceramic V60 Pour Over kit"
                  className="rounded-2xl bg-espresso-100"
                />
                <img
                  src="/images/products/gift-box.svg"
                  alt="Indian Estate Discovery Box"
                  className="rounded-2xl bg-espresso-100"
                />
              </div>
              <div className="mt-4 flex items-center justify-between rounded-2xl bg-espresso-950/70 px-4 py-3 text-xs">
                <span>First order perk: Use code</span>
                <span className="rounded-lg bg-caramel px-2.5 py-1 font-mono font-bold text-white">
                  WELCOME10
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Categories */}
      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-caramel-dark">
              Curated For Every Brewer
            </p>
            <h2 className="mt-1 font-serif text-3xl font-bold text-espresso-900">
              Shop by Category
            </h2>
          </div>
          <Link
            href="/shop"
            className="text-sm font-semibold text-caramel-dark hover:underline"
          >
            View all 20 items →
          </Link>
        </div>

        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {CATEGORIES.map((cat) => (
            <Link
              key={cat.slug}
              href={`/shop?category=${cat.slug}`}
              className="group flex flex-col items-center rounded-2xl border border-espresso-200 bg-white p-4 text-center transition hover:border-caramel hover:shadow-warm"
            >
              <img
                src={cat.image}
                alt={cat.title}
                className="h-28 w-28 rounded-2xl object-cover transition group-hover:scale-105"
              />
              <h3 className="mt-3 font-serif text-base font-bold text-espresso-900">
                {cat.title}
              </h3>
              <p className="mt-1 text-xs text-espresso-600">{cat.subtitle}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* Featured Roasts */}
      <section className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-caramel-dark">
              Roaster&apos;s Selection
            </p>
            <h2 className="mt-1 font-serif text-3xl font-bold text-espresso-900">
              Featured Roasts & Kits
            </h2>
          </div>
          <Link
            href="/shop"
            className="text-sm font-semibold text-caramel-dark hover:underline"
          >
            Browse catalog →
          </Link>
        </div>

        <div className="mt-8">
          {loading ? (
            <ProductSkeletonGrid count={4} />
          ) : (
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {featured.map((product) => (
                <ProductCard key={product.id} product={product} />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Estate Terroir Banner */}
      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 rounded-3xl border border-espresso-200 bg-espresso-100/70 p-8 lg:grid-cols-3 lg:p-10">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-espresso-900 text-caramel-light">
              <Leaf className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <h3 className="font-serif text-lg font-bold text-espresso-900">
                Shade-Grown Indian Estates
              </h3>
              <p className="mt-1.5 text-sm text-espresso-700 leading-relaxed">
                Grown beneath silver oak, cardamom, and pepper canopies in
                Chikmagalur, Coorg, Araku Valley, and the Nilgiris.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-espresso-900 text-caramel-light">
              <Coffee className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <h3 className="font-serif text-lg font-bold text-espresso-900">
                Ground Custom to Your Brewer
              </h3>
              <p className="mt-1.5 text-sm text-espresso-700 leading-relaxed">
                Pick Whole Bean, Espresso, Pour-Over Filter, or French Press in
                250g, 500g, or 1kg nitrogen-flushed packs.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-espresso-900 text-caramel-light">
              <Truck className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <h3 className="font-serif text-lg font-bold text-espresso-900">
                Transparent GST & Free Delivery
              </h3>
              <p className="mt-1.5 text-sm text-espresso-700 leading-relaxed">
                Enjoy complimentary express shipping across India above ₹999 and
                downloadable GST tax invoices on every order.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="mx-auto max-w-7xl px-4 pb-8 sm:px-6 lg:px-8">
        <h2 className="text-center font-serif text-3xl font-bold text-espresso-900">
          Loved by Home Brewers Across India
        </h2>
        <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3">
          {TESTIMONIALS.map((t) => (
            <blockquote
              key={t.author}
              className="flex flex-col justify-between rounded-2xl border border-espresso-200 bg-white p-6 shadow-sm"
            >
              <p className="text-sm leading-relaxed text-espresso-700">
                &ldquo;{t.quote}&rdquo;
              </p>
              <footer className="mt-5 border-t border-espresso-100 pt-3">
                <div className="font-semibold text-sm text-espresso-900">
                  {t.author}
                </div>
                <div className="text-xs text-espresso-500">
                  {t.city} · {t.brew}
                </div>
              </footer>
            </blockquote>
          ))}
        </div>
      </section>
    </div>
  );
}
