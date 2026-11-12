import type { Metadata } from 'next';
import { Fraunces, Plus_Jakarta_Sans } from 'next/font/google';
import './globals.css';
import { Providers } from '@/components/Providers';
import { VerifyEmailBanner } from '@/components/auth/VerifyEmailBanner';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { CartDrawer } from '@/components/cart/CartDrawer';

const fraunces = Fraunces({
  subsets: ['latin'],
  variable: '--font-fraunces',
  display: 'swap'
});

const jakarta = Plus_Jakarta_Sans({
  subsets: ['latin'],
  variable: '--font-jakarta',
  display: 'swap'
});

export const metadata: Metadata = {
  title: {
    default: 'BeanBox — Indian Specialty Coffee Roasters',
    template: '%s | BeanBox'
  },
  description:
    'Freshly roasted single-estate Indian coffee beans, South Indian filter kaapi, cold brew concentrates & pour-over gear. Free shipping above ₹999.',
  keywords: [
    'Indian specialty coffee',
    'Chikmagalur arabica',
    'Monsooned Malabar',
    'Filter Kaapi',
    'BeanBox'
  ]
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${fraunces.variable} ${jakarta.variable}`}>
      <body className="font-sans flex flex-col min-h-screen bg-espresso-50 text-espresso-900">
        <Providers>
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2 focus:bg-espresso-900 focus:text-white focus:rounded-lg"
          >
            Skip to main content
          </a>
          <Navbar />
          <VerifyEmailBanner />
          <CartDrawer />
          <main id="main-content" className="flex-1">
            {children}
          </main>
          <Footer />
        </Providers>
      </body>
    </html>
  );
}
