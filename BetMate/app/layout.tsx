import type { Metadata, Viewport } from 'next';
import { Suspense } from 'react';
import { Roboto, Montserrat } from 'next/font/google';
import './globals.css';
import Header from '@/components/layout/Header';

const roboto = Roboto({
  subsets: ['latin'],
  weight: ['300', '400', '500', '700'],
  variable: '--font-roboto',
  display: 'swap',
});

const montserrat = Montserrat({
  subsets: ['latin'],
  weight: ['600', '700', '800'],
  variable: '--font-montserrat',
  display: 'swap',
});
import Footer from '@/components/layout/Footer';
import ServiceWorker from '@/components/ServiceWorker';

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#0D0D0D',
};

export const metadata: Metadata = {
  title: 'BetMate — Best Odds. Quantitative Edge.',
  description:
    'Find the best odds across all major bookmakers. Powered by a quantitative model. EV analysis, market sentiment, and referee intelligence.',
  keywords: ['sports betting', 'NRL odds', 'AFL odds', 'EPL odds', 'best odds', 'EV betting', 'value betting'],
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'BetMate',
  },
  icons: {
    icon: '/icons/icon.svg',
    apple: '/icons/icon.svg',
  },
  openGraph: {
    title: 'BetMate',
    description: 'Find the best odds. Powered by a quantitative model.',
    type: 'website',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${roboto.variable} ${montserrat.variable}`}>
      <body className="min-h-[100dvh] bg-[#F0F2F5] text-[#111827] flex flex-col font-sans">
        <ServiceWorker />
        <Suspense fallback={null}>
          <Header />
        </Suspense>
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
