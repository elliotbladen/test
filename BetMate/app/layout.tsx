import type { Metadata, Viewport } from 'next';
import './globals.css';
import Header from '@/components/layout/Header';
import Footer from '@/components/layout/Footer';
import ServiceWorker from '@/components/ServiceWorker';

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#000000',
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
    <html lang="en" className="dark">
      <body className="min-h-[100dvh] bg-black text-white flex flex-col">
        <ServiceWorker />
        <Header />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
