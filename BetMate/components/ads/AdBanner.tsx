'use client';

// AdBanner — placeholder ad slots matching the BetMate dark theme.
// variant="leaderboard"  → full-width horizontal strip (top of list)
// variant="inline"       → card-height inline slot (between game cards)

import Link from 'next/link';

type Promo = {
  bm:      string;
  logo:    string;   // google favicon domain
  label:   string;
  cta:     string;
  href:    string;
  accent:  string;   // tailwind bg class for the CTA button
};

const PROMOS: Promo[] = [
  {
    bm:     'Sportsbet',
    logo:   'sportsbet.com.au',
    label:  'New customers only. Bet $10, Get $30 in Bonus Bets.',
    cta:    'Claim Offer',
    href:   'https://www.sportsbet.com.au',
    accent: 'bg-[#F5A623]',
  },
  {
    bm:     'TAB',
    logo:   'tab.com.au',
    label:  'Sign up & get a $50 Bonus Bet on your first deposit.',
    cta:    'Join TAB',
    href:   'https://www.tab.com.au',
    accent: 'bg-[#007DC5]',
  },
  {
    bm:     'Bet365',
    logo:   'bet365.com.au',
    label:  'Open account offer. Up to $100 in Bet Credits.',
    cta:    'Bet Now',
    href:   'https://www.bet365.com.au',
    accent: 'bg-[#1C7F3D]',
  },
  {
    bm:     'Neds',
    logo:   'neds.com.au',
    label:  'New members: Deposit $50, Get $50 in Bonus Bets.',
    cta:    'Join Neds',
    href:   'https://www.neds.com.au',
    accent: 'bg-[#E8001C]',
  },
];

export default function AdBanner({
  variant  = 'leaderboard',
  promoIdx = 0,
}: {
  variant?:  'leaderboard' | 'inline' | 'chat';
  promoIdx?: number;
}) {
  const promo = PROMOS[promoIdx % PROMOS.length];

  if (variant === 'leaderboard') {
    return (
      <div className="relative w-full rounded border border-[#1C1C1C] bg-[#0A0A0A] overflow-hidden mb-3">
        <span className="absolute top-1.5 right-2 text-[9px] font-mono text-[#333] uppercase tracking-widest">
          Advertisement
        </span>

        <div className="flex items-center gap-4 px-4 py-3">
          {/* Logo */}
          <img
            src={`https://www.google.com/s2/favicons?domain=${promo.logo}&sz=64`}
            alt={promo.bm}
            className="w-8 h-8 rounded shrink-0"
          />

          {/* Text */}
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-mono font-bold text-white uppercase tracking-widest">
              {promo.bm}
            </p>
            <p className="text-[11px] font-mono text-[#666] leading-snug mt-0.5 truncate">
              {promo.label}
            </p>
          </div>

          {/* CTA */}
          <Link
            href={promo.href}
            target="_blank"
            rel="noopener noreferrer sponsored"
            className={`shrink-0 px-4 py-1.5 rounded text-[11px] font-mono font-bold uppercase tracking-widest text-black transition-opacity hover:opacity-90 ${promo.accent}`}
          >
            {promo.cta}
          </Link>
        </div>

        <p className="px-4 pb-1.5 text-[9px] font-mono text-[#2A2A2A]">
          18+ only. Gamble responsibly. T&Cs apply.
        </p>
      </div>
    );
  }

  // chat — compact strip that sits above the input bar
  if (variant === 'chat') {
    return (
      <div className="shrink-0 border-t border-[#1C1C1C] px-3 py-2 bg-[#080808]">
        <div className="flex items-center gap-3">
          <img
            src={`https://www.google.com/s2/favicons?domain=${promo.logo}&sz=64`}
            alt={promo.bm}
            className="w-6 h-6 rounded shrink-0"
          />
          <p className="flex-1 text-[10px] font-mono text-[#555] leading-snug min-w-0 truncate">
            <span className="text-[#888]">{promo.bm}:</span> {promo.label}
          </p>
          <Link
            href={promo.href}
            target="_blank"
            rel="noopener noreferrer sponsored"
            className={`shrink-0 px-3 py-1 rounded text-[10px] font-mono font-bold uppercase tracking-widest text-black transition-opacity hover:opacity-90 ${promo.accent}`}
          >
            {promo.cta}
          </Link>
        </div>
        <p className="text-[8px] font-mono text-[#222] mt-0.5 text-right">Ad · 18+ · Gamble responsibly</p>
      </div>
    );
  }

  // inline — styled like a game card, same visual weight
  return (
    <div className="relative w-full rounded border border-[#1C1C1C] bg-[#0A0A0A] overflow-hidden">
      <span className="absolute top-1.5 right-2 text-[9px] font-mono text-[#333] uppercase tracking-widest">
        Advertisement
      </span>

      <div className="flex items-center gap-4 px-4 py-4">
        {/* Logo */}
        <img
          src={`https://www.google.com/s2/favicons?domain=${promo.logo}&sz=64`}
          alt={promo.bm}
          className="w-10 h-10 rounded shrink-0"
        />

        {/* Text */}
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-mono font-bold text-white uppercase tracking-widest">
            {promo.bm} Special
          </p>
          <p className="text-[12px] font-mono text-[#666] leading-snug mt-0.5">
            {promo.label}
          </p>
        </div>

        {/* CTA */}
        <Link
          href={promo.href}
          target="_blank"
          rel="noopener noreferrer sponsored"
          className={`shrink-0 px-5 py-2 rounded text-[12px] font-mono font-bold uppercase tracking-widest text-black transition-opacity hover:opacity-90 ${promo.accent}`}
        >
          {promo.cta}
        </Link>
      </div>

      <p className="px-4 pb-2 text-[9px] font-mono text-[#2A2A2A]">
        18+ only. Gamble responsibly. T&Cs apply.
      </p>
    </div>
  );
}
