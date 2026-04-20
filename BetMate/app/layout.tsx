import type { Metadata } from 'next';
import './globals.css';
import Header from '@/components/layout/Header';
import Footer from '@/components/layout/Footer';

export const metadata: Metadata = {
  title: 'BetMate — Best Odds. Quantitative Edge.',
  description:
    'Find the best odds across all major bookmakers. Powered by a quantitative model. EV analysis, market sentiment, and referee intelligence.',
  keywords: ['sports betting', 'NRL odds', 'AFL odds', 'EPL odds', 'best odds', 'EV betting', 'value betting'],
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
      <body className="min-h-screen bg-black text-white flex flex-col">
        <Header />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
